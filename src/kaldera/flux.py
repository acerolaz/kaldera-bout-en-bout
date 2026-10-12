"""Flux SSE du back-office (spec C3-3 §3.4) : LISTEN PostgreSQL → événements filtrés, prêts
à afficher. Asynchrone de bout en bout : aucune E/S bloquante dans la boucle d'événements."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing

import psycopg

from .postgres import CANAL
from .vue_gestionnaire import evenement

PING_S = 15.0  # battement : garde la connexion ouverte à travers proxys et navigateurs


async def ecouter(conninfo: str, ping_s: float = PING_S) -> AsyncGenerator[str | None]:
    """Charges utiles du canal d'avancement ; ``None`` à chaque fenêtre de ``ping_s`` secondes."""
    # ponytail: une connexion par client SSE (usage local) ; un écouteur partagé si plusieurs
    # gestionnaires suivent des lots en même temps
    async with await psycopg.AsyncConnection.connect(
        conninfo, autocommit=True, connect_timeout=2
    ) as conn:
        await conn.execute(f"LISTEN {CANAL}")  # CANAL : constante du module, jamais une donnée
        while True:
            async for notification in conn.notifies(timeout=ping_s):
                yield notification.payload
            yield None


async def diffuser(
    charges: AsyncGenerator[str | None], references: frozenset[str]
) -> AsyncIterator[str]:
    """Messages SSE des seuls dossiers suivis ; un signal illisible est ignoré."""
    yield ": ouvert\n\n"  # premier octet tout de suite : EventSource passe à « open »
    async with aclosing(charges):  # déconnexion du client : LISTEN fermé sans attendre le GC
        async for charge in charges:
            if charge is None:
                yield ": ping\n\n"
                continue
            try:
                brut = json.loads(charge)
            except json.JSONDecodeError:
                continue
            vue = evenement(brut) if isinstance(brut, dict) else None
            if vue is not None and vue.reference in references:
                yield f"event: avancement\ndata: {vue.model_dump_json()}\n\n"
