"""Kaldera — traitement des demandes de remboursement d'assurance."""

from __future__ import annotations

from typing import Any

from .etat import BORNES
from .orchestrateur import Orchestrateur

__all__ = ["bornes", "traiter_demande", "traiter_lot"]


def bornes() -> dict[str, Any]:
    """Bornes d'exécution en vigueur."""
    return BORNES.model_dump()


def traiter_demande(
    demande: dict[str, Any], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite une demande et retourne sa fiche de décision."""
    return Orchestrateur(partenaire_url).traiter(demande)


def traiter_lot(
    demandes: list[dict[str, Any]], *, partenaire_url: str | None = None
) -> dict[str, Any]:
    """Traite un lot de demandes ; retourne les fiches (dans l'ordre) et les métriques par agent."""
    # ponytail: séquentiel ; paralléliser (§12) si une mesure montre un lot trop lent
    fiches = [traiter_demande(d, partenaire_url=partenaire_url) for d in demandes]
    return {"fiches": fiches, "metriques": _metriques_par_agent(fiches)}


def _metriques_par_agent(fiches: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metriques: dict[str, dict[str, Any]] = {}
    for etape in (e for f in fiches for e in f["trace"]):
        m = metriques.setdefault(
            etape["agent"], {"appels": 0, "echecs": 0, "duree_ms": 0.0, "appels_externes": 0}
        )
        m["appels"] += 1
        m["echecs"] += int(etape["statut"] == "echec")
        m["duree_ms"] += etape["duree_ms"]
        m["appels_externes"] += etape["appels_externes"]
    for m in metriques.values():
        m["latence_ms"] = round(m.pop("duree_ms") / m["appels"], 2)
    return metriques
