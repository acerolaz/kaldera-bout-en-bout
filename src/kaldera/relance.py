"""Agent de relance (UI1, spec §5) : explique les pièces à fournir, rien d'autre.

Le code calcule les faits (pièces attendues, intention de la question) ; le LLM ne rédige que
``texte`` ; le garde-fou le vérifie ; à défaut, le gabarit répond. Mécanique d'``AgentLLM`` :
référence d'abord, boucle bornée, champs décisifs identiques à la référence, repli tracé.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from . import llm
from .agents_llm import AgentLLM, Outil, SpecAgent
from .etat import BORNES
from .vue_assure import LIBELLES_PIECES, PieceAttendue

Intention = Literal["liste", "rejet", "conseiller"]
TEXTE_MAX = 600
# ni argent, ni issue, ni contrôle, ni service externe, ni mécanique interne (spec §5)
TERMES_INTERDITS = re.compile(
    r"fraud|partenaire|score|repli|indicateur|suspic|soup[çc]on|rembours|indemni|accept|refus"
    r"|d[ée]cision|montant|€|euro|contr[ôo]le|gestionnaire|agent"
    r"|\bEUR\b|\d\s*(?:€|eur)|vir(?:e)?ment|pai(?:e|ement)|pay[ée]|vers[ée]|approuv|couvert"
    r"|prise? en charge|estimation|escalad|cellule|d[ée]grad|[ée]tat interne",
    re.IGNORECASE,
)
MOTS_PIECES = {
    "facture": re.compile(r"factur", re.IGNORECASE),
    "photo": re.compile(r"photo", re.IGNORECASE),
    "depot_plainte": re.compile(r"plainte|r[ée]c[ée]piss", re.IGNORECASE),
}
CONSIGNE_DEPOT = (
    "Glisser le fichier dans la zone de dépôt, ou le choisir ; formats PDF, PNG ou JPEG, "
    "10 Mo au plus ; un document par fichier."
)
COMPLET = "Toutes les pièces attendues sont là. Vous pouvez soumettre votre dossier."


class ReponseRelance(BaseModel):
    intention: Intention
    pieces_citees: list[str]
    texte: str | None = None


def intention(question: str, pieces: list[PieceAttendue]) -> Intention:
    q = question.lower()
    a_refaire = any(p.statut == "a_refaire" for p in pieces)
    if a_refaire and re.search(r"pourquoi|refus|rejet|illisible|probl|erreur|pas accept", q):
        return "rejet"
    if re.search(
        r"pi[eè]ce|document|justificatif|factur|photo|plainte|r[ée]c[ée]piss|d[ée]pos|fournir"
        r"|envoy|manqu|besoin|suffi",
        q,
    ):
        return "liste"
    return "conseiller"


def _concernees(intention: Intention, pieces: list[PieceAttendue]) -> list[str]:
    if intention == "rejet":
        return [p.type for p in pieces if p.statut == "a_refaire"]
    if intention == "liste":
        return [p.type for p in pieces if p.statut in ("a_fournir", "a_refaire")]
    return []


def _libelles(types: list[str]) -> str:
    return ", ".join(LIBELLES_PIECES[t].lower() for t in types)


def gabarit(ref: dict[str, Any]) -> str:
    citees = ref["pieces_citees"]
    if ref["intention"] == "rejet":
        return (
            f"Ce document n'a pas pu être lu ou ne correspond pas au type indiqué : "
            f"{_libelles(citees)}. Déposez une version nette et complète, par exemple un scan "
            "bien lisible ou le fichier d'origine."
        )
    if ref["intention"] == "liste":
        if not citees:
            return COMPLET
        return f"Il nous reste à recevoir : {_libelles(citees)}. Vous pouvez les déposer ici."
    return (
        "Je peux seulement vous aider sur les pièces de votre dossier. Pour toute autre question, "
        "un conseiller vous répondra."
    )


def controle_relance(texte: str | None, ref: dict[str, Any]) -> list[str]:
    if not texte:
        return ["texte vide"]
    violations = []
    if len(texte) > TEXTE_MAX:
        violations.append("texte trop long")
    if TERMES_INTERDITS.search(texte):
        violations.append("terme interdit")
    for type_piece, motif in MOTS_PIECES.items():
        if motif.search(texte) and type_piece not in ref["pieces_citees"]:
            violations.append(f"pièce non concernée : {type_piece}")
    return violations


def _pieces(vue: dict[str, Any]) -> list[PieceAttendue]:
    return [PieceAttendue.model_validate(p) for p in vue["pieces"]]


def _repli(vue: dict[str, Any]) -> dict[str, Any]:
    pieces = _pieces(vue)
    choix = intention(vue["question"], pieces)
    return {"relance": {"intention": choix, "pieces_citees": _concernees(choix, pieces)}}


def _outils(vue: dict[str, Any], ref: dict[str, Any]) -> list[Outil]:
    return [  # le premier fait foi (les LLM fidèles le recopient)
        Outil(
            "reference_relance",
            "Intention de la question et pièces concernées (fait foi).",
            lambda a: {k: ref[k] for k in ("intention", "pieces_citees")},
        ),
        Outil("liste_pieces", "Pièces attendues et leur statut.", lambda a: vue["pieces"]),
        Outil("consigne_depot", "Comment déposer une pièce.", lambda a: CONSIGNE_DEPOT),
    ]


SPEC = SpecAgent(
    "relance", ReponseRelance, "texte", gabarit, _outils, controle_relance, lambda b, e: _repli
)


def agent_relance(client: llm.ClientLLM | None, config: llm.ConfigLLM | None) -> AgentLLM:
    return AgentLLM(
        "relance", SPEC, _repli, client, config or llm.ConfigLLM(modele="aucun"), BORNES
    )


def repondre(
    question: str, pieces: list[PieceAttendue], assure: dict[str, Any], agent: AgentLLM
) -> str:
    """Réponse vérifiée (ou gabarit) ; l'identité de l'assuré sert au seul contrôle de fuite."""
    # la question est une donnée non fiable : elle ne doit pas pouvoir fermer la balise qui l'isole
    question = question.replace("<", "‹").replace(">", "›")
    vue = {
        "question": question,
        "pieces": [p.model_dump() for p in pieces],
        "demande": {"assure": assure},
    }
    patch, _ = agent.executer(vue, agent.config.delai_agent_s)
    return str(patch["relance"]["texte"])


def message_spontane(type_analyse: str, pieces: list[PieceAttendue]) -> str | None:
    """Gabarit publié par le worker après une analyse (sans LLM) : à refaire, ou dossier complet."""
    analysee = next((p for p in pieces if p.type == type_analyse), None)
    if analysee is not None and analysee.statut == "a_refaire":
        return gabarit({"intention": "rejet", "pieces_citees": [type_analyse]})
    if pieces and all(p.statut == "validee" for p in pieces):
        return COMPLET
    return None
