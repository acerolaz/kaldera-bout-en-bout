"""Intégration — adaptateurs PostgreSQL : pièces, garanties sous concurrence, bout en bout."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest

from kaldera import partenaire
from kaldera.etat import EtatDemande
from kaldera.orchestrateur import Orchestrateur
from kaldera.postgres import DepotPostgres, RegistreA2APostgres, SnapshotsPostgres
from kaldera.reaper import faucher

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
NOM_01 = json.loads((RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])


def _pieces(conn: Any) -> None:
    conn.execute(
        "INSERT INTO demandes (reference, etat, etat_courant, statut) "
        "VALUES ('KAL-26-9001', '{}', 'pieces', 'en_cours')"
    )
    lignes = [  # (sha, relance, type, statut_analyse, lisible, montant)
        ("1" * 64, None, "facture", "ok", True, 640.50),
        ("2" * 64, None, "photo", "echec", True, None),
        ("3" * 64, 1, "photo", "ok", True, None),
        ("4" * 64, 2, "facture", "en_attente", None, None),
    ]
    for sha, relance, type_, statut, lisible, montant in lignes:
        conn.execute(
            "INSERT INTO blobs (sha256, contenu, mime, taille) VALUES (%s, 'x', 'application/pdf', 1)",
            (sha,),
        )
        conn.execute(
            "INSERT INTO pieces (reference, sha256, relance, type, statut_analyse, lisible, montant) "
            "VALUES ('KAL-26-9001', %s, %s, %s, %s, %s, %s)",
            (sha, relance, type_, statut, lisible, montant),
        )


def test_depot_postgres(base: Any) -> None:
    with base.connection() as conn:
        _pieces(conn)
    depot = DepotPostgres(base)
    demande = {"reference": "KAL-26-9001"}
    initiales = sorted(depot.initiales(demande), key=lambda p: p.type)
    assert [(p.type, p.lisible, p.montant, p.statut_analyse) for p in initiales] == [
        ("facture", True, 640.5, "ok"),
        ("photo", False, None, "echec"),
    ]
    assert all(p.piece_id is not None and p.sha256 for p in initiales)
    depots = depot.depots(demande)
    assert [(p.type, p.lisible, p.statut_analyse) for p in depots] == [
        ("photo", True, "ok"),
        ("facture", False, "echec"),  # en_attente : jamais lisible
    ]


def test_deux_reapers_ne_prennent_jamais_la_meme_demande(base: Any) -> None:
    snapshots = SnapshotsPostgres(base)
    references = [f"KAL-26-{i:04d}" for i in range(20)]
    for reference in references:
        snapshots.debuter(EtatDemande(demande={"reference": reference}))
    with base.connection() as conn:  # mortes depuis une heure ; une fauchée a maj = now()
        conn.execute("UPDATE demandes SET maj = now() - interval '1 hour'")
    with ThreadPoolExecutor(2) as pool:
        lots = list(pool.map(lambda _: faucher(snapshots, 60), range(2)))
    fauchees = [fiche["reference"] for lot in lots for fiche in lot]
    assert sorted(fauchees) == references  # chacune exactement une fois


def test_un_seul_appel_partenaire_sous_concurrence(base: Any) -> None:
    SnapshotsPostgres(base).debuter(EtatDemande(demande={"reference": "KAL-26-0042"}))
    registre = RegistreA2APostgres(base)
    with ThreadPoolExecutor(8) as pool:
        reserves = list(pool.map(lambda _: registre.reserver("KAL-26-0042"), range(8)))
    assert reserves.count(True) == 1


def test_traiter_demande_avec_base(base: Any) -> None:
    demande = copy.deepcopy(NOM_01["demandes"][0])
    fiche = Orchestrateur(snapshots=SnapshotsPostgres(base)).traiter(demande)
    with base.connection() as conn:
        statut, etat_courant, decision, trace = conn.execute(
            "SELECT statut, etat_courant, fiche->>'decision', jsonb_array_length(etat->'trace') "
            "FROM demandes WHERE reference = %s",
            (demande["reference"],),
        ).fetchone()
    assert (statut, etat_courant, decision) == ("terminee", "acceptee", fiche["decision"])
    assert trace == len(fiche["trace"])


def test_reaper_classe_la_fiche_en_base(base: Any) -> None:
    snapshots = SnapshotsPostgres(base)
    snapshots.debuter(EtatDemande(demande={"reference": "KAL-26-9002"}))
    (fiche,) = faucher(snapshots, 0)
    with base.connection() as conn:
        statut, fichier = conn.execute(
            "SELECT statut, fiche->>'file' FROM demandes WHERE reference = 'KAL-26-9002'"
        ).fetchone()
    assert (statut, fichier) == ("secours", fiche["file"])


AF_01 = next(
    json.loads(ligne)
    for ligne in (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()
    if json.loads(ligne)["id"] == "AF-01"
)


def test_registre_postgres_un_seul_appel_entre_deux_orchestrateurs(
    base: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le registre survit à l'orchestrateur (et au processus) : aucun second appel (EX-D19)."""
    envois: list[str] = []

    def post(url: str, *, json: Any, headers: Any, timeout: Any) -> httpx.Response:
        reference = json["params"]["message"]["parts"][0]["data"]["reference_dossier"]
        envois.append(reference)
        evaluation = {
            "reference_dossier": reference,
            "score": 0.08,
            "niveau": "faible",
            "indicateurs": [],
            "evaluation_id": "EVA-integration",
            "version_modele": "af-2.3.1",
        }
        corps = {
            "jsonrpc": "2.0",
            "id": json["id"],
            "result": {
                "kind": "task",
                "id": "tsk-1",
                "status": {"state": "completed"},
                "artifacts": [{"artifactId": "a", "parts": [{"kind": "data", "data": evaluation}]}],
            },
        }
        return httpx.Response(200, json=corps)

    def get(url: str, *, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("pas de carte")  # /a2a en secours

    monkeypatch.setattr(partenaire.httpx, "post", post)
    monkeypatch.setattr(partenaire.httpx, "get", get)
    monkeypatch.setenv("PARTENAIRE_JETON", "jeton-de-test")

    def traiter() -> dict[str, Any]:
        return Orchestrateur(
            partenaire_url="http://partenaire:8100",
            snapshots=SnapshotsPostgres(base),
            registre=RegistreA2APostgres(base),
        ).traiter(copy.deepcopy(AF_01["demandes"][0]))

    premiere, seconde = traiter(), traiter()
    assert envois == ["KAL-26-0201"]
    assert premiere["avis_fraude"]["evaluation_id"] == "EVA-integration"
    assert seconde["avis_fraude"] is None and seconde["mode_degrade"] is True
    (etape,) = [e for e in seconde["trace"] if e["agent"] == "antifraude"]
    assert etape["motif"] == "registre : dossier déjà soumis"
    with base.connection() as conn:
        (evaluation_id,) = conn.execute(
            "SELECT evaluation_id FROM appels_partenaire WHERE reference = 'KAL-26-0201'"
        ).fetchone()
    assert evaluation_id == "EVA-integration"
