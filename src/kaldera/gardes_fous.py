"""Garde-fous de sortie des agents LLM (dossier 1.4 bis, EX-D31).

Le patch du LLM est comparé à la référence déterministe (le repli) : les champs
décisifs doivent être identiques, le champ rédigé doit être utile et sans donnée
sensible. Chaque fonction renvoie la liste des violations (vide = sortie acceptée).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

Controle = Callable[[str | None, dict[str, Any]], list[str]]

MOTIFS_SENSIBLES = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,}"),
    "telephone": re.compile(r"(?:\+33\s?|\b0)[1-9](?:[ .]?\d{2}){4}\b"),
}


def champs_differents(patch: dict[str, Any], ref: dict[str, Any], ignores: set[str]) -> list[str]:
    return [champ for champ in ref if champ not in ignores and patch.get(champ) != ref[champ]]


def donnees_sensibles(texte: str | None, vue: dict[str, Any]) -> list[str]:
    if not texte:
        return []
    trouvees, reste = [], texte
    for nom, motif in MOTIFS_SENSIBLES.items():  # l'IBAN est retiré avant de chercher un téléphone
        if motif.search(reste):
            trouvees.append(nom)
            reste = motif.sub(" ", reste)
    assure = vue.get("demande", {}).get("assure", {})
    identite = [assure.get(c) for c in ("nom", "prenom") if len(assure.get(c) or "") >= 3]
    # sur le reste : le nom dans une adresse e-mail est déjà signalé comme « email »
    if any(re.search(rf"\b{re.escape(i)}\b", reste, re.IGNORECASE) for i in identite if i):
        trouvees.append("identite")
    return trouvees


def _compact(texte: str) -> str:
    return re.sub(r"[\s  ]", "", texte).replace(",", ".")


def _nombre(valeur: float) -> str:
    return str(int(valeur)) if valeur == int(valeur) else f"{valeur:.2f}"


def controle_pieces(texte: str | None, ref: dict[str, Any]) -> list[str]:
    if ref["statut"] == "incomplet":
        return [] if texte else ["message_relance vide"]
    return ["relance sans pièce à relancer"] if texte else []


def controle_estimation(texte: str | None, ref: dict[str, Any]) -> list[str]:
    if not texte:
        return ["explication vide"]
    compact = _compact(texte)
    return [
        f"explication sans {libelle}"
        for libelle, champ in (("la franchise", "franchise"), ("le plafond", "plafond"))
        if _nombre(ref[champ]) not in compact
    ]


def controle_antifraude(texte: str | None, ref: dict[str, Any]) -> list[str]:
    if not texte:
        return ["note vide"]
    return ["note avec réponse brute"] if "{" in texte else []


def controle_decision(texte: str | None, ref: dict[str, Any]) -> list[str]:
    if not texte:
        return ["motif vide"]
    regle = re.split(r"\s*[:—(]", ref["motif"], maxsplit=1)[0].strip()
    return [] if regle.lower() in texte.lower() else [f"motif sans la règle « {regle} »"]


def verifier_sortie(
    patch: dict[str, Any],
    ref: dict[str, Any],
    vue: dict[str, Any],
    champ: str,
    prives: tuple[str, ...],
    controle: Controle,
) -> list[str]:
    texte = patch.get(champ)
    return (
        [f"champ décisif modifié : {c}" for c in champs_differents(patch, ref, {champ, *prives})]
        + [f"donnée sensible : {d}" for d in donnees_sensibles(texte, vue)]
        + controle(texte, ref)
    )
