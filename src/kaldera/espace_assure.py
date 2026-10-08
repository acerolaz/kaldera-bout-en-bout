"""Espace assuré en ligne (simulation).

Les dépôts qu'un assuré effectue en réponse aux demandes de complément sont lus par le port
``DepotPieces``, dans l'ordre où il les effectue. Comme sur le portail réel, un assuré qui n'a
rien de nouveau à transmettre re-soumet son dernier dépôt pour le type de pièce demandé.
"""

from __future__ import annotations

from typing import Any


def depot_pour(
    depots: list[dict[str, Any]], type_piece: str, tentative: int
) -> dict[str, Any] | None:
    """Dépôt n°``tentative`` (0 = première relance) de ce type ; l'assuré re-soumet le dernier."""
    du_type = [piece for piece in depots if piece.get("type") == type_piece]
    if not du_type:
        return None
    return dict(du_type[min(tentative, len(du_type) - 1)])
