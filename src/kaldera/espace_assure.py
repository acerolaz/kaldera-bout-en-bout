"""Espace assuré en ligne (simulation).

Les dépôts qu'un assuré effectue en réponse aux demandes de complément figurent dans
``demande["espace_assure"]["depots"]``, dans l'ordre où il les effectue. Comme sur le
portail réel, un assuré qui n'a rien de nouveau à transmettre re-soumet son dernier
dépôt pour le type de pièce demandé.
"""

from __future__ import annotations

from typing import Any


def demander_piece(
    demande: dict[str, Any], type_piece: str, tentative: int
) -> dict[str, Any] | None:
    """Demande une pièce à l'assuré et retourne son dépôt.

    ``tentative`` est le numéro de la demande de complément pour ce type de pièce
    (0 pour la première). Retourne ``None`` si l'assuré n'a jamais rien déposé de ce type.
    """
    depots = [
        piece
        for piece in demande.get("espace_assure", {}).get("depots", [])
        if piece.get("type") == type_piece
    ]
    if not depots:
        return None
    return dict(depots[min(tentative, len(depots) - 1)])


def depot_pour(
    depots: list[dict[str, Any]], type_piece: str, tentative: int
) -> dict[str, Any] | None:
    """Dépôt n°``tentative`` (0 = première relance) de ce type ; l'assuré re-soumet le dernier."""
    du_type = [piece for piece in depots if piece.get("type") == type_piece]
    if not du_type:
        return None
    return dict(du_type[min(tentative, len(du_type) - 1)])
