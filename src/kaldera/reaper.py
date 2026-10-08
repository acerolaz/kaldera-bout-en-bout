"""Reaper (dossier 2.5, niveau 2) : escalade les demandes dont le processus est mort.

Il lit le dernier snapshot, trace son passage et classe une fiche de secours vers la file la plus
prudente. Il ne rejoue jamais la machine : le partenaire refuserait un second appel (-32029).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from .etat import EtatDemande
from .machine import Etat
from .orchestrateur import _etape_sans_action, construire_fiche
from .ports import Snapshots

LOGGER = logging.getLogger(__name__)


def faucher(snapshots: Snapshots, age_s: float) -> list[dict[str, Any]]:
    """Passe en ``secours`` les demandes inactives depuis ``age_s`` s ; retourne leurs fiches."""
    fiches = []
    for reference, brut in snapshots.faucher(age_s):
        fiche = fiche_de_secours(reference, brut)
        snapshots.classer(reference, fiche)
        fiches.append(fiche)
    return fiches


def fiche_de_secours(reference: str, brut: dict[str, Any]) -> dict[str, Any]:
    try:
        etat = EtatDemande.model_validate(brut)
    except ValidationError:
        LOGGER.error("snapshot illisible, demande %s", reference)
        return {
            "reference": reference,
            "issue": "escalade",
            "decision": None,
            "montant_rembourse": None,
            "motif": "Escalade de secours : snapshot illisible",
            "file": "gestionnaire",
            "mode_degrade": False,
            "avis_fraude": None,
            "trace": [],
            "arret": None,
        }
    etat.escalade_forcee = "processus interrompu (reaper)"
    etat.trace.append(
        _etape_sans_action(
            agent="orchestrateur",
            action="reaper",
            statut="echec",
            de=etat.etat_courant,
            vers=Etat.ESCALADE.value,
            garde="reaper",
        )
    )
    return construire_fiche(etat)
