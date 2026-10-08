"""Unitaires — base configurée mais injoignable : jamais bloquant (EX-01)."""

from __future__ import annotations

import pytest

from kaldera.postgres import snapshots_par_defaut  # avant le patch autouse du conftest


def test_sans_url_aucune_persistance() -> None:
    assert snapshots_par_defaut() is None


def test_base_injoignable_traitement_sans_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KALDERA_DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    assert snapshots_par_defaut() is None
