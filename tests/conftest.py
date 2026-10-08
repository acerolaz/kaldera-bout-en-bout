"""Isolation : aucun test ne parle à un vrai LLM, même si `make test` exporte le .env."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

from kaldera import llm


@pytest.fixture(autouse=True)
def _sans_llm_reel(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in [v for v in os.environ if v.startswith(("KALDERA_", "AZURE_AI_"))]:
        monkeypatch.delenv(variable)
    monkeypatch.setattr(llm, "charger_config", lambda: llm.ConfigAgents(_env_file=None))


@pytest.fixture
def base() -> Iterator[Any]:
    """Pool PostgreSQL de test, tables vidées (TRUNCATE : la concurrence exige des commits)."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL absente : make test-integration")
    from kaldera.postgres import pool

    connexions = pool(url)
    with connexions.connection() as conn:
        conn.execute(
            "TRUNCATE appels_partenaire, pieces, file_ingestion, analyses, demandes, contrats, blobs"
        )
    yield connexions
