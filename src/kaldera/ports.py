"""Ports de persistance (dossier 2.4 bis, 2.5, 2.6) : le domaine ne connaît que ces contrats.

Adaptateurs : ``memoire`` (sans base, niveau 0 et tests), ``postgres`` (production).
"""

from __future__ import annotations

from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, model_validator

from .etat import EtatDemande


class ErreurPersistance(Exception):
    """La base n'a pas pu lire ou écrire : jamais bloquant pour une décision (EX-01)."""


class PieceRef(BaseModel):
    """Descripteur d'une pièce : une référence, jamais d'octets (claim check)."""

    type: Literal["facture", "photo", "depot_plainte"]
    lisible: bool
    montant: float | None = None  # numeric → float au centime dans l'adaptateur Postgres
    piece_id: UUID | None = None
    sha256: str | None = None
    statut_analyse: Literal["ok", "echec"] = "ok"

    @model_validator(mode="after")
    def _illisible_si_echec(self) -> PieceRef:
        if self.statut_analyse == "echec":
            self.lisible = False
        return self


class DepotPieces(Protocol):
    """Lecture des pièces d'une demande ; seule la vue de ``pieces`` les reçoit."""

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]: ...

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]: ...  # dans l'ordre de dépôt


class Snapshots(Protocol):
    """Exécution durable (dossier 2.5) : un snapshot par transition, CAS en fin de traitement."""

    def debuter(self, etat: EtatDemande) -> None: ...

    def enregistrer(self, etat: EtatDemande) -> None: ...

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool: ...

    def faucher(self, age_s: float) -> list[tuple[str, dict[str, Any]]]: ...

    def classer(self, reference: str, fiche: dict[str, Any]) -> None: ...


class RegistreA2A(Protocol):
    """Un appel partenaire par dossier (contrat §6) ; branché au chantier 2."""

    def reserver(self, reference: str) -> bool: ...

    def noter(self, reference: str, evaluation_id: str) -> None: ...
