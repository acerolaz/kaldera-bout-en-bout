"""Dépose les pièces générées par l'API (dossier 2.7) : même chemin que la prod, jamais d'INSERT.

Usage : make api & make worker-epreuve, puis uv run python tools/seed.py [--attente-s 900]
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

MANIFESTE = Path(__file__).resolve().parents[1] / "fixtures/pieces/manifeste.jsonl"


class EchecSeed(Exception):
    """Le seed ne s'est pas déroulé comme le manifeste le prévoit."""


def lire_manifeste(chemin: Path = MANIFESTE) -> list[dict[str, Any]]:
    return [json.loads(x) for x in chemin.read_text("utf-8").splitlines() if x.strip()]


def _verifier(reponse: httpx.Response, attendu: int, quoi: str) -> None:
    if reponse.status_code != attendu:
        raise EchecSeed(
            f"{quoi} : HTTP {reponse.status_code} au lieu de {attendu} ({reponse.text})"
        )


def deposer(
    client: httpx.Client, manifeste: list[dict[str, Any]], dossier: Path = MANIFESTE.parent
) -> list[str]:
    """Crée chaque demande, dépose ses fichiers, la soumet ; renvoie les références."""
    par_reference: dict[str, list[dict[str, Any]]] = {}
    for ligne in manifeste:
        par_reference.setdefault(ligne["reference"], []).append(ligne)
    for reference, lignes in par_reference.items():
        for ligne in lignes:
            if ligne["role"] == "demande":
                reponse = client.post("/demandes", json=ligne["json"])
                if reponse.status_code == 409:
                    raise EchecSeed(f"{reference} existe déjà : base déjà semée")
                _verifier(reponse, 201, reference)
                continue
            donnees = {"role": ligne["role"]}
            if ligne["role"] != "contrat":
                donnees["type"] = ligne["type"]
            if ligne["relance"] is not None:
                donnees["relance"] = str(ligne["relance"])
            octets = (dossier / ligne["fichier"]).read_bytes()
            reponse = client.post(
                f"/demandes/{reference}/pieces",
                files={"fichier": (Path(ligne["fichier"]).name, octets)},
                data=donnees,
            )
            _verifier(reponse, ligne["http"], f"{reference} {ligne['fichier']}")
        _verifier(client.post(f"/demandes/{reference}/soumettre"), 202, f"{reference} soumission")
    return list(par_reference)


def attendre(
    client: httpx.Client, references: list[str], attente_s: float, pause_s: float = 2.0
) -> None:
    """Jusqu'à ce que toutes les demandes soient traitées (``terminee``), au plus ``attente_s``."""
    echeance, restantes = time.monotonic() + attente_s, set(references)
    while True:
        restantes = {
            r for r in restantes if client.get(f"/demandes/{r}").json()["statut"] != "terminee"
        }
        if not restantes:
            return
        if time.monotonic() >= echeance:
            raise EchecSeed(f"délai dépassé : {len(restantes)} demande(s) non traitée(s)")
        time.sleep(pause_s)


def verites_fake(manifeste: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Ce que rendrait un VLM fidèle, par sha256 (tests : chaîne complète avec FakeVLM)."""
    verites: dict[str, dict[str, Any]] = {}
    for ligne in manifeste:
        if ligne["role"] == "contrat":
            verites[ligne["sha256"]] = (
                dict(ligne["attendu"]) if ligne["lisible"] else {"illisible": True}
            )
        elif "sha256" in ligne and ligne["http"] != 415:
            verites[ligne["sha256"]] = {
                "type": ligne["type"],
                "lisible": ligne["lisible"],
                "montant": ligne["montant"] if ligne["type"] == "facture" else None,
            }
    return verites


def main() -> None:
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--attente-s", type=float, default=900.0)
    a = args.parse_args()
    url = os.environ.get("KALDERA_API_URL", "http://localhost:8000")
    with httpx.Client(base_url=url, timeout=30) as client:
        try:
            references = deposer(client, lire_manifeste())
            print(f"{len(references)} demandes déposées et soumises ; attente du traitement…")
            attendre(client, references, a.attente_s)
        except EchecSeed as exc:
            raise SystemExit(f"seed en échec : {exc}") from exc
    print(f"{len(references)} demandes traitées")


if __name__ == "__main__":
    main()
