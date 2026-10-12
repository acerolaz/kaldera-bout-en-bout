"""Dépôt des lots (spec C3-3 §2.2, §2.3) : lancement tout ou rien, lecture pour E3.

Toute ``psycopg.Error`` devient ``ErreurPersistance`` (via ``postgres._connexion``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg_pool import ConnectionPool

from .ingestion_postgres import DemandeLue, _demande_lue, _ligne
from .postgres import _connexion


class ReferencesInconnues(Exception):
    def __init__(self, references: list[str]) -> None:
        super().__init__(f"demandes inconnues : {', '.join(references)}")
        self.references = references


class DossiersNonLancables(Exception):
    """Au moins un dossier n'est pas « prete » : rien n'est lancé (tout ou rien)."""

    def __init__(self, references: list[str]) -> None:
        super().__init__(f"dossiers non lançables : {', '.join(references)}")
        self.references = references


@dataclass(frozen=True)
class LotLu:
    id: int
    debut: datetime
    derniere_maj: datetime
    demandes: list[DemandeLue]


class DepotLots:
    def __init__(self, connexions: ConnectionPool) -> None:
        self.connexions = connexions

    def lancer(self, references: list[str]) -> tuple[int, list[dict[str, Any]]]:
        """Crée le lot et passe ses dossiers de ``prete`` à ``en_cours`` en une transaction ;
        renvoie (id du lot, demandes dans l'ordre reçu). Une exception annule tout."""
        with _connexion(self.connexions) as conn, conn.transaction():
            connues = {
                r
                for (r,) in conn.execute(
                    # ordre fixe : deux lots qui se recouvrent verrouillent dans le même ordre
                    "SELECT reference FROM demandes WHERE reference = ANY(%s) "
                    "ORDER BY reference FOR UPDATE",
                    (references,),
                )
            }
            if inconnues := [r for r in references if r not in connues]:
                raise ReferencesInconnues(inconnues)
            lancees = dict(
                conn.execute(
                    "UPDATE demandes SET statut = 'en_cours', maj = now() "
                    "WHERE reference = ANY(%s) AND statut = 'prete' RETURNING reference, etat",
                    (references,),
                ).fetchall()
            )
            if refusees := [r for r in references if r not in lancees]:
                raise DossiersNonLancables(refusees)
            (lot_id,) = _ligne(conn.execute("INSERT INTO lots DEFAULT VALUES RETURNING id"))
            conn.cursor().executemany(
                "INSERT INTO lot_demandes (lot_id, reference) VALUES (%s, %s)",
                [(lot_id, r) for r in references],
            )
        return int(lot_id), [dict(lancees[r]["demande"]) for r in references]

    def lire(self, lot_id: int) -> LotLu | None:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "SELECT l.cree_le, d.maj, d.reference, d.statut, d.fiche, d.etat FROM lots l "
                "JOIN lot_demandes ld ON ld.lot_id = l.id "
                "JOIN demandes d ON d.reference = ld.reference "
                "WHERE l.id = %s ORDER BY d.reference",
                (lot_id,),
            ).fetchall()
        if not lignes:  # un lot a toujours au moins un dossier
            return None
        return LotLu(
            id=lot_id,
            debut=lignes[0][0],
            derniere_maj=max(ligne[1] for ligne in lignes),
            demandes=[_demande_lue(tuple(ligne[2:])) for ligne in lignes],
        )

    def references(self, lot_id: int) -> list[str] | None:
        with _connexion(self.connexions) as conn:
            lignes = conn.execute(
                "SELECT reference FROM lot_demandes WHERE lot_id = %s ORDER BY reference",
                (lot_id,),
            ).fetchall()
        return [r for (r,) in lignes] or None
