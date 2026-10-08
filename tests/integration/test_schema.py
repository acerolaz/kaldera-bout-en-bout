"""Intégration — les règles de conception tenues par la base (dossier 2.6 bis)."""

from __future__ import annotations

from typing import Any

import psycopg
import pytest

from kaldera.postgres import appliquer_migrations

pytestmark = pytest.mark.integration
SHA = "a" * 64


def _blob(conn: Any, sha: str = SHA, mime: str = "application/pdf", taille: int = 10) -> None:
    conn.execute(
        "INSERT INTO blobs (sha256, contenu, mime, taille) VALUES (%s, %s, %s, %s)",
        (sha, b"x", mime, taille),
    )


def _demande(conn: Any, reference: str = "KAL-26-9001", statut: str = "en_cours") -> None:
    conn.execute(
        "INSERT INTO demandes (reference, etat, etat_courant, statut) "
        "VALUES (%s, '{}', 'eligibilite', %s)",
        (reference, statut),
    )


def _piece(conn: Any, montant: float | None = None, sha: str = SHA) -> None:
    conn.execute(
        "INSERT INTO pieces (reference, sha256, type, statut_analyse, lisible, montant) "
        "VALUES ('KAL-26-9001', %s, 'facture', 'ok', true, %s)",
        (sha, montant),
    )


def test_migrations_rejouables_sans_effet(base: Any) -> None:
    with base.connection() as conn:
        assert appliquer_migrations(conn) == []


@pytest.mark.parametrize(
    ("mime", "taille"),
    [("application/x-msdownload", 10), ("application/pdf", 10_485_761), ("application/pdf", 0)],
)
def test_fichier_hors_contrat_refuse(base: Any, mime: str, taille: int) -> None:
    with base.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        _blob(conn, mime=mime, taille=taille)


def test_empreinte_mal_formee_refusee(base: Any) -> None:
    with base.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        _blob(conn, sha="pas-un-sha256")


def test_meme_fichier_depose_deux_fois_compte_une_fois(base: Any) -> None:  # ING-04
    with base.connection() as conn:
        _blob(conn)
        _demande(conn)
        _piece(conn, 640.5)
        with pytest.raises(psycopg.errors.UniqueViolation):
            _piece(conn, 640.5)


def test_montant_nul_refuse(base: Any) -> None:
    with base.connection() as conn:
        _blob(conn)
        _demande(conn)
        with pytest.raises(psycopg.errors.CheckViolation):
            _piece(conn, 0)


def test_statut_de_demande_inconnu_refuse(base: Any) -> None:
    with base.connection() as conn, pytest.raises(psycopg.errors.CheckViolation):
        _demande(conn, statut="perdue")


def test_demande_sans_contrat_acceptee(base: Any) -> None:  # numero_contrat nullable
    with base.connection() as conn:
        _demande(conn)
        (numero,) = conn.execute(
            "SELECT numero_contrat FROM demandes WHERE reference = 'KAL-26-9001'"
        ).fetchone()
    assert numero is None
