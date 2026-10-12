"""Unitaires — diffusion SSE : filtre par dossier, traduction, battement (spec C3-3 §3.4)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from kaldera.flux import diffuser


async def _charges(*charges: str | None) -> AsyncIterator[str | None]:
    for charge in charges:
        yield charge


def _tout(charges: AsyncIterator[str | None], references: frozenset[str]) -> list[str]:
    async def lire() -> list[str]:
        return [morceau async for morceau in diffuser(charges, references)]

    return asyncio.run(lire())


def test_diffuser_filtre_et_traduit() -> None:
    a = {"type": "sous_etape", "reference": "A", "etat": "pieces", "sous_etape": "vue",
         "tour": 0, "tours_max": 3}
    b = {**a, "reference": "B"}
    sorties = _tout(
        _charges(json.dumps(a), json.dumps(b), None, "pas du json", json.dumps({"type": "x"})),
        frozenset({"A"}),
    )
    assert sorties[0] == ": ouvert\n\n"
    assert sorties[1].startswith("event: avancement\ndata: ")
    donnees = json.loads(sorties[1].split("data: ", 1)[1])
    assert donnees == {"type": "sous_etape", "reference": "A", "etat": "pieces",
                       "statut": "en_cours", "avancement_agent": 17}
    assert sorties[2:] == [": ping\n\n"]  # B filtré, JSON cassé et type inconnu ignorés


def test_diffuser_ferme_les_charges_a_la_deconnexion() -> None:
    fermee: list[bool] = []

    async def charges() -> AsyncIterator[str | None]:
        try:
            while True:
                yield None
        finally:
            fermee.append(True)

    async def scenario() -> None:
        flux = diffuser(charges(), frozenset({"A"}))
        await anext(flux)  # « ouvert »
        await anext(flux)  # « ping » : la boucle est en cours
        await flux.aclose()

    asyncio.run(scenario())
    assert fermee == [True]
