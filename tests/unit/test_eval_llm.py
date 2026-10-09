"""Unitaires — make eval (C2c) : matrice agent × modèle, seuils du LLM, invariance, rapport."""

from __future__ import annotations

from typing import Any

from kaldera.llm import ConfigAgents, ConfigLLM
from tools import eval_llm


def _etape(agent: str, mode: str = "llm", **champs: Any) -> dict[str, Any]:
    return {
        "agent": agent,
        "mode": mode,
        "cause": None if mode == "llm" else champs.pop("cause", "erreur_llm"),
        "sortie_rejetee": False,
        "latence_llm_ms": 100.0,
        "tours_llm": 2,
        "jetons": 30,
        **champs,
    }


def _fiche(*etapes: dict[str, Any], **decisifs: Any) -> dict[str, Any]:
    base = {
        "reference": "R1",
        "issue": "decision",
        "decision": "acceptee",
        "montant_rembourse": 750.0,
        "file": None,
        "mode_degrade": False,
    }
    return {**base, **decisifs, "trace": list(etapes)}


def test_modeles_nettoyes() -> None:
    cfg = ConfigAgents.model_construct()
    assert eval_llm.modeles(cfg, " a, ,b,a ,") == ["a", "b"]


def test_modeles_par_defaut_ceux_des_agents() -> None:
    cfg = ConfigAgents.model_construct(
        pieces=ConfigLLM(modele="A"),
        estimation=ConfigLLM(modele="B"),
        decision=ConfigLLM(modele="A"),
    )
    assert eval_llm.modeles(cfg, "") == ["A", "B"]
    assert eval_llm.modeles(ConfigAgents.model_construct(), "  ") == []


def test_config_pour_garde_les_bornes_de_chaque_agent() -> None:
    cfg = ConfigAgents.model_construct(
        pieces=ConfigLLM(modele="A", delai_agent_s=1.2, tours_max=3),
        estimation=ConfigLLM(modele="A", delai_agent_s=0.8, tours_max=2),
    )
    clone = eval_llm.config_pour(cfg, "M")
    assert all(getattr(clone, nom).modele == "M" for nom in ("pieces", "estimation", "decision"))
    assert (clone.pieces.delai_agent_s, clone.estimation.tours_max) == (1.2, 2)
    assert cfg.pieces is not None and cfg.pieces.modele == "A"  # l'original n'est pas modifié


def test_case_mesures_et_seuils_a_la_limite() -> None:
    fiches = [_fiche(*([_etape("pieces")] * 4 + [_etape("pieces", "repli")]))]
    c = eval_llm.case(fiches, "pieces", delai_s=1.2)
    mesures = (c["etapes"], c["replis"], c["tours_moyen"], c["jetons_par_demande"])
    assert mesures == (5, 0.2, 2.0, 150.0)
    assert c["causes"] == {"erreur_llm": 1} and c["alertes"] == []  # 20 % : vert (strict)


def test_case_alertes_au_dessus_des_seuils() -> None:
    etapes = [
        _etape(
            "pieces",
            "repli",
            sortie_rejetee=True,
            cause="garde_fou",
            tours_llm=3,
            latence_llm_ms=1500.0,
        ),
        _etape("pieces", "repli", cause="erreur_llm", tours_llm=3, latence_llm_ms=1500.0),
        _etape("pieces", tours_llm=3, latence_llm_ms=1500.0),
    ]
    c = eval_llm.case([_fiche(*etapes)], "pieces", delai_s=1.2)
    assert set(c["alertes"]) == {"replis", "sorties_rejetees", "latence_llm_p95_ms", "tours_moyen"}


def test_case_sans_etape() -> None:
    c = eval_llm.case([_fiche(_etape("pieces"))], "antifraude", delai_s=1.5)
    assert c["etapes"] == 0 and c["replis"] is None and c["alertes"] == []


def test_invariance_par_position() -> None:
    reference = [_fiche(), _fiche(issue="escalade", file="fraude")]  # même référence « R1 »
    conforme = [_fiche(), _fiche(issue="escalade", file="fraude")]
    inverse = [_fiche(issue="escalade", file="fraude"), _fiche()]
    inv = eval_llm.invariance(reference, [conforme, inverse])
    assert inv["taux"] == 0.5
    assert inv["ecarts"][0] == "R1 · issue : 'decision' → 'escalade'"


def test_recommandation_le_moins_de_replis_parmi_les_cases_vertes() -> None:
    vert = {"etapes": 4, "replis": 0.1, "latence_llm_p95_ms": 900.0, "alertes": []}
    mat = {
        "pieces": {
            "A": {**vert, "replis": 0.15},
            "B": vert,
            "C": {**vert, "replis": 0.0, "alertes": ["tours_moyen"]},
            "D": {**vert, "replis": 0.0},  # invariance < 100 % : écarté
        },
        "antifraude": {"A": {**vert, "etapes": 0, "replis": None}},
    }
    inv = {"A": {"taux": 1.0}, "B": {"taux": 1.0}, "C": {"taux": 1.0}, "D": {"taux": 0.9}}
    assert eval_llm.recommandation(mat, inv) == {"pieces": "B", "antifraude": None}
