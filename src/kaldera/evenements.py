"""Événements de l'espace assuré (UI1) : contenu déjà projeté par ``vue_assure``, relu par le SSE.

Rien d'interne n'entre dans ``evenements_assure`` : une vue (``etape``, ``piece``, ``verdict``) ou
un message de chat. La colonne ``etape`` horodate la première atteinte de chaque étape.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from .assure_postgres import DepotAssure
from .vue_assure import MessageChat, VueDemande, construire

TypeVue = Literal["etape", "piece", "verdict"]


def publier_vue(
    depot: DepotAssure,
    reference: str,
    type_: TypeVue,
    delai_analyse_s: float,
    etape: int | None = None,
) -> VueDemande | None:
    donnees = depot.donnees(reference)
    if donnees is None:
        return None
    vue = construire(donnees, delai_analyse_s)
    depot.inserer_evenement(reference, type_, etape or vue.etape, vue.model_dump(mode="json"))
    return vue


def publier_message(
    depot: DepotAssure,
    reference: str,
    auteur: Literal["assure", "agent"],
    texte: str,
    actions: Sequence[Literal["deposer"]] = (),
) -> int:
    message = MessageChat(auteur=auteur, texte=texte, actions=list(actions))
    return depot.inserer_evenement(reference, "message", None, message.model_dump(mode="json"))
