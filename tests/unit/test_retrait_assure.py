"""Unitaires — l'espace assuré (UI1) est retiré : plus de route /assure, plus d'agent de relance."""

from __future__ import annotations

import pytest

from kaldera.api import app
from kaldera.llm import ConfigAgents


def test_aucune_route_assure_les_routes_de_depot_restent() -> None:
    chemins = {getattr(route, "path", "") for route in app.routes}
    assert not any(chemin.startswith("/assure") for chemin in chemins)
    assert {"/demandes", "/demandes/{reference}/pieces", "/demandes/{reference}"} <= chemins


def test_aucun_role_llm_relance() -> None:
    assert "relance" not in ConfigAgents.model_fields


def test_un_ancien_env_avec_relance_et_session_ne_bloque_pas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KALDERA_RELANCE__MODELE", "Kimi-K2.6")
    monkeypatch.setenv("KALDERA_SESSION_SECRET", "ancien")
    config = ConfigAgents(_env_file=None)
    assert not hasattr(config, "relance")
