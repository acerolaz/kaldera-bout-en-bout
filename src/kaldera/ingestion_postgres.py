"""Dépôt d'ingestion PostgreSQL : un seul dépôt pour l'API et le worker (écart SP2 consigné).

Toute ``psycopg.Error`` devient ``ErreurPersistance`` (via ``postgres._connexion``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .etat import EtatDemande
from .postgres import _connexion


class IngestionPostgres:
    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    # ------------------------------------------------------------------ API

    def creer_demande(self, demande: dict[str, Any]) -> bool:
        """Ligne ``admission`` ; faux si la référence existe déjà."""
        etat = EtatDemande(demande=demande).model_dump(mode="json")
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "INSERT INTO demandes (reference, numero_contrat, etat, etat_courant, statut) "
                "VALUES (%s, %s, %s, 'eligibilite', 'admission') "
                "ON CONFLICT (reference) DO NOTHING RETURNING reference",
                (demande["reference"], demande["contrat"]["numero"], Jsonb(etat)),
            ).fetchone()
        return ligne is not None

    def statut(self, reference: str) -> str | None:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "SELECT statut FROM demandes WHERE reference = %s", (reference,)
            ).fetchone()
        return None if ligne is None else str(ligne[0])

    def lire(self, reference: str) -> dict[str, Any] | None:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "SELECT reference, statut, fiche FROM demandes WHERE reference = %s", (reference,)
            ).fetchone()
        return None if ligne is None else dict(zip(("reference", "statut", "fiche"), ligne))

    def deposer_piece(
        self,
        reference: str,
        contenu: bytes,
        mime: str,
        sha256: str,
        type_piece: str,
        relance: int | None,
    ) -> tuple[UUID, bool]:
        """Blob dédupliqué + pièce en attente + tâche ; même fichier déjà déposé ⇒ (id, False)."""
        with _connexion(self.connexions) as conn, conn.transaction():
            self._blob(conn, contenu, mime, sha256)
            ligne = conn.execute(
                "INSERT INTO pieces (reference, sha256, relance, type) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (reference, sha256) DO NOTHING RETURNING piece_id",
                (reference, sha256, relance, type_piece),
            ).fetchone()
            if ligne is None:  # ING-04 : une pièce déposée deux fois ne compte qu'une fois
                existante = conn.execute(
                    "SELECT piece_id FROM pieces WHERE reference = %s AND sha256 = %s",
                    (reference, sha256),
                ).fetchone()
                assert existante is not None  # le conflit prouve qu'elle existe
                return existante[0], False
            self._tache(conn, sha256, "analyser_piece", reference)
            return ligne[0], True

    def deposer_contrat(self, reference: str, contenu: bytes, mime: str, sha256: str) -> None:
        with _connexion(self.connexions) as conn, conn.transaction():
            self._blob(conn, contenu, mime, sha256)
            self._tache(conn, sha256, "extraire_contrat", reference)

    def soumettre(self, reference: str) -> bool:
        """Dossier complet : faux si la demande est inconnue ou n'est plus en admission."""
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "UPDATE demandes SET soumise_le = now() "
                "WHERE reference = %s AND statut = 'admission' RETURNING reference",
                (reference,),
            ).fetchone()
        return ligne is not None

    @staticmethod
    def _blob(conn: Any, contenu: bytes, mime: str, sha256: str) -> None:
        conn.execute(
            "INSERT INTO blobs (sha256, contenu, mime, taille) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (sha256) DO NOTHING",
            (sha256, contenu, mime, len(contenu)),
        )

    @staticmethod
    def _tache(conn: Any, sha256: str, tache: str, reference: str) -> None:
        conn.execute(
            "INSERT INTO file_ingestion (sha256, tache, reference) VALUES (%s, %s, %s)",
            (sha256, tache, reference),
        )
