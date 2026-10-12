"""Helpers d'intégration : la partie JSON d'une demande de scénario."""

from __future__ import annotations

import copy
from typing import Any


def json_demande(demande: dict[str, Any]) -> dict[str, Any]:
    """Partie JSON d'une demande de scénario : ni pièces, ni dépôts, ni termes du contrat."""
    d = copy.deepcopy(demande)
    d.pop("pieces", None)
    d.pop("espace_assure", None)
    d["contrat"] = {k: d["contrat"][k] for k in ("numero", "statut", "cotisations_a_jour")}
    return d


def lancer_pretes(connexions: Any) -> None:
    """Lance, comme le gestionnaire, toutes les demandes prêtes (un lot, traité tout de suite)."""
    from kaldera import traitements
    from kaldera.lots_postgres import DepotLots

    with connexions.connection() as conn:
        pretes = [
            r
            for (r,) in conn.execute(
                "SELECT reference FROM demandes WHERE statut = 'prete' ORDER BY reference"
            )
        ]
    if pretes:
        _, demandes = DepotLots(connexions).lancer(pretes)
        traitements.traiter(connexions, demandes)
