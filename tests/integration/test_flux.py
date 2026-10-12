"""Intégration — LISTEN : un pg_notify émis par SignauxPostgres arrive au flux (spec §3.4)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kaldera.flux import ecouter
from kaldera.postgres import SignauxPostgres

pytestmark = pytest.mark.integration


def test_ecouter_recoit_un_signal(base: Any) -> None:
    async def scenario() -> str | None:
        flux = ecouter(base.conninfo, ping_s=0.2)
        assert await anext(flux) is None  # premier battement : LISTEN est en place
        SignauxPostgres(base).emettre({"type": "dossier_fin", "reference": "KAL-26-9001"})
        charge = await anext(flux)
        while charge is None:  # un battement peut précéder la notification
            charge = await anext(flux)
        await flux.aclose()
        return charge

    charge = asyncio.run(scenario())
    assert charge is not None and json.loads(charge) == {
        "type": "dossier_fin", "reference": "KAL-26-9001"
    }


def test_flux_inconnus_404(client: TestClient) -> None:
    assert client.get("/flux/demandes/KAL-26-9999").status_code == 404
    assert client.get("/flux/lots/999").status_code == 404
