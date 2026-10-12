"""Reaper (dossier 2.5, niveau 2) : escalade les demandes dont le processus est mort.

Il lit le dernier snapshot, trace son passage et classe une fiche de secours vers la file la plus
prudente. Il ne rejoue jamais la machine : le partenaire refuserait un second appel (-32029).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import ValidationError

from .etat import EtatDemande
from .machine import Etat
from .orchestrateur import _etape_sans_action, construire_fiche
from .ports import ErreurPersistance, Signaux, Snapshots
from .postgres import ConfigBase, SignauxPostgres, SnapshotsPostgres, pool

LOGGER = logging.getLogger(__name__)


def faucher(
    snapshots: Snapshots, age_s: float, signaux: Signaux | None = None
) -> list[dict[str, Any]]:
    """Passe en ``secours`` les demandes inactives depuis ``age_s`` s ; retourne leurs fiches."""
    fiches = []
    for reference, brut in snapshots.faucher(age_s):
        fiche = fiche_de_secours(reference, brut)
        try:
            snapshots.classer(reference, fiche)
        except ErreurPersistance as exc:  # sans fiche : reprise au passage suivant
            LOGGER.error("demande %s non classée : %s", reference, exc)
            continue
        if signaux is not None:  # E2 / E3 relisent le dossier clos
            signaux.emettre({"type": "dossier_fin", "reference": reference})
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


PERIODE_S = 10.0


def main() -> None:
    """``python -m kaldera.reaper`` : fauche toutes les 10 s, indépendamment des workers."""
    logging.basicConfig(level=logging.INFO)
    config = ConfigBase()
    if not config.database_url:
        raise SystemExit("KALDERA_DATABASE_URL absente : rien à faucher")
    connexions = pool(config.database_url)
    snapshots = SnapshotsPostgres(connexions)
    signaux = SignauxPostgres(connexions)
    while True:
        try:
            fiches = faucher(snapshots, config.reaper_age_s, signaux)
            for fiche in fiches:
                LOGGER.warning(
                    "demande %s escaladée par le reaper (file %s)",
                    fiche["reference"],
                    fiche["file"],
                )
        except ErreurPersistance as exc:
            LOGGER.error("reaper : %s ; nouvel essai dans %s s", exc, PERIODE_S)
        time.sleep(PERIODE_S)


if __name__ == "__main__":
    main()
