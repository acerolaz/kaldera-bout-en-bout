"""Isolation : aucun test ne parle à un vrai LLM, même si `make test` exporte le .env."""

from __future__ import annotations

import os

import pytest

from kaldera import llm


@pytest.fixture(autouse=True)
def _sans_llm_reel(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in [v for v in os.environ if v.startswith(("KALDERA_", "AZURE_AI_"))]:
        monkeypatch.delenv(variable)
    monkeypatch.setattr(llm, "charger_config", lambda: llm.ConfigAgents(_env_file=None))
