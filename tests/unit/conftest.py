"""Unitaires : la carte du partenaire par défaut n'est jamais lue sur le réseau."""

from __future__ import annotations

import pytest

from kaldera import partenaire


@pytest.fixture(autouse=True)
def _carte_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """``Orchestrateur()`` sans ``evaluer`` lirait l'Agent Card sur ``localhost:8100``."""
    monkeypatch.delenv("PARTENAIRE_URL", raising=False)
    base = partenaire.URL_PAR_DEFAUT
    monkeypatch.setitem(partenaire._CARTES, base, f"{base}/a2a")
