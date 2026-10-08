"""Adaptateurs sans base : niveau 0 (demande JSON) et tests."""

from __future__ import annotations

from typing import Any

from .ports import PieceRef


class DepotDepuisDemande:
    """Niveau 0 : ``pieces`` et ``espace_assure.depots`` de la demande (§3)."""

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]:
        return [PieceRef.model_validate(p) for p in demande.get("pieces", [])]

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]:
        depots = demande.get("espace_assure", {}).get("depots", [])
        return [PieceRef.model_validate(p) for p in depots]
