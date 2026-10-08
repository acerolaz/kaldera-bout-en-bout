"""Unitaires — exécution durable : snapshot par transition (dossier 2.5, niveau 2)."""

from __future__ import annotations

import copy
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import EtatDemande
from kaldera.machine import Etat
from kaldera.memoire import SnapshotsEnMemoire
from kaldera.orchestrateur import Orchestrateur
from kaldera.ports import ErreurPersistance

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}
NOMINAUX = [d for s in SCENARIOS.values() if s["categorie"] == "nominal" for d in s["demandes"]]
DECISIFS = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")


def _demande(scenario: str = "NOM-01") -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][0])


def _sans_partenaire(demande: dict[str, Any], timeout: float) -> None:
    raise AssertionError("aucun appel au partenaire attendu")


class Espion(SnapshotsEnMemoire):
    def __init__(self) -> None:
        super().__init__()
        self.appels: list[Any] = []

    def debuter(self, etat: EtatDemande) -> None:
        self.appels.append("debuter")
        super().debuter(etat)

    def enregistrer(self, etat: EtatDemande) -> None:
        self.appels.append(("enregistrer", etat.etat_courant))
        super().enregistrer(etat)

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        self.appels.append("terminer")
        return super().terminer(etat, fiche)


class EnPanne(SnapshotsEnMemoire):
    def debuter(self, etat: EtatDemande) -> None:
        raise ErreurPersistance("base injoignable")

    def enregistrer(self, etat: EtatDemande) -> None:
        raise ErreurPersistance("base injoignable")

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        raise ErreurPersistance("base injoignable")


def test_un_snapshot_par_transition() -> None:
    snapshots = Espion()
    fiche = Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots).traiter(_demande())
    assert snapshots.appels == [
        "debuter",
        ("enregistrer", "pieces"),
        ("enregistrer", "estimation"),
        ("enregistrer", "antifraude"),
        ("enregistrer", "decision"),
        ("enregistrer", "acceptee"),
        "terminer",
    ]
    ligne = snapshots.lignes[fiche["reference"]]
    assert ligne["statut"] == "terminee" and ligne["fiche"] == fiche


def test_la_garde_d_entree_est_aussi_snapshotee() -> None:
    snapshots = Espion()
    demande = _demande()
    demande["contrat"]["statut_extraction"] = "non_exploitable"
    Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots).traiter(demande)
    assert [a for a in snapshots.appels if a[0] == "enregistrer"] == [
        ("enregistrer", "decision"),
        ("enregistrer", "escalade"),
    ]


def test_base_en_panne_ne_change_aucune_issue() -> None:
    temoin = Orchestrateur(evaluer=_sans_partenaire).traiter(_demande())
    fiche = Orchestrateur(evaluer=_sans_partenaire, snapshots=EnPanne()).traiter(_demande())
    assert {k: fiche[k] for k in DECISIFS} == {k: temoin[k] for k in DECISIFS}
    assert all(e.get("persistance") == "echec" for e in fiche["trace"])


def test_demande_sans_reference_rendue_malgre_la_base() -> None:
    fiche = Orchestrateur(snapshots=SnapshotsEnMemoire()).traiter({})
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")


def test_fin_normale_apres_le_reaper(caplog: pytest.LogCaptureFixture) -> None:
    snapshots = SnapshotsEnMemoire()
    orch = Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots)
    decision = orch.actions[Etat.DECISION]

    def reaper_puis_decision(vue: dict[str, Any]) -> dict[str, Any]:
        snapshots.faucher(0)  # le reaper passe pendant que la demande traîne
        patch, _ = decision.executer(vue, 5.0)  # type: ignore[union-attr]
        return patch

    orch.actions[Etat.DECISION] = reaper_puis_decision
    with caplog.at_level(logging.WARNING):
        fiche = orch.traiter(_demande())
    assert fiche["decision"] == "acceptee"
    assert snapshots.lignes[fiche["reference"]]["statut"] == "secours"
    assert "reaper" in caplog.text


def test_lot_parallele_snapshots_partages() -> None:
    snapshots = SnapshotsEnMemoire()
    # KAL-26-0104 lève F2 : le partenaire est consulté, ici indisponible (mode dégradé)
    orch = Orchestrateur(evaluer=lambda demande, timeout: None, snapshots=snapshots)
    with ThreadPoolExecutor() as pool:
        fiches = list(pool.map(orch.traiter, copy.deepcopy(NOMINAUX)))
    assert {f["reference"] for f in fiches} == set(snapshots.lignes)
    assert {ligne["statut"] for ligne in snapshots.lignes.values()} == {"terminee"}


class EnPanneLente(SnapshotsEnMemoire):
    """Base tombée après l'ouverture du pool : chaque écriture attend avant d'échouer."""

    def __init__(self) -> None:
        super().__init__()
        self.essais = 0

    def _echouer(self) -> None:
        self.essais += 1
        time.sleep(0.5)
        raise ErreurPersistance("PoolTimeout")

    def debuter(self, etat: EtatDemande) -> None:
        self._echouer()

    def enregistrer(self, etat: EtatDemande) -> None:
        self._echouer()

    def terminer(self, etat: EtatDemande, fiche: dict[str, Any]) -> bool:
        self._echouer()
        return False


def test_base_tombee_une_seule_attente_par_demande() -> None:
    snapshots = EnPanneLente()
    temoin = Orchestrateur(evaluer=_sans_partenaire).traiter(_demande())
    fiche = Orchestrateur(evaluer=_sans_partenaire, snapshots=snapshots).traiter(_demande())
    assert snapshots.essais == 1  # après le premier échec, plus aucune écriture
    assert {k: fiche[k] for k in DECISIFS} == {k: temoin[k] for k in DECISIFS}


def test_les_vues_hors_pieces_ne_contiennent_aucune_piece() -> None:
    vues: dict[str, dict[str, Any]] = {}
    orch = Orchestrateur(evaluer=_sans_partenaire)
    for etat_machine in (Etat.ELIGIBILITE, Etat.ESTIMATION):
        action = orch.actions[etat_machine]

        def espion(vue: dict[str, Any], action: Any = action, nom: str = etat_machine.value) -> Any:
            vues[nom] = vue
            return (
                action(vue)
                if callable(action) and not hasattr(action, "executer")
                else (action.executer(vue, 5.0)[0])
            )

        orch.actions[etat_machine] = espion
    orch.traiter(_demande("NOM-07"))
    for nom, vue in vues.items():
        assert "pieces" not in vue["demande"] and "espace_assure" not in vue["demande"], nom
