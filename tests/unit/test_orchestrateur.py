"""Unitaires — le moteur : « les agents proposent, l'orchestration impose » (dossier 2.2 bis)."""

from __future__ import annotations

import copy
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

import kaldera
from kaldera import partenaire
from kaldera.agents import AgentDecision, AgentEstimation, AgentPieces
from kaldera.agents_llm import SPECS, AgentLLM
from kaldera.etat import Bornes, EtatDemande
from kaldera.llm import fidele
from kaldera.machine import Etat
from kaldera.orchestrateur import ErreurEcriture, Orchestrateur, fusionner

RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


def _demande(scenario: str, rang: int = 0) -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][rang])


def _sans_partenaire(demande: dict[str, Any], timeout: float) -> None:
    raise AssertionError("aucun appel au partenaire attendu")


def _orchestrateur(
    bornes: Bornes | None = None, evaluer: Any = _sans_partenaire, **remplacements: Any
) -> Orchestrateur:
    orch = Orchestrateur(bornes=bornes, evaluer=evaluer)
    orch.actions.update({Etat[nom.upper()]: action for nom, action in remplacements.items()})
    return orch


def _actions(fiche: dict[str, Any]) -> list[str]:
    return [etape["action"] for etape in fiche["trace"]]


# --------------------------------------------------------------------- parcours


def test_non_eligible_va_droit_a_la_decision() -> None:
    fiche = _orchestrateur().traiter(_demande("NOM-02"))
    assert fiche["decision"] == "refusee"
    assert [(e["de"], e["vers"]) for e in fiche["trace"]] == [
        ("eligibilite", "decision"),
        ("decision", "refusee"),
    ]


def test_un_agent_par_section_dans_la_trace() -> None:
    fiche = _orchestrateur().traiter(_demande("NOM-01"))
    assert [(e["agent"], e["ecrit"]) for e in fiche["trace"]] == [
        ("orchestrateur", ["eligibilite"]),
        ("pieces", ["pieces"]),
        ("estimation", ["estimation"]),
        ("antifraude", ["avis_fraude"]),
        ("decision", ["issue"]),
    ]
    assert fiche["decision"] == "acceptee" and fiche["arret"] is None


def test_relance_bornee_signale_l_arret() -> None:
    fiche = _orchestrateur().traiter(_demande("BCL-01"))
    assert _actions(fiche) == ["eligibilite", "pieces", "pieces", "decision"]
    assert fiche["issue"] == "escalade" and fiche["arret"]["borne"] == "relances_pieces_max"


def test_relance_reussie_sans_arret() -> None:
    fiche = _orchestrateur().traiter(_demande("NOM-07"))
    assert fiche["decision"] == "acceptee" and fiche["arret"] is None
    assert _actions(fiche).count("pieces") == 2


def test_la_demande_d_origine_n_est_jamais_modifiee() -> None:
    demande = _demande("NOM-07")
    avant = copy.deepcopy(demande)
    _orchestrateur().traiter(demande)
    assert demande == avant


# --------------------------------------------------------------------- frontières


def test_antifraude_ne_voit_ni_identite_ni_texte_libre_ni_pieces() -> None:
    vues: list[dict[str, Any]] = []

    def espion(vue: dict[str, Any]) -> dict[str, Any]:
        vues.append(vue)
        return {"avis_fraude": {"requis": False, "statut": "non_requis"}}

    _orchestrateur(antifraude=espion).traiter(_demande("NOM-01"))
    (vue,) = vues
    demande = vue["demande"]
    assert demande["assure"] == {"code_postal": _demande("NOM-01")["assure"]["code_postal"]}
    assert "description" not in demande["sinistre"] and "numero" not in demande["contrat"]
    assert "pieces" not in demande and "espace_assure" not in demande


def test_patch_hors_de_sa_section_rejete_puis_escalade_forcee() -> None:
    def empietant(vue: dict[str, Any]) -> dict[str, Any]:
        return {
            "estimation": {"justifie": 0, "retenu": 0, "franchise": 0, "plafond": 0, "estime": 0}
        }

    fiche = _orchestrateur(pieces=empietant).traiter(_demande("NOM-01"))
    etape = fiche["trace"][1]
    assert (etape["agent"], etape["statut"], etape["ecrit"]) == ("pieces", "echec", [])
    assert fiche["issue"] == "escalade" and "pieces" in fiche["motif"]
    assert _actions(fiche) == ["eligibilite", "pieces", "decision"]


def test_agent_en_erreur_escalade_forcee_sans_planter() -> None:
    def en_panne(vue: dict[str, Any]) -> dict[str, Any]:
        raise KeyError("formule")

    fiche = _orchestrateur(estimation=en_panne).traiter(_demande("NOM-01"))
    assert fiche["trace"][-2]["statut"] == "echec"
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")


def test_decision_en_erreur_fiche_de_secours() -> None:
    def en_panne(vue: dict[str, Any]) -> dict[str, Any]:
        raise TypeError("bug")

    fiche = _orchestrateur(decision=en_panne).traiter(_demande("NOM-01"))
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")
    assert "decision" in fiche["motif"]


def test_reecrire_une_section_deja_remplie_est_refuse() -> None:
    etat = EtatDemande(demande=_demande("NOM-01"))
    estimation = {"justifie": 1, "retenu": 1, "franchise": 0, "plafond": 9, "estime": 1}
    fusionner(etat, {"estimation": estimation}, "estimation")
    with pytest.raises(ErreurEcriture):
        fusionner(etat, {"estimation": estimation}, "estimation")


def test_la_relance_peut_reecrire_les_pieces() -> None:
    etat = EtatDemande(demande=_demande("NOM-01"))
    fusionner(etat, {"pieces": {"statut": "incomplet"}}, "pieces")
    fusionner(etat, {"pieces": {"statut": "complet"}}, "pieces")
    assert etat.pieces is not None and etat.pieces.statut == "complet"


# --------------------------------------------------------------------- garde globale


def test_garde_globale_sur_les_etapes() -> None:
    def toujours_incomplet(vue: dict[str, Any]) -> dict[str, Any]:
        return {"pieces": {"statut": "incomplet", "manquantes": ["facture"]}}

    bornes = Bornes(etapes_max=4, relances_pieces_max=50)
    fiche = _orchestrateur(bornes, pieces=toujours_incomplet).traiter(_demande("NOM-01"))
    assert fiche["arret"]["borne"] == "etapes_max"
    assert len(fiche["trace"]) <= bornes.etapes_max
    assert fiche["issue"] == "escalade" and fiche["trace"][-1]["agent"] == "decision"


def test_garde_globale_sur_la_duree() -> None:
    def lent(vue: dict[str, Any]) -> dict[str, Any]:
        time.sleep(0.05)
        return AgentPieces()(vue)

    bornes = Bornes(duree_max_s=0.01)
    fiche = _orchestrateur(bornes, pieces=lent).traiter(_demande("NOM-01"))
    assert fiche["arret"]["borne"] == "duree_max_s" and fiche["arret"]["etat"] == "estimation"
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")
    assert "duree_max_s" in fiche["motif"]


def test_decision_toujours_executee_meme_borne_depassee() -> None:
    bornes = Bornes(duree_max_s=1e-9)
    fiche = _orchestrateur(bornes).traiter(_demande("NOM-01"))
    assert _actions(fiche) == ["decision"] and fiche["issue"] == "escalade"


# --------------------------------------------------------------------- métriques


def test_appel_externe_et_echec_comptes_dans_la_trace() -> None:
    orch = _orchestrateur(evaluer=lambda demande, timeout: None)
    fiche = orch.traiter(_demande("PAN-01", 3))  # 8 800 € : F1
    etape = next(e for e in fiche["trace"] if e["agent"] == "antifraude")
    assert (etape["appels_externes"], etape["statut"]) == (1, "echec")
    assert fiche["mode_degrade"] is True and fiche["file"] == "cellule_fraude"


# --------------------------------------------------------------------- robustesse (revue T4)


def test_section_vide_rejetee_sans_planter() -> None:
    fiche = _orchestrateur(eligibilite=lambda vue: {"eligibilite": None}).traiter(
        _demande("NOM-01")
    )
    assert fiche["trace"][0]["statut"] == "echec"
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")


def test_agent_qui_leve_attribute_error_escalade_sans_planter() -> None:
    def casse(vue: dict[str, Any]) -> dict[str, Any]:
        raise AttributeError("bug")

    fiche = _orchestrateur(pieces=casse).traiter(_demande("NOM-01"))
    assert fiche["issue"] == "escalade" and "pieces" in fiche["motif"]


def test_appel_partenaire_plafonne_par_le_temps_restant() -> None:
    delais: list[float] = []

    def espion(demande: dict[str, Any], timeout: float) -> None:
        delais.append(timeout)

    bornes = Bornes(duree_max_s=0.5, delai_partenaire_s=3)
    _orchestrateur(bornes, evaluer=espion).traiter(_demande("PAN-01", 3))  # F1 : appel requis
    (delai,) = delais
    assert 0 < delai <= 0.5


def test_agents_par_defaut() -> None:
    actions = Orchestrateur().actions
    assert isinstance(actions[Etat.PIECES], AgentLLM)
    assert isinstance(actions[Etat.PIECES].repli, AgentPieces)
    assert isinstance(actions[Etat.ESTIMATION].repli, AgentEstimation)
    assert isinstance(actions[Etat.DECISION].repli, AgentDecision)
    assert all(a.llm is None for e, a in actions.items() if e is not Etat.ELIGIBILITE)


def test_budget_degressif() -> None:
    orch = Orchestrateur(bornes=Bornes())
    etat = EtatDemande(demande=_demande("NOM-01"))
    assert orch._budget(etat, Etat.PIECES) == pytest.approx(8 - 3 - 1, abs=0.05)
    assert orch._budget(etat, Etat.ESTIMATION) == pytest.approx(4, abs=0.05)
    assert orch._budget(etat, Etat.ANTIFRAUDE) == pytest.approx(7, abs=0.05)
    assert orch._budget(etat, Etat.DECISION) == pytest.approx(8, abs=0.05)


def _avis_faible(demande: dict[str, Any], timeout: float) -> dict[str, Any]:
    return {
        "reference_dossier": demande["reference"],
        "score": 0.2,
        "niveau": "faible",
        "indicateurs": [],
        "evaluation_id": "EV-1",
        "version_modele": "v1",
    }


def test_trace_porte_la_mesure_des_agents_llm() -> None:
    llms = {nom: fidele(SPECS[nom].champ, SPECS[nom].gabarit) for nom in SPECS}
    fiche = Orchestrateur(evaluer=_avis_faible, llms=llms).traiter(_demande("NOM-01"))
    etapes = [e for e in fiche["trace"] if e["agent"] != "orchestrateur"]
    assert etapes and all(e["mode"] == "llm" and e["modele"] == "fake" for e in etapes)
    assert all(len(e["version_prompt"]) == 8 and e["tours_llm"] == 2 for e in etapes)
    eligibilite = next(e for e in fiche["trace"] if e["agent"] == "orchestrateur")
    assert "mode" not in eligibilite


def test_sans_llm_les_agents_tracent_le_repli() -> None:
    fiche = Orchestrateur(evaluer=_avis_faible).traiter(_demande("NOM-01"))
    etapes = [e for e in fiche["trace"] if e["agent"] != "orchestrateur"]
    assert all((e["mode"], e["cause"]) == ("repli", "llm_non_configure") for e in etapes)


# --------------------------------------------------------------------- partenaire


def test_partenaire_muet_abandonne_au_delai() -> None:
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen()  # accepte la connexion, ne répond jamais
    try:
        debut = time.monotonic()
        avis = partenaire.evaluer_risque(
            {"reference": "KAL-26-0000"},
            f"http://127.0.0.1:{serveur.getsockname()[1]}",
            timeout=0.3,
        )
        assert avis is None and time.monotonic() - debut < 2
    finally:
        serveur.close()


def test_partenaire_au_compte_gouttes_abandonne_au_delai_total(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """httpx borne chaque lecture, pas la durée totale : l'échéance doit être globale."""
    monkeypatch.setenv("PARTENAIRE_JETON", "jeton-de-test")  # sinon en-tête illégal, échec immédiat
    serveur = socket.socket()
    serveur.bind(("127.0.0.1", 0))
    serveur.listen()
    arret = threading.Event()

    def goutte_a_goutte() -> None:
        connexion, _ = serveur.accept()
        connexion.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n")
        while not arret.wait(0.1):  # un octet toutes les 100 ms, bien sous le délai par lecture
            try:
                connexion.sendall(b" ")
            except OSError:
                break
        connexion.close()

    threading.Thread(target=goutte_a_goutte, daemon=True).start()
    try:
        debut = time.monotonic()
        avis = partenaire.evaluer_risque(
            {"reference": "KAL-26-0000"},
            f"http://127.0.0.1:{serveur.getsockname()[1]}",
            timeout=0.5,
        )
        assert avis is None and time.monotonic() - debut < 1.0
    finally:
        arret.set()
        serveur.close()


# --------------------------------------------------------------------- entrée malformée (EX-01)


@pytest.mark.parametrize("demande", [{}, {"reference": "KAL-26-9999"}, {"contrat": "?"}])
def test_demande_malformee_escalade_motivee_sans_planter(demande: dict[str, Any]) -> None:
    fiche = kaldera.traiter_demande(demande)
    assert fiche["reference"] == demande.get("reference")
    assert (fiche["issue"], fiche["file"]) == ("escalade", "gestionnaire")
    assert len(fiche["motif"]) >= 3


def test_config_invalide_replie_sans_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KALDERA_PIECES__DELAI_AGENT_S", "abc")
    fiche = Orchestrateur(evaluer=_avis_faible).traiter(_demande("NOM-01"))
    etapes = [e for e in fiche["trace"] if e["agent"] != "orchestrateur"]
    assert etapes and all(e["cause"] == "llm_non_configure" for e in etapes)
