"""Évaluation des agents LLM (dossier 4.3, niveau ③ ; C2c) : les 28 scénarios rejoués avec chaque
modèle candidat ⇒ matrice agent × modèle, seuils d'alerte du LLM, invariance, bornes remesurées.

Usage : uv run python -m tools.eval_llm (ou make eval). Sans clés Azure : « non mesuré », code 2.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

from kaldera.llm import AGENTS_LLM, ConfigAgents, ConfigLLM

REPETITIONS = 5
# mêmes champs que tests/unit/test_invariance.py (critère d'invariance, C2-Q14c)
DECISIFS = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")
# seuils d'alerte (C2-Q14c), strictement dépassés ; latence : delai_agent_s de l'agent
SEUILS = {"replis": 0.20, "sorties_rejetees": 0.05, "tours_moyen": 2.5}


def modeles(cfg: ConfigAgents, brut: str) -> list[str]:
    """``KALDERA_EVAL__MODELES`` nettoyé ; à défaut, les modèles distincts des agents."""
    liste = [m.strip() for m in brut.split(",") if m.strip()]
    if not liste:
        liste = [c.modele for nom in AGENTS_LLM if (c := getattr(cfg, nom)) is not None]
    return list(dict.fromkeys(liste))


def config_pour(cfg: ConfigAgents, modele: str) -> ConfigAgents:
    """Les 4 agents sur ``modele`` ; chacun garde son délai, ses jetons et ses tours."""
    maj = {
        nom: (getattr(cfg, nom) or ConfigLLM(modele=modele)).model_copy(update={"modele": modele})
        for nom in AGENTS_LLM
    }
    return cfg.model_copy(update=maj)


def _delai(cfg: ConfigAgents, agent: str) -> float:
    config: ConfigLLM | None = getattr(cfg, agent)
    return (config or ConfigLLM(modele="aucun")).delai_agent_s


def case(fiches: list[dict[str, Any]], agent: str, delai_s: float) -> dict[str, Any]:
    """Mesures d'un agent sur les fiches d'un modèle, et les seuils qu'elles franchissent."""
    etapes = [e for f in fiches for e in f["trace"] if e["agent"] == agent and "mode" in e]
    n = len(etapes)
    if not n:  # agent jamais atteint (court-circuit) : rien à mesurer, rien à recommander
        vide: dict[str, Any] = dict.fromkeys(
            (
                "replis",
                "sorties_rejetees",
                "latence_llm_p95_ms",
                "tours_moyen",
                "jetons_par_demande",
            )
        )
        return {"etapes": 0, **vide, "causes": {}, "alertes": []}
    latences = sorted(e["latence_llm_ms"] for e in etapes)
    mesures: dict[str, Any] = {
        "etapes": n,
        "replis": round(sum(e["mode"] == "repli" for e in etapes) / n, 4),
        "sorties_rejetees": round(sum(bool(e["sortie_rejetee"]) for e in etapes) / n, 4),
        # centile au rang le plus proche, comme metriques_equipe
        "latence_llm_p95_ms": latences[math.ceil(0.95 * n) - 1],
        "tours_moyen": round(sum(e["tours_llm"] for e in etapes) / n, 2),
        "jetons_par_demande": round(sum(e["jetons"] for e in etapes) / len(fiches), 1),
        "causes": dict(Counter(e["cause"] for e in etapes if e["mode"] == "repli")),
    }
    limites = {**SEUILS, "latence_llm_p95_ms": delai_s * 1000}
    mesures["alertes"] = [k for k, limite in limites.items() if mesures[k] > limite]
    return mesures


def matrice(
    par_modele: dict[str, list[dict[str, Any]]], cfg: ConfigAgents
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        agent: {m: case(fiches, agent, _delai(cfg, agent)) for m, fiches in par_modele.items()}
        for agent in AGENTS_LLM
    }


def invariance(
    reference: list[dict[str, Any]], passes: list[list[dict[str, Any]]]
) -> dict[str, Any]:
    """Part des fiches dont les champs décisifs égalent la référence, position par position."""
    paires = [(r, o) for fiches in passes for r, o in zip(reference, fiches, strict=True)]
    ecarts = [
        f"{r['reference']} · {k} : {r[k]!r} → {o[k]!r}"
        for r, o in paires
        for k in DECISIFS
        if o[k] != r[k]
    ]
    conformes = sum(all(o[k] == r[k] for k in DECISIFS) for r, o in paires)
    return {"taux": round(conformes / len(paires), 4) if paires else 0.0, "ecarts": ecarts}


def recommandation(
    mat: dict[str, dict[str, dict[str, Any]]], inv: dict[str, dict[str, Any]]
) -> dict[str, str | None]:
    """Par rôle : parmi les cases vertes à invariance 100 %, le moins de replis, puis de latence."""
    choix: dict[str, str | None] = {}
    for agent, cases in mat.items():
        candidats = [
            (c["replis"], c["latence_llm_p95_ms"], m)
            for m, c in cases.items()
            if c["etapes"] and not c["alertes"] and inv[m]["taux"] == 1.0
        ]
        choix[agent] = min(candidats)[2] if candidats else None
    return choix
