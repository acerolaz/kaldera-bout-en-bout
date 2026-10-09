"""Espace assuré (UI1) : comptes, rattachement, données projetables, événements — SQL seul.

La projection vers l'assuré vit dans ``vue_assure`` ; ce dépôt ne fait que lire et écrire.
Toute ``psycopg.Error`` devient ``ErreurPersistance`` (via ``postgres._connexion``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .ingestion_postgres import _ligne
from .postgres import _connexion

_COMPTE = "SELECT id, identifiant, hash, role, echecs, bloque_jusqu FROM utilisateurs WHERE "


@dataclass(frozen=True)
class Compte:
    id: UUID
    identifiant: str
    hash: str
    role: str
    echecs: int
    bloque_jusqu: datetime | None


class DepotAssure:
    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    # ------------------------------------------------------------------ comptes

    def creer_compte(self, identifiant: str, hash_: str, role: str) -> UUID:
        """Crée le compte, ou le réinitialise (démonstration rejouable)."""
        with _connexion(self.connexions) as conn:
            (id_,) = _ligne(
                conn.execute(
                    "INSERT INTO utilisateurs (identifiant, hash, role) VALUES (%s, %s, %s) "
                    "ON CONFLICT (identifiant) DO UPDATE SET hash = EXCLUDED.hash, "
                    "role = EXCLUDED.role, echecs = 0, bloque_jusqu = NULL RETURNING id",
                    (identifiant, hash_, role),
                )
            )
        return UUID(str(id_))

    def compte(self, identifiant: str) -> Compte | None:
        return self._compte("identifiant = %s", identifiant)

    def compte_par_id(self, id_: UUID) -> Compte | None:
        return self._compte("id = %s", id_)

    def _compte(self, condition: str, valeur: Any) -> Compte | None:
        with _connexion(self.connexions) as conn:  # condition : littéral de cette classe
            ligne = conn.execute(_COMPTE + condition, (valeur,)).fetchone()
        return None if ligne is None else Compte(*ligne)

    def noter_echec(self, id_: UUID, seuil: int, blocage_s: float) -> None:
        """Un échec de plus ; ``seuil`` atteint ⇒ bloqué ``blocage_s`` s (repart à 1 après)."""
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE utilisateurs SET "
                "echecs = CASE WHEN bloque_jusqu < now() THEN 1 ELSE echecs + 1 END, "
                "bloque_jusqu = CASE "
                "WHEN (CASE WHEN bloque_jusqu < now() THEN 1 ELSE echecs + 1 END) >= %s "
                "THEN now() + make_interval(secs => %s) "
                "WHEN bloque_jusqu < now() THEN NULL ELSE bloque_jusqu END "
                "WHERE id = %s",
                (seuil, blocage_s, id_),
            )

    def remettre_a_zero(self, id_: UUID) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "UPDATE utilisateurs SET echecs = 0, bloque_jusqu = NULL WHERE id = %s", (id_,)
            )

    # ------------------------------------------------------------------ rattachement

    def rattacher(self, utilisateur: UUID, reference: str) -> None:
        with _connexion(self.connexions) as conn:
            conn.execute(
                "INSERT INTO demandes_assure (utilisateur, reference) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING",
                (utilisateur, reference),
            )

    def demandes_de(self, utilisateur: UUID) -> list[str]:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "SELECT reference FROM demandes_assure WHERE utilisateur = %s ORDER BY reference",
                (utilisateur,),
            ).fetchall()
        return [str(reference) for (reference,) in lignes]

    def appartient(self, utilisateur: UUID, reference: str) -> bool:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "SELECT 1 FROM demandes_assure WHERE utilisateur = %s AND reference = %s",
                (utilisateur, reference),
            ).fetchone()
        return ligne is not None

    # ------------------------------------------------------------------ lecture

    def statut(self, reference: str) -> str | None:
        with _connexion(self.connexions) as conn:
            ligne = conn.execute(
                "SELECT statut FROM demandes WHERE reference = %s", (reference,)
            ).fetchone()
        return None if ligne is None else str(ligne[0])

    def donnees(self, reference: str) -> dict[str, Any] | None:
        """Tout ce dont ``vue_assure`` a besoin ; rien n'est exposé tel quel à l'assuré."""
        with _connexion(self.connexions) as conn:
            curseur = conn.cursor(row_factory=dict_row)
            demande = curseur.execute(
                "SELECT reference, statut, etat_courant, etat, fiche, soumise_le, cree_le "
                "FROM demandes WHERE reference = %s",
                (reference,),
            ).fetchone()
            if demande is None:
                return None
            pieces = curseur.execute(
                "SELECT type, statut_analyse, lisible, montant, depose_le FROM pieces "
                "WHERE reference = %s ORDER BY depose_le, piece_id",
                (reference,),
            ).fetchall()
            etapes = curseur.execute(
                "SELECT etape, min(cree_le) AS le FROM evenements_assure "
                "WHERE reference = %s AND etape IS NOT NULL GROUP BY etape",
                (reference,),
            ).fetchall()
        return {
            **demande,
            "pieces": pieces,
            "horodatages": {int(e["etape"]): e["le"] for e in etapes},
        }

    # ------------------------------------------------------------------ événements

    def inserer_evenement(
        self, reference: str, type_: str, etape: int | None, contenu: dict[str, Any]
    ) -> int:
        with _connexion(self.connexions) as conn:
            (id_,) = _ligne(
                conn.execute(
                    "INSERT INTO evenements_assure (reference, type, etape, contenu) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (reference, type_, etape, Jsonb(contenu)),
                )
            )
        return int(id_)

    def evenements_depuis(
        self, reference: str, apres: int, limite: int = 100
    ) -> list[dict[str, Any]]:
        with _connexion(self.connexions) as conn:
            lignes = (
                conn.cursor(row_factory=dict_row)
                .execute(
                    "SELECT id, type, contenu FROM evenements_assure "
                    "WHERE reference = %s AND id > %s ORDER BY id LIMIT %s",
                    (reference, apres, limite),
                )
                .fetchall()
            )
        return list(lignes)

    def messages_assure(self, reference: str) -> int:
        with _connexion(self.connexions) as conn:
            (nombre,) = _ligne(
                conn.execute(
                    "SELECT count(*) FROM evenements_assure WHERE reference = %s "
                    "AND type = 'message' AND contenu->>'auteur' = 'assure'",
                    (reference,),
                )
            )
        return int(nombre)
