"""Adaptateurs PostgreSQL (dossier 2.6) : psycopg 3 synchrone, SQL brut, migrations versionnées.

Toute ``psycopg.Error`` devient ``ErreurPersistance`` : le domaine ne voit jamais le pilote.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources

import psycopg
from psycopg_pool import ConnectionPool
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .ports import ErreurPersistance

LOGGER = logging.getLogger(__name__)
VERROU_MIGRATIONS = 20261008  # pg_advisory_lock : un seul processus migre à la fois


class ConfigBase(BaseSettings):
    """``KALDERA_DATABASE_URL`` absente ⇒ aucune persistance."""

    model_config = SettingsConfigDict(env_prefix="KALDERA_", env_file=".env", extra="ignore")

    database_url: str | None = None
    reaper_age_s: float = Field(default=30, gt=0)


def appliquer_migrations(conn: psycopg.Connection) -> list[str]:
    """Applique dans l'ordre les ``NNN_*.sql`` absents de ``schema_migrations`` ; rejouable."""
    conn.execute("SELECT pg_advisory_lock(%s)", (VERROU_MIGRATIONS,))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version text PRIMARY KEY, applique_le timestamptz NOT NULL DEFAULT now())"
        )
        faites = {v for (v,) in conn.execute("SELECT version FROM schema_migrations")}
        fichiers = sorted(
            (
                f
                for f in resources.files("kaldera").joinpath("migrations").iterdir()
                if f.name.endswith(".sql")
            ),
            key=lambda f: f.name,
        )
        appliquees = []
        for fichier in fichiers:
            if fichier.name in faites:
                continue
            with conn.transaction():
                conn.execute(fichier.read_text("utf-8"))  # sans paramètre : plusieurs requêtes
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (fichier.name,))
            appliquees.append(fichier.name)
        return appliquees
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (VERROU_MIGRATIONS,))


@functools.cache
def pool(url: str) -> ConnectionPool:
    """Un pool par processus et par URL, migrations appliquées à l'ouverture."""
    # ponytail: pool par processus ; injection explicite si une app FastAPI le gère (SP3)
    connexions = ConnectionPool(
        url,
        min_size=1,
        max_size=10,
        timeout=2.0,  # base injoignable : on renonce vite, le traitement continue sans snapshot
        kwargs={"autocommit": True, "connect_timeout": 2},
        open=True,
    )
    try:
        with connexions.connection() as conn:
            appliquer_migrations(conn)
    except psycopg.Error:
        connexions.close()
        raise
    return connexions


@contextmanager
def _connexion(connexions: ConnectionPool) -> Iterator[psycopg.Connection]:
    try:
        with connexions.connection() as conn:
            yield conn
    except psycopg.Error as exc:
        raise ErreurPersistance(f"{type(exc).__name__}: {exc}") from exc
