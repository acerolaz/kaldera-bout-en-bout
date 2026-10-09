"""Unitaires — make eval (C2c) : matrice agent × modèle, seuils du LLM, invariance, rapport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.agents_llm import SPECS
from kaldera.llm import (
    ClientLLM,
    ConfigAgents,
    ConfigLLM,
    FakeLLM,
    ReponseLLM,
    fidele,
    saboteur,
)
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
    repli = _etape("pieces", "repli", cause="garde_fou")
    fiches = [_fiche(*([_etape("pieces")] * 4 + [repli]))]
    c = eval_llm.case(fiches, "pieces", delai_s=1.2)
    mesures = (c["etapes"], c["replis"], c["tours_moyen"], c["jetons_par_demande"])
    assert mesures == (5, 0.2, 2.0, 150.0)
    assert c["causes"] == {"garde_fou": 1} and c["alertes"] == []  # 20 % : vert (strict)


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


def test_case_alerte_sur_la_valeur_brute_non_arrondie() -> None:
    # tours_moyen brut = (101 * 3 + 99 * 2) / 200 = 2.505 > 2.5, mais round(.., 2) peut dire 2.5
    etapes = [_etape("pieces", tours_llm=3)] * 101 + [_etape("pieces", tours_llm=2)] * 99
    c = eval_llm.case([_fiche(*etapes)], "pieces", delai_s=1.2)
    assert "tours_moyen" in c["alertes"]


RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


def _fabrique(cfg: ConfigAgents, nom: str) -> ClientLLM | None:
    """« sain » : rédige fidèlement ; « casse » : JSON invalide à chaque appel."""
    if getattr(cfg, nom).modele == "casse":
        return FakeLLM(lambda m, o: ReponseLLM(texte="{pas du json", jetons=5), modele="casse")
    return fidele(SPECS[nom].champ, SPECS[nom].gabarit)


def _evaluer(brut: str) -> dict[str, Any]:
    return eval_llm.evaluer(
        [SCENARIOS["NOM-01"], SCENARIOS["NOM-07"]],
        cfg=ConfigAgents.model_construct(),
        brut_modeles=brut,
        fabrique=_fabrique,
        repetitions=1,
    )


def test_evaluer_matrice_sain_et_casse(tmp_path: Path) -> None:
    rapport = _evaluer("sain,casse")
    assert rapport["mesure"] and rapport["modeles"] == ["sain", "casse"]
    for agent in eval_llm.AGENTS_LLM:
        assert rapport["matrice"][agent]["sain"]["alertes"] == []
        assert "replis" in rapport["matrice"][agent]["casse"]["alertes"]
        assert rapport["recommandation"][agent] == "sain"
    # le repli rend la référence : l'invariance tient même avec un modèle cassé
    assert rapport["invariance"]["sain"]["taux"] == rapport["invariance"]["casse"]["taux"] == 1.0
    assert rapport["bornes"]["sain"]["ok"] and not rapport["reussi"]
    chemin = eval_llm.ecrire_rapport(rapport, tmp_path)
    texte = chemin.read_text("utf-8")
    for titre in ("Matrice agent × modèle", "Modèle recommandé par rôle", "Invariance",
                  "Bornes remesurées"):
        assert f"## {titre}" in texte
    assert json.loads(chemin.with_suffix(".json").read_text("utf-8"))["modeles"] == [
        "sain", "casse"
    ]


def test_evaluer_tout_vert() -> None:
    rapport = _evaluer("sain")
    assert rapport["reussi"], rapport["matrice"]


def test_sans_cles_non_mesure(tmp_path: Path) -> None:
    rapport = eval_llm.evaluer(cfg=ConfigAgents.model_construct(), brut_modeles="Kimi-K2.6")
    assert not rapport["mesure"] and "aucun modèle configuré" in rapport["cause"]
    texte = eval_llm.ecrire_rapport(rapport, tmp_path).read_text("utf-8")
    assert "non mesuré" in texte and "## Matrice" not in texte


def test_config_malformee_non_mesure(monkeypatch: pytest.MonkeyPatch) -> None:
    def malformee() -> ConfigAgents:
        raise ValueError("KALDERA_PIECES__DELAI_AGENT_S=abc")

    monkeypatch.setattr(eval_llm, "charger_config", malformee)
    rapport = eval_llm.evaluer(brut_modeles="")
    assert not rapport["mesure"]


def test_main_sort_en_2_sans_cles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(eval_llm, "charger_config", ConfigAgents.model_construct)
    monkeypatch.setattr(eval_llm, "RAPPORTS", tmp_path)
    monkeypatch.setenv("KALDERA_EVAL__MODELES", "")
    with pytest.raises(SystemExit) as sortie:
        eval_llm.main()
    assert sortie.value.code == 2
    assert list(tmp_path.glob("eval-*.md"))


def test_case_p95_sur_valeurs_distinctes() -> None:
    etapes = [_etape("pieces", latence_llm_ms=float(i)) for i in range(1, 21)]
    c = eval_llm.case([_fiche(*etapes)], "pieces", delai_s=1.2)
    assert c["latence_llm_p95_ms"] == 19.0  # rang le plus proche


def _erreurs(n_erreur: int, total: int = 100) -> list[dict[str, Any]]:
    return [_etape("pieces", "repli", cause="erreur_llm", latence_llm_ms=0.0)] * n_erreur + [
        _etape("pieces", latence_llm_ms=10.0)
    ] * (total - n_erreur)


def test_case_alerte_latence_quand_plus_de_5_pct_sans_reponse() -> None:
    c = eval_llm.case([_fiche(*_erreurs(15))], "pieces", delai_s=1.2)
    assert c["alertes"] == ["latence_llm_p95_ms"]  # 15 % de replis : sous le seuil des replis


def test_case_pas_d_alerte_latence_sous_5_pct_sans_reponse() -> None:
    c = eval_llm.case([_fiche(*_erreurs(4))], "pieces", delai_s=1.2)
    assert "latence_llm_p95_ms" not in c["alertes"]


def test_case_exclut_les_etapes_sans_tentative_llm() -> None:
    sans = [_etape("pieces", "repli", cause=c, tours_llm=0, latence_llm_ms=0.0)
            for c in ("disjoncteur", "budget", "llm_non_configure")]
    tentee = _etape("pieces", tours_llm=2, latence_llm_ms=50.0)
    c = eval_llm.case([_fiche(*sans, tentee)], "pieces", delai_s=1.2)
    assert (c["etapes"], c["latence_llm_p95_ms"], c["tours_moyen"]) == (4, 50.0, 2.0)
    assert c["replis"] == 0.75
    seul = eval_llm.case([_fiche(*sans)], "pieces", delai_s=1.2)
    assert seul["latence_llm_p95_ms"] is None and seul["tours_moyen"] is None
    assert seul["alertes"] == ["replis"]


def _fiche_bornes(*etapes: dict[str, Any], arret: str | None = None) -> dict[str, Any]:
    f = _fiche(*etapes)
    f["trace"] = [{**e, "duree_ms": 5.0} for e in f["trace"]]
    f["arret"] = {"borne": arret} if arret else None
    return f


def test_bornes_replis_budget_et_arrets_en_plus_font_echouer() -> None:
    ref = [_fiche_bornes(_etape("pieces"))]
    assert eval_llm._bornes(ref, ref)["ok"]
    budget = [_fiche_bornes(_etape("pieces", "repli", cause="budget"))]
    b = eval_llm._bornes(budget, ref)
    assert b["replis_budget"] == 1 and not b["ok"]
    arrete = [_fiche_bornes(_etape("pieces"), arret="duree_max_s")]
    assert not eval_llm._bornes(arrete, ref)["ok"]
    assert eval_llm._bornes(arrete, arrete)["ok"]


def test_invariance_100_pct_avec_un_menteur() -> None:
    mensonges = {
        "pieces": {"statut": "manquant"},
        "estimation": {"estime": 1.0},
        "antifraude": {"requis": False},
        "decision": {"file": "autre_file"},
    }

    def menteur(cfg: ConfigAgents, nom: str) -> ClientLLM | None:
        return saboteur("menteur", SPECS[nom].champ, SPECS[nom].gabarit, mensonges[nom])

    rapport = eval_llm.evaluer(
        [SCENARIOS["NOM-01"], SCENARIOS["NOM-07"]],
        cfg=ConfigAgents.model_construct(),
        brut_modeles="menteur",
        fabrique=menteur,
        repetitions=1,
    )
    assert rapport["invariance"]["menteur"]["taux"] == 1.0
    # antifraude : « requis: False » égale la référence de ces scénarios, donc accepté (0 repli)
    for agent in ("pieces", "estimation", "decision"):
        assert "replis" in rapport["matrice"][agent]["menteur"]["alertes"], agent
