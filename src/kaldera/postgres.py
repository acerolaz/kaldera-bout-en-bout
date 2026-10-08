"""Adaptateurs PostgreSQL (dossier 2.6) : psycopg 3 synchrone, SQL brut, migrations versionnées.

Toute ``psycopg.Error`` devient ``ErreurPersistance`` : le domaine ne voit jamais le pilote.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from typing import Any

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from .etat import EtatDemande
from .ports import ErreurPersistance, PieceRef

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


def _piece(
    type_: str, lisible: bool | None, montant: Any, piece_id: Any, sha256: str, statut: str
) -> PieceRef:
    ok = statut == "ok"  # en_attente ou echec : jamais lisible
    return PieceRef.model_validate(
        {
            "type": type_,
            "lisible": bool(lisible) and ok,
            "montant": None if montant is None else round(float(montant), 2),  # Decimal → float
            "piece_id": piece_id,
            "sha256": sha256,
            "statut_analyse": "ok" if ok else "echec",
        }
    )


class DepotPostgres:
    """Niveau 1 : descripteurs de la table ``pieces`` (remplie par l'ingestion, SP3)."""

    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]:
        return self._lire(
            "SELECT type, lisible, montant, piece_id, sha256, statut_analyse FROM pieces "
            "WHERE reference = %s AND relance IS NULL ORDER BY piece_id",
            demande,
        )

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]:
        return self._lire(
            "SELECT type, lisible, montant, piece_id, sha256, statut_analyse FROM pieces "
            "WHERE reference = %s AND relance IS NOT NULL ORDER BY relance, piece_id",
            demande,
        )

    def _lire(self, requete: str, demande: dict[str, Any]) -> list[PieceRef]:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(requete, (demande.get("reference"),)).fetchall()
        return [_piece(*ligne) for ligne in lignes]


def _snapshot(etat: EtatDemande) -> Jsonb:
    return Jsonb(etat.model_dump(mode="json"))


class SnapshotsPostgres:
    """Table ``demandes`` : snapshot par transition, compare-and-set en fin et pour le reaper."""

    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def debuter(self, etat: EtatDemande) -> None:
        contrat = etat.demande.get("contrat")
        numero = contrat.get("numero") if isinstance(contrat, dict) else None
        with _connexion(self.connexions) as conn:
            conn.execute(
                "INSERT INTO demandes (reference, numero_contrat, etat, etat_courant, statut) "
                "VALUES (%s, %s, %s, %s, 'en_cours') "
                "ON CONFLICT (reference) DO UPDATE SET numero_contrat = EXCLUDED.numero_contrat, "
                "etat = EXCLUDED.etat, etat_courant = EXCLUDED.etat_courant, "
                "statut = 'en_cours', maj = now(), fiche = NULL",
                (etat.demande.get("reference"), numero, _snapshot(etat), etat.etat_courant),
            )

    def enregistrer(self, etat: EtatDemande) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE demandes SET etat = %s, etat_courant = %s, maj = now() "
                "WHERE reference = %s AND statut = 'en_cours'",
                (_snapshot(etat), etat.etat_courant, etat.demande.get("reference")),
            )

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "UPDATE demandes SET statut = 'terminee', etat = %s, etat_courant = %s, "
                "fiche = %s, maj = now() WHERE reference = %s AND statut = 'en_cours' "
                "RETURNING reference",
                (_snapshot(etat), etat.etat_courant, Jsonb(fiche), etat.demande.get("reference")),
            ).fetchone()
        return ligne is not None

    def faucher(self, age_s: float) -> list[tuple[str, dict[str, Any]]]:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "UPDATE demandes SET statut = 'secours', maj = now() "
                "WHERE statut = 'en_cours' AND maj < now() - make_interval(secs => %s) "
                "RETURNING reference, etat",
                (age_s,),
            ).fetchall()
        return [(reference, etat) for reference, etat in lignes]

    def classer(self, reference: str, fiche: dict[str, Any]) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE demandes SET fiche = %s WHERE reference = %s", (Jsonb(fiche), reference)
            )


class RegistreA2APostgres:
    """Table ``appels_partenaire`` : la réservation précède l'envoi (contrat §6)."""

    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def reserver(self, reference: str) -> bool:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "INSERT INTO appels_partenaire (reference) VALUES (%s) "
                "ON CONFLICT (reference) DO NOTHING RETURNING reference",
                (reference,),
            ).fetchone()
        return ligne is not None

    def noter(self, reference: str, evaluation_id: str) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE appels_partenaire SET evaluation_id = %s WHERE reference = %s",
                (evaluation_id, reference),
            )


def snapshots_par_defaut() -> SnapshotsPostgres | None:
    """Snapshots PostgreSQL si ``KALDERA_DATABASE_URL`` est configurée et joignable, sinon aucun."""
    try:
        url = ConfigBase().database_url
    except ValidationError as exc:  # .env malformé : jamais bloquant
        LOGGER.warning("configuration de la base invalide, sans snapshot : %s", exc)
        return None
    if not url:
        return None
    try:
        return SnapshotsPostgres(pool(url))
    except psycopg.Error as exc:
        LOGGER.warning("PostgreSQL injoignable, traitement sans snapshot : %s", exc)
        return None
