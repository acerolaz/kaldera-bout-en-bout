"""Unitaires — le reaper : escalade depuis le dernier snapshot, jamais de rejeu (dossier 2.5)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import AvisFraude, Estimation, EtatDemande
from kaldera.machine import Etat
from kaldera.memoire import SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur
from kaldera.reaper import faucher

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


def _demande(scenario: str = "NOM-01") -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][0])


def _processus_tue(vue: dict[str, Any]) -> dict[str, Any]:
    raise KeyboardInterrupt  # BaseException : échappe au filet niveau 1, comme un kill


def test_demande_morte_escaladee_depuis_le_snapshot() -> None:
    snapshots = SnapshotsEnMemoire()
    orch = Orchestrateur(snapshots=snapshots)
    orch.actions[Etat.ESTIMATION] = _processus_tue
    with pytest.raises(KeyboardInterrupt):
        orch.traiter(_demande())

    (fiche,) = faucher(snapshots, 0)
    assert (fiche["reference"], fiche["issue"], fiche["file"]) == (
        "KAL-26-0101",
        "escalade",
        "gestionnaire",
    )
    assert "processus interrompu (reaper)" in fiche["motif"]
    assert "(dernier état : estimation)" in fiche["motif"]
    assert fiche["trace"][-1]["action"] == "reaper"
    ligne = snapshots.lignes["KAL-26-0101"]
    assert ligne["statut"] == "secours" and ligne["fiche"] == fiche
    assert faucher(snapshots, 0) == []  # jamais escaladée deux fois


def test_file_prudente_depuis_le_snapshot() -> None:
    snapshots = SnapshotsEnMemoire()
    etat = EtatDemande(demande=_demande())
    etat.estimation = Estimation(justifie=2000, retenu=2000, franchise=0, plafond=8000, estime=2000)
    etat.avis_fraude = AvisFraude(requis=True, indicateurs=["F1"], statut="indisponible")
    etat.etat_courant = "decision"
    snapshots.debuter(etat)
    (fiche,) = faucher(snapshots, 0)
    assert fiche["file"] == "cellule_fraude"


def test_snapshot_illisible_fiche_minimale() -> None:
    snapshots = SnapshotsEnMemoire()
    snapshots.debuter(EtatDemande(demande=_demande()))
    snapshots.lignes["KAL-26-0101"]["etat"] = {"ancien": "schéma"}
    (fiche,) = faucher(snapshots, 0)
    assert fiche["reference"] == "KAL-26-0101"
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")
    assert fiche["motif"] == "Escalade de secours : snapshot illisible"


def test_rien_a_faucher() -> None:
    assert faucher(SnapshotsEnMemoire(), 0) == []
