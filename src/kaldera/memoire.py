"""Adaptateurs sans base : niveau 0 (demande JSON) et tests."""

from __future__ import annotations

import copy
import threading
from time import monotonic
from typing import Any

from .etat import EtatDemande
from .ports import ErreurPersistance, PieceRef


class DepotDepuisDemande:
    """Niveau 0 : ``pieces`` et ``espace_assure.depots`` de la demande (§3)."""

    def initiales(self, demande: dict[str, Any]) -> list[PieceRef]:
        return [PieceRef.model_validate(p) for p in demande.get("pieces", [])]

    def depots(self, demande: dict[str, Any]) -> list[PieceRef]:
        depots = demande.get("espace_assure", {}).get("depots", [])
        return [PieceRef.model_validate(p) for p in depots]


def _reference(etat: EtatDemande) -> str:
    reference = etat.demande.get("reference")
    if not isinstance(reference, str):  # même refus que la clé primaire en base
        raise ErreurPersistance("demande sans référence")
    return reference


class SnapshotsEnMemoire:
    """Mêmes règles que ``demandes`` en base (CAS) ; tests et démonstration."""

    def __init__(self) -> None:
        self.lignes: dict[str, dict[str, Any]] = {}
        self._verrou = threading.Lock()

    def debuter(self, etat: EtatDemande) -> None:
        with self._verrou:
            self.lignes[_reference(etat)] = {
                "etat": etat.model_dump(mode="json"),
                "etat_courant": etat.etat_courant,
                "statut": "en_cours",
                "maj": monotonic(),
                "fiche": None,
            }

    def enregistrer(self, etat: EtatDemande) -> None:
        with self._verrou:
            ligne = self.lignes.get(_reference(etat))
            if ligne is not None and ligne["statut"] == "en_cours":
                ligne.update(
                    etat=etat.model_dump(mode="json"),
                    etat_courant=etat.etat_courant,
                    maj=monotonic(),
                )

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        with self._verrou:
            ligne = self.lignes.get(_reference(etat))
            if ligne is None or ligne["statut"] != "en_cours":
                return False
            ligne.update(
                statut="terminee",
                etat=etat.model_dump(mode="json"),
                etat_courant=etat.etat_courant,
                fiche=copy.deepcopy(fiche),
                maj=monotonic(),
            )
            return True

    def faucher(self, age_s: float) -> list[tuple[str, dict[str, Any]]]:
        limite = monotonic() - age_s
        with self._verrou:
            mortes = [
                (reference, ligne)
                for reference, ligne in self.lignes.items()
                if ligne["statut"] == "en_cours" and ligne["maj"] < limite
            ]
            for _, ligne in mortes:
                ligne.update(statut="secours", maj=monotonic())
            return [(reference, copy.deepcopy(ligne["etat"])) for reference, ligne in mortes]

    def classer(self, reference: str, fiche: dict[str, Any]) -> None:
        with self._verrou:
            if reference in self.lignes:
                self.lignes[reference]["fiche"] = copy.deepcopy(fiche)


class RegistreA2AEnMemoire:
    """Un appel partenaire par dossier ; même règle que ``appels_partenaire``."""

    def __init__(self) -> None:
        self.evaluations: dict[str, str | None] = {}
        self._verrou = threading.Lock()

    def reserver(self, reference: str) -> bool:
        with self._verrou:
            if reference in self.evaluations:
                return False
            self.evaluations[reference] = None
            return True

    def noter(self, reference: str, evaluation_id: str) -> None:
        with self._verrou:
            if reference in self.evaluations:
                self.evaluations[reference] = evaluation_id
