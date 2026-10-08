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
