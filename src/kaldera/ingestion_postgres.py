"""Dépôt d'ingestion PostgreSQL : un seul dépôt pour l'API et le worker (écart SP2 consigné).

Toute ``psycopg.Error`` devient ``ErreurPersistance`` (via ``postgres._connexion``).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .etat import EtatDemande
from .ingestion import ExtractionContrat
from .ports import ErreurPersistance
from .postgres import _connexion


def _ligne(curseur: Any) -> tuple[Any, ...]:
    """Ligne garantie par le schéma ; absente ⇒ base incohérente, jamais un plantage muet."""
    ligne = curseur.fetchone()
    if ligne is None:
        raise ErreurPersistance("ligne attendue absente")
    return tuple(ligne)


@dataclass(frozen=True)
class Tache:
    id: int
    sha256: str
    tache: str
    reference: str
    contenu: bytes
    mime: str


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

    # ------------------------------------------------------------------ worker

    def reprendre_bloquees(self, age_s: float) -> int:
        """Tâches prises par un worker mort : de nouveau en attente."""
        with _connexion(self.connexions) as conn:
            curseur = conn.execute(
                "UPDATE file_ingestion SET statut = 'en_attente', pris_le = NULL "
                "WHERE statut = 'en_cours' AND pris_le < now() - make_interval(secs => %s)",
                (age_s,),
            )
            return curseur.rowcount

    def prendre_tache(self) -> Tache | None:
        """Une tâche, verrouillée le temps de la marquer : l'analyse se fait hors transaction."""
        with _connexion(self.connexions) as conn:
            with conn.transaction():
                ligne = conn.execute(
                    "SELECT id, sha256, tache, reference FROM file_ingestion "
                    "WHERE statut = 'en_attente' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1"
                ).fetchone()
                if ligne is None:
                    return None
                conn.execute(
                    "UPDATE file_ingestion SET statut = 'en_cours', pris_le = now() WHERE id = %s",
                    (ligne[0],),
                )
            contenu, mime = _ligne(
                conn.execute("SELECT contenu, mime FROM blobs WHERE sha256 = %s", (ligne[1],))
            )
        return Tache(ligne[0], ligne[1], ligne[2], ligne[3], bytes(contenu), mime)

    def analyse_en_cache(self, sha256: str, modele: str, version: str) -> dict[str, Any] | None:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "SELECT resultat FROM analyses "
                "WHERE sha256 = %s AND modele = %s AND version_prompt = %s",
                (sha256, modele, version),
            ).fetchone()
        return None if ligne is None else dict(ligne[0])

    def mettre_en_cache(
        self, sha256: str, modele: str, version: str, resultat: dict[str, Any]
    ) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "INSERT INTO analyses (sha256, modele, version_prompt, resultat) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (sha256, modele, version, Jsonb(resultat)),
            )

    def type_declare(self, reference: str, sha256: str) -> str:
        with _connexion(self.connexions) as conn:
            (type_piece,) = _ligne(
                conn.execute(
                    "SELECT type FROM pieces WHERE reference = %s AND sha256 = %s",
                    (reference, sha256),
                )
            )
        return str(type_piece)

    def ecrire_piece(
        self,
        reference: str,
        sha256: str,
        statut: str,
        lisible: bool,
        montant: Decimal | None,
    ) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE pieces SET statut_analyse = %s, lisible = %s, montant = %s "
                "WHERE reference = %s AND sha256 = %s",
                (statut, lisible, montant, reference, sha256),
            )

    def numero_contrat(self, reference: str) -> str:
        with _connexion(self.connexions) as conn:
            (numero,) = _ligne(
                conn.execute(
                    "SELECT numero_contrat FROM demandes WHERE reference = %s", (reference,)
                )
            )
        return str(numero)

    def ecrire_contrat(
        self,
        numero: str,
        sha256: str,
        extraction: ExtractionContrat | None,
        violations: list[str],
        modele: str,
        version: str,
    ) -> None:
        """Termes extraits, une ligne par numéro ; ``valide`` seulement sans aucune violation."""
        termes = (
            (None, None, None, None)
            if extraction is None
            else (
                extraction.formule,
                extraction.date_souscription,
                extraction.franchise,
                extraction.plafond,
            )
        )
        with _connexion(self.connexions) as conn:
            conn.execute(
                "INSERT INTO contrats (numero, sha256, formule, date_souscription, franchise, "
                "plafond, statut_extraction, violations, modele, version_prompt) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (numero) DO UPDATE SET sha256 = EXCLUDED.sha256, "
                "formule = EXCLUDED.formule, date_souscription = EXCLUDED.date_souscription, "
                "franchise = EXCLUDED.franchise, plafond = EXCLUDED.plafond, "
                "statut_extraction = EXCLUDED.statut_extraction, "
                "violations = EXCLUDED.violations, modele = EXCLUDED.modele, "
                "version_prompt = EXCLUDED.version_prompt",
                (
                    numero,
                    sha256,
                    *termes,
                    "non_exploitable" if violations else "valide",
                    violations,
                    modele,
                    version,
                ),
            )

    def finir_tache(self, id_tache: int, statut: str) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute("UPDATE file_ingestion SET statut = %s WHERE id = %s", (statut, id_tache))

    _ADMISSIBLE = (
        "statut = 'admission' AND soumise_le IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM pieces p WHERE p.reference = demandes.reference "
        "AND p.statut_analyse = 'en_attente') "
        "AND NOT EXISTS (SELECT 1 FROM file_ingestion f WHERE f.reference = demandes.reference "
        "AND f.statut IN ('en_attente', 'en_cours'))"
    )

    def admissibles(self, limite: int = 10) -> list[str]:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "SELECT reference FROM demandes WHERE " + self._ADMISSIBLE + " LIMIT %s",
                (limite,),
            ).fetchall()
        return [reference for (reference,) in lignes]

    def admettre(self, reference: str) -> dict[str, Any] | None:
        """Contrôle d'admission atomique : la demande JSON au gagnant, None aux autres."""
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "UPDATE demandes SET statut = 'en_cours', maj = now() "
                "WHERE reference = %s AND " + self._ADMISSIBLE + " RETURNING etat",
                (reference,),
            ).fetchone()
        return None if ligne is None else dict(ligne[0]["demande"])

    def contrat(self, numero: str) -> dict[str, Any] | None:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "SELECT formule, date_souscription, statut_extraction, violations, modele, "
                "version_prompt, sha256 FROM contrats WHERE numero = %s",
                (numero,),
            ).fetchone()
        if ligne is None:
            return None
        cles = (
            "formule",
            "date_souscription",
            "statut_extraction",
            "violations",
            "modele",
            "version_prompt",
            "sha256",
        )
        contrat = dict(zip(cles, ligne))
        if contrat["date_souscription"] is not None:
            contrat["date_souscription"] = contrat["date_souscription"].isoformat()
        contrat["violations"] = list(contrat["violations"])
        return contrat
