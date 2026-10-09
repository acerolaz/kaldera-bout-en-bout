"""Unitaires — le serveur e2e refuse de démarrer sans base de test (il la vide)."""

from __future__ import annotations

import pytest

from tests.e2e import serveur


@pytest.mark.parametrize(
    "valeur",
    [
        None,
        "",
    ],
)
def test_refuse_de_demarrer_sans_base_de_test(
    monkeypatch: pytest.MonkeyPatch, valeur: str | None
) -> None:
    if valeur is None:
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("TEST_DATABASE_URL", valeur)

    def interdit(*_: object, **__: object) -> None:
        raise AssertionError("aucune connexion ne doit être ouverte")

    monkeypatch.setattr("kaldera.postgres.pool", interdit)
    with pytest.raises(SystemExit, match="TEST_DATABASE_URL absente"):
        serveur.main()
