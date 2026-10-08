"""Unitaires — le tool d'éligibilité et les 4 agents spécialistes (dossier 1.1 à 1.3).

Chaque agent reçoit une vue (dict) et renvoie un patch de sa seule section.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.agents import (
    AgentAntifraude,
    AgentDecision,
    AgentEstimation,
    AgentPieces,
    is_eligible,
)

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


def _demande(scenario: str, rang: int = 0) -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][rang])


def _pieces(scenario: str, relances: int = 0) -> dict[str, Any]:
    patch = AgentPieces()({"demande": _demande(scenario), "relances": relances})
    assert set(patch) == {"pieces"}
    return patch["pieces"]


def _estimation(scenario: str) -> dict[str, Any]:
    vue = {"demande": _demande(scenario), "pieces": _pieces(scenario)}
    patch = AgentEstimation()(vue)
    assert set(patch) == {"estimation"}
    return patch["estimation"]


# ------------------------------------------------------------------ is_eligible


def test_contrat_resilie_non_eligible() -> None:
    eligibilite = is_eligible(_demande("NOM-02"))
    assert eligibilite["eligible"] is False and eligibilite["conditions_ko"]


def test_plafond_ne_releve_pas_de_l_eligibilite() -> None:
    """NOM-05 : déclaré 4 200 € > plafond 3 000 €, mais éligible — c'est l'estimation qui plafonne."""
    assert is_eligible(_demande("NOM-05")) == {"eligible": True, "conditions_ko": []}


# ------------------------------------------------------------------ pieces


def test_pieces_completes() -> None:
    assert _pieces("NOM-01")["statut"] == "complet"


def test_piece_manquante_sans_depot_possible() -> None:
    pieces = _pieces("NOM-09")
    assert pieces["statut"] == "manquant" and pieces["manquantes"] == ["photo"]


def test_piece_manquante_avec_depot_a_lire() -> None:
    assert _pieces("NOM-07")["statut"] == "incomplet"


def test_relance_lit_le_depot_et_complete() -> None:
    assert _pieces("NOM-07", relances=1)["statut"] == "complet"


def test_depot_illisible_n_est_pas_un_progres() -> None:
    pieces = _pieces("BCL-01", relances=1)
    assert pieces["statut"] == "incomplet" and pieces["manquantes"] == ["facture"]


# ------------------------------------------------------------------ estimation


def test_franchise_puis_plafond() -> None:
    """NOM-05 : min(4 200, 4 200) − 300 = 3 900, plafonné à 3 000."""
    assert _estimation("NOM-05")["estime"] == 3000.0


def test_estimation_nominale() -> None:
    estimation = _estimation("NOM-01")  # confort, franchise 150
    assert estimation["justifie"] == 1850.0 and estimation["estime"] == 1700.0


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.startswith("NOM")])
def test_estime_entre_zero_et_plafond(scenario: str) -> None:
    estimation = _estimation(scenario)
    assert 0 <= estimation["estime"] <= estimation["plafond"]


# ------------------------------------------------------------------ antifraude


class Partenaire:
    """Double du client A2A : enregistre ce qu'il reçoit."""

    def __init__(self, reponse: dict[str, Any] | None) -> None:
        self.reponse, self.recus = reponse, []

    def __call__(self, demande: dict[str, Any], timeout: float) -> dict[str, Any] | None:
        self.recus.append((demande, timeout))
        return self.reponse


def _antifraude(scenario: str, partenaire: Partenaire) -> dict[str, Any]:
    vue = {"demande": _demande(scenario), "estimation": _estimation(scenario)}
    patch = AgentAntifraude(partenaire, delai_s=3)(vue)
    assert set(patch) == {"avis_fraude"}
    return patch["avis_fraude"]


def test_sans_indicateur_aucun_appel() -> None:
    partenaire = Partenaire({"niveau": "faible"})
    avis = _antifraude("NOM-01", partenaire)
    assert avis["statut"] == "non_requis" and avis["requis"] is False
    assert partenaire.recus == []


def test_partenaire_muet_avis_indisponible() -> None:
    partenaire = Partenaire(None)
    avis = AgentAntifraude(partenaire, delai_s=3)(
        {"demande": _demande("PAN-01", 3), "estimation": {"justifie": 8800.0}}
    )["avis_fraude"]
    assert avis["requis"] is True and avis["statut"] == "indisponible" and avis["avis"] is None
    assert len(partenaire.recus) == 1 and partenaire.recus[0][1] == 3


def test_avis_du_partenaire_conserve() -> None:
    partenaire = Partenaire({"niveau": "faible", "score": 0.1})
    avis = AgentAntifraude(partenaire, delai_s=3)(
        {"demande": _demande("PAN-01", 3), "estimation": {"justifie": 8800.0}}
    )["avis_fraude"]
    assert avis["statut"] == "avis" and avis["avis"] == {"niveau": "faible", "score": 0.1}
    assert "F1" in avis["indicateurs"]  # 8 800 € ≥ 5 000 €


# ------------------------------------------------------------------ decision


def _vue_decision(**sections: Any) -> dict[str, Any]:
    vue: dict[str, Any] = {
        "eligibilite": {"eligible": True, "conditions_ko": []},
        "pieces": {"statut": "complet", "manquantes": [], "retenues": []},
        "estimation": {"estime": 1000.0},
        "avis_fraude": {"requis": False, "statut": "non_requis", "avis": None},
        "arret": None,
        "escalade_forcee": None,
    }
    vue.update(sections)
    return vue


def _issue(**sections: Any) -> dict[str, Any]:
    patch = AgentDecision()(_vue_decision(**sections))
    assert set(patch) == {"issue"}
    return patch["issue"]


def test_regle_6_acceptee() -> None:
    issue = _issue()
    assert (issue["issue"], issue["decision"], issue["montant_rembourse"]) == (
        "decision",
        "acceptee",
        1000.0,
    )
    assert issue["mode_degrade"] is False and len(issue["motif"]) >= 3


def test_regle_1_non_eligible_refusee() -> None:
    issue = _issue(eligibilite={"eligible": False, "conditions_ko": ["contrat non actif"]})
    assert issue["decision"] == "refusee" and issue["montant_rembourse"] == 0.0
    assert "contrat non actif" in issue["motif"]


def test_regle_2_pieces_manquantes_gestionnaire() -> None:
    issue = _issue(pieces={"statut": "manquant", "manquantes": ["photo"]})
    assert (issue["issue"], issue["file"]) == ("escalade", "gestionnaire")
    assert "photo" in issue["motif"]


def test_regle_2_signale_la_borne_de_relance() -> None:
    issue = _issue(
        pieces={"statut": "incomplet", "manquantes": ["facture"]},
        arret={"borne": "relances_pieces_max"},
    )
    assert issue["file"] == "gestionnaire" and "relances_pieces_max" in issue["motif"]


def test_regle_3_estime_nul_refusee() -> None:
    assert _issue(estimation={"estime": 0.0})["decision"] == "refusee"


@pytest.mark.parametrize(
    ("niveau", "file"), [("modere", "gestionnaire"), ("eleve", "cellule_fraude")]
)
def test_regle_4_avis_defavorable_escalade(niveau: str, file: str) -> None:
    avis = {"requis": True, "statut": "avis", "avis": {"niveau": niveau}}
    issue = _issue(avis_fraude=avis)
    assert (issue["issue"], issue["file"]) == ("escalade", file)


def test_regle_4_avis_faible_poursuit() -> None:
    avis = {"requis": True, "statut": "avis", "avis": {"niveau": "faible"}}
    assert _issue(avis_fraude=avis)["decision"] == "acceptee"


def test_mode_degrade_sous_le_seuil_decision_marquee() -> None:
    issue = _issue(
        estimation={"estime": 1350.0},
        avis_fraude={"requis": True, "statut": "indisponible", "avis": None},
    )
    assert issue["decision"] == "acceptee" and issue["mode_degrade"] is True
    assert "§9" in issue["motif"]


def test_mode_degrade_au_dela_du_seuil_cellule_fraude() -> None:
    issue = _issue(
        estimation={"estime": 12_000.0},  # la règle 4 passe avant la règle 5
        avis_fraude={"requis": True, "statut": "indisponible", "avis": None},
    )
    assert (issue["file"], issue["mode_degrade"]) == ("cellule_fraude", True)


def test_regle_5_seuil_de_delegation() -> None:
    issue = _issue(estimation={"estime": 10_500.0})
    assert (issue["issue"], issue["file"]) == ("escalade", "gestionnaire")


def test_escalade_forcee_cite_la_raison() -> None:
    issue = _issue(
        estimation=None,
        avis_fraude=None,
        arret={"borne": "duree_max_s"},
        escalade_forcee="borne duree_max_s atteinte",
    )
    assert (issue["issue"], issue["file"]) == ("escalade", "gestionnaire")
    assert "duree_max_s" in issue["motif"]


def test_borne_violee_jamais_acceptee_meme_sections_completes() -> None:
    issue = _issue(arret={"borne": "etapes_max"})
    assert (issue["issue"], issue["file"]) == ("escalade", "gestionnaire")
    assert "etapes_max" in issue["motif"]


@pytest.mark.parametrize("avis", [{}, {"niveau": "inconnu"}, None])
def test_niveau_d_avis_inconnu_traite_comme_indisponible(avis: dict[str, Any] | None) -> None:
    issue = _issue(
        estimation={"estime": 1350.0},
        avis_fraude={"requis": True, "statut": "avis", "avis": avis},
    )
    assert issue["decision"] == "acceptee" and issue["mode_degrade"] is True


# ------------------------------------------------------------------ frontières


def test_agents_independants_de_la_machine_et_des_autres_modules_d_orchestration() -> None:
    source = (RACINE / "src/kaldera/agents.py").read_text("utf-8")
    importes = {
        noeud.module
        for noeud in ast.walk(ast.parse(source))
        if isinstance(noeud, ast.ImportFrom) and noeud.module
    }
    assert not importes & {"machine", "orchestrateur", "etat"}
