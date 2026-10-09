"""Événements de l'espace assuré (UI1) : contenu déjà projeté par ``vue_assure``, relu par le SSE.

Rien d'interne n'entre dans ``evenements_assure`` : une vue (``etape``, ``piece``, ``verdict``) ou
un message de chat. La colonne ``etape`` horodate la première atteinte de chaque étape.

Les événements sont au mieux : une publication en échec est journalisée et renvoie ``None``, elle ne
change jamais l'issue d'une demande (EX-01 : la base ne bloque jamais une décision).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal

from pydantic import ValidationError

from .assure_postgres import DepotAssure
from .ports import ErreurPersistance
from .vue_assure import MessageChat, VueDemande, construire

LOGGER = logging.getLogger(__name__)
ECHECS = (ErreurPersistance, KeyError, ValidationError)
TypeVue = Literal["etape", "piece", "verdict"]


def publier_vue(
    depot: DepotAssure,
    reference: str,
    type_: TypeVue,
    delai_analyse_s: float,
    etape: int | None = None,
) -> VueDemande | None:
    try:
        donnees = depot.donnees(reference)
        if donnees is None:
            return None
        vue = construire(donnees, delai_analyse_s)
        depot.inserer_evenement(reference, type_, etape or vue.etape, vue.model_dump(mode="json"))
    except ECHECS as exc:
        LOGGER.warning("événement %s non publié, demande %s : %s", type_, reference, _nom(exc))
        return None
    return vue


def publier_message(
    depot: DepotAssure,
    reference: str,
    auteur: Literal["assure", "agent"],
    texte: str,
    actions: Sequence[Literal["deposer"]] = (),
) -> int | None:
    try:
        message = MessageChat(auteur=auteur, texte=texte, actions=list(actions))
        return depot.inserer_evenement(reference, "message", None, message.model_dump(mode="json"))
    except ECHECS as exc:
        LOGGER.warning("message non publié, demande %s : %s", reference, _nom(exc))
        return None


def _nom(exc: Exception) -> str:
    return type(exc).__name__
