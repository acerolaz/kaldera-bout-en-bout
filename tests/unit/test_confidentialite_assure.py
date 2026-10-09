"""Confidentialité (spec §6) : les 28 scénarios, avec 4 avis possibles du partenaire, ne laissent
rien passer vers l'assuré — ni avis, score, indicateurs, file fraude, mode dégradé, repli, trace."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from kaldera.memoire import SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur
from kaldera.vue_assure import TEXTE_TRANSMISE, construire

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = [
    json.loads(x) for x in (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()
]
INTERDITS = (
    "fraud",
    "cellule",
    "dégradé",
    "degrade",
    "repli",
    "score",
    "indicateur",
    "partenaire",
    "avis",
    "trace",
    "§",
    "F1",
    "F2",
    "F3",
    "F4",
    "EV-",
    "eligibilite",
    "estimation",
    "antifraude",
    "escalade",
    "decision",
    "llm",
    "agent",
)


def _avis(niveau: str | None) -> Any:
    def evaluer(demande: dict[str, Any], timeout: float) -> dict[str, Any] | None:
        if niveau is None:
            return None  # partenaire indisponible : mode dégradé
        return {
            "reference_dossier": demande["reference"],
            "score": 0.9,
            "niveau": niveau,
            "indicateurs": ["F1"],
            "evaluation_id": "EV-1",
            "version_modele": "m",
        }

    return evaluer


@pytest.mark.parametrize("niveau", [None, "faible", "modere", "eleve"])
def test_rien_d_interne_ne_sort(niveau: str | None) -> None:
    maintenant = datetime.now(UTC)
    for scenario in SCENARIOS:
        for demande in scenario["demandes"]:
            snapshots = SnapshotsEnMemoire()
            fiche = Orchestrateur(evaluer=_avis(niveau), snapshots=snapshots).traiter(demande)
            ligne = snapshots.lignes[demande["reference"]]
            pieces = [
                {
                    "type": p["type"],
                    "statut_analyse": "ok",
                    "lisible": p.get("lisible", True),
                    "montant": p.get("montant"),
                    "depose_le": maintenant,
                }
                for p in demande.get("pieces", [])
            ]
            vue = construire(
                {
                    "reference": demande["reference"],
                    "statut": ligne["statut"],
                    "etat_courant": ligne["etat_courant"],
                    "etat": ligne["etat"],
                    "fiche": fiche,
                    "soumise_le": maintenant,
                    "cree_le": maintenant,
                    "pieces": pieces,
                    "horodatages": {},
                },
                60.0,
            )
            texte = vue.model_dump_json().lower()
            fuites = [mot for mot in INTERDITS if mot.lower() in texte]
            assert not fuites, (scenario["id"], niveau, fuites, texte)
            if fiche["issue"] == "escalade":  # gestionnaire ou cellule_fraude : même vue
                assert vue.branche == "gestionnaire" and vue.verdict is not None
                assert vue.verdict.explication == TEXTE_TRANSMISE
