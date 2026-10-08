"""Unitaires — seed : une API injoignable donne un message, pas une trace Python."""

from __future__ import annotations

import pytest

from tools import seed


def test_api_injoignable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KALDERA_API_URL", "http://127.0.0.1:9")
    monkeypatch.setattr("sys.argv", ["seed"])
    with pytest.raises(SystemExit, match="seed en échec : API injoignable"):
        seed.main()
