"""Machine à états d'une demande : la table de transitions, seule source de vérité du flux.

Les gardes sont des fonctions pures : elles lisent l'état de la demande et les bornes,
ne le modifient jamais. La garde globale (TG) n'est pas dans la table : le moteur
l'évalue avant chaque action (voir ``orchestrateur``).
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any


class Etat(str, Enum):
    ELIGIBILITE = "eligibilite"
    PIECES = "pieces"
    ESTIMATION = "estimation"
    ANTIFRAUDE = "antifraude"
    DECISION = "decision"
    ACCEPTEE = "acceptee"  # terminal
    REFUSEE = "refusee"  # terminal
    ESCALADE = "escalade"  # terminal


TERMINAUX = frozenset({Etat.ACCEPTEE, Etat.REFUSEE, Etat.ESCALADE})

# Une garde lit l'état de la demande (EtatDemande) et les bornes (Bornes) : oui / non
Garde = Callable[[Any, Any], bool]


def TOUJOURS(e: Any, b: Any) -> bool:  # noqa: N802 — garde « sinon », lue comme une constante
    return True


# (état de départ, garde, état suivant) : évaluées DANS L'ORDRE, la première garde vraie gagne
TRANSITIONS: list[tuple[Etat, Garde, Etat]] = [
    (Etat.ELIGIBILITE, lambda e, b: not e.eligibilite.eligible, Etat.DECISION),  # T1
    (Etat.ELIGIBILITE, TOUJOURS, Etat.PIECES),  # T2
    (Etat.PIECES, lambda e, b: e.pieces.statut == "complet", Etat.ESTIMATION),  # T3
    (
        Etat.PIECES,
        lambda e, b: e.pieces.statut == "incomplet"
        and e.compteurs.relances < b.relances_pieces_max,
        Etat.PIECES,
    ),  # T4
    (Etat.PIECES, TOUJOURS, Etat.DECISION),  # T5
    (Etat.ESTIMATION, lambda e, b: e.estimation.estime == 0, Etat.DECISION),  # T6
    (Etat.ESTIMATION, TOUJOURS, Etat.ANTIFRAUDE),  # T7
    (Etat.ANTIFRAUDE, TOUJOURS, Etat.DECISION),  # T8
    (Etat.DECISION, lambda e, b: e.issue.decision == "acceptee", Etat.ACCEPTEE),  # T9
    (Etat.DECISION, lambda e, b: e.issue.decision == "refusee", Etat.REFUSEE),  # T10
    (Etat.DECISION, TOUJOURS, Etat.ESCALADE),  # T11
]


class TransitionInconnue(Exception):
    """Aucune garde vraie pour l'état courant : la table est incomplète."""


def transition(courant: Etat, etat: Any, bornes: Any) -> tuple[Etat, str]:
    """Retourne l'état suivant et le numéro de la transition empruntée (« T1 »…)."""
    for numero, (depart, garde, suivant) in enumerate(TRANSITIONS, start=1):
        if depart == courant and garde(etat, bornes):
            return suivant, f"T{numero}"
    raise TransitionInconnue(courant)


def peut_atteindre(depart: Etat, cibles: set[Etat] | frozenset[Etat]) -> bool:
    """Parcours en largeur de la table : existe-t-il un chemin de depart vers une cible ?"""
    vus, file = {depart}, [depart]
    while file:
        e = file.pop(0)
        if e in cibles:
            return True
        for d, _, s in TRANSITIONS:
            if d == e and s not in vus:
                vus.add(s)
                file.append(s)
    return False
