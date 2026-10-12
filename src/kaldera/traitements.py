"""Traitement lancé par le gestionnaire (spec C3-3 §2.2) : un lot, un orchestrateur câblé sur
PostgreSQL (snapshots, pièces, signaux). Appelé en tâche de fond par ``POST /traitements``."""

from __future__ import annotations

from typing import Any

from psycopg_pool import ConnectionPool

from . import traiter_lot
from .orchestrateur import Orchestrateur
from .postgres import DepotPostgres, SignauxPostgres, SnapshotsPostgres


def orchestrateur(connexions: ConnectionPool) -> Orchestrateur:
    # ponytail: un disjoncteur par lot (un orchestrateur par lot) ; un disjoncteur de processus
    # si les pannes LLM doivent être retenues d'un lot à l'autre
    return Orchestrateur(
        depot=DepotPostgres(connexions),
        snapshots=SnapshotsPostgres(connexions),
        signaux=SignauxPostgres(connexions),
    )


def traiter(connexions: ConnectionPool, demandes: list[dict[str, Any]]) -> None:
    """Traite le lot ; chaque dossier a son filet, le reaper couvre un arrêt brutal de l'API."""
    traiter_lot(demandes, orchestrateur=orchestrateur(connexions))
