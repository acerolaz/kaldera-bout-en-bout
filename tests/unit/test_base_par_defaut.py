"""Unitaires — base configurée mais injoignable : jamais bloquant (EX-01)."""

from __future__ import annotations

from pathlib import Path

import pytest

# avant le patch autouse du conftest
from kaldera.ports import ErreurPersistance
from kaldera.postgres import RegistreA2APostgres, registre_par_defaut, snapshots_par_defaut


def test_sans_url_aucune_persistance() -> None:
    assert snapshots_par_defaut() is None


def test_base_injoignable_traitement_sans_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KALDERA_DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    assert snapshots_par_defaut() is None


def test_sans_url_aucun_registre_persistant(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # aucun .env local lu
    assert registre_par_defaut() is None


def test_base_injoignable_registre_postgres_en_panne(monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec §1 : base configurée ⇒ registre Postgres, même en panne (jamais la mémoire)."""
    monkeypatch.setenv("KALDERA_DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    registre = registre_par_defaut()
    assert isinstance(registre, RegistreA2APostgres)
    with pytest.raises(ErreurPersistance):
        registre.reserver("KAL-26-0201")


def test_base_injoignable_n_est_pas_reessayee_a_chaque_demande(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kaldera import postgres

    essais = []

    def pool_injoignable(url: str) -> None:
        essais.append(url)
        raise postgres.psycopg.OperationalError("connexion refusée")

    monkeypatch.setattr(postgres, "pool", pool_injoignable)
    monkeypatch.setattr(postgres, "_ECHECS", {})
    monkeypatch.setenv("KALDERA_DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    assert snapshots_par_defaut() is None and snapshots_par_defaut() is None
    assert len(essais) == 1
