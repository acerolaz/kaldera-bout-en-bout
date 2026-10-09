"""Évaluation des agents LLM (dossier 4.3, niveau ③ ; C2c) : les 28 scénarios rejoués avec chaque
modèle candidat ⇒ matrice agent × modèle, seuils d'alerte du LLM, invariance, bornes remesurées.

Usage : uv run python -m tools.eval_llm (ou make eval). Sans clés Azure : « non mesuré », code 2.
"""

from __future__ import annotations

import json
import math
import time
from collections import Counter
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

import kaldera
from kaldera.disjoncteur import Disjoncteur
from kaldera.etat import BORNES
from kaldera.llm import (
    AGENTS_LLM,
    ClientLLM,
    ConfigAgents,
    ConfigLLM,
    charger_config,
    fabrique_llm,
)
from tools import epreuve

REPETITIONS = 5
# mêmes champs que tests/unit/test_invariance.py (critère d'invariance, C2-Q14c)
DECISIFS = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")
# seuils d'alerte (C2-Q14c), strictement dépassés ; latence : delai_agent_s de l'agent
SEUILS = {"replis": 0.20, "sorties_rejetees": 0.05, "tours_moyen": 2.5}
SANS_TENTATIVE = {"disjoncteur", "budget", "llm_non_configure"}  # le LLM n'a pas été appelé
RAPPORTS = epreuve.RAPPORTS
Fabrique = Callable[[ConfigAgents, str], ClientLLM | None]
SANS_MODELE = (
    "aucun modèle configuré (AZURE_AI_ENDPOINT, AZURE_AI_API_KEY et KALDERA_EVAL__MODELES "
    "ou KALDERA_<AGENT>__MODELE dans le .env)"
)


class ConfigEval(BaseSettings):
    """``KALDERA_EVAL__MODELES=Kimi-K2.6,…`` : modèles candidats, séparés par des virgules."""

    model_config = SettingsConfigDict(
        env_prefix="KALDERA_EVAL__", env_file=".env", extra="ignore"
    )

    modeles: str = ""


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
            "replis sorties_rejetees latence_llm_p95_ms tours_moyen jetons_par_demande".split()
        )
        return {"etapes": 0, **vide, "causes": {}, "alertes": []}
    # seules les étapes qui ont tenté le LLM jugent latence et tours ; une étape « erreur_llm »
    # (délai dépassé ou erreur fournisseur) compte pour l'infini : > 5 % ⇒ p95 > délai ⇒ alerte
    tentees = [e for e in etapes if e["cause"] not in SANS_TENTATIVE]
    latences = sorted(
        math.inf if e["cause"] == "erreur_llm" else e["latence_llm_ms"] for e in tentees
    )
    # les alertes se jugent sur les valeurs brutes ; l'arrondi ne sert qu'à l'affichage
    brut: dict[str, Any] = {
        "replis": sum(e["mode"] == "repli" for e in etapes) / n,
        "sorties_rejetees": sum(bool(e["sortie_rejetee"]) for e in etapes) / n,
        # centile au rang le plus proche, comme metriques_equipe
        "latence_llm_p95_ms": latences[math.ceil(0.95 * len(latences)) - 1] if tentees else None,
        "tours_moyen": sum(e["tours_llm"] for e in tentees) / len(tentees) if tentees else None,
    }
    limites = {**SEUILS, "latence_llm_p95_ms": delai_s * 1000}
    return {
        "etapes": n,
        "replis": round(brut["replis"], 4),
        "sorties_rejetees": round(brut["sorties_rejetees"], 4),
        "latence_llm_p95_ms": brut["latence_llm_p95_ms"],
        "tours_moyen": None if brut["tours_moyen"] is None else round(brut["tours_moyen"], 2),
        "jetons_par_demande": round(sum(e["jetons"] for e in etapes) / len(fiches), 1),
        "causes": dict(Counter(e["cause"] for e in etapes if e["mode"] == "repli")),
        "alertes": [k for k, limite in limites.items() if (v := brut[k]) is not None and v > limite],
    }


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


def _config() -> ConfigAgents:
    try:
        return charger_config()
    except ValueError:  # .env malformé (ValidationError) : rien n'est mesurable
        return ConfigAgents.model_construct()


def _scenarios() -> list[dict[str, Any]]:
    lignes = epreuve.SCENARIOS.read_text("utf-8").splitlines()
    return [json.loads(ligne) for ligne in lignes if ligne.strip()]


def _passe(
    url: str,
    scenarios: list[dict[str, Any]],
    llms: dict[str, ClientLLM | None],
    cfg: ConfigAgents,
) -> list[dict[str, Any]]:
    """Scénarios rejoués avec un disjoncteur neuf (la panne d'un modèle ne gêne pas l'autre)."""
    disjoncteur = Disjoncteur.depuis(BORNES)
    return [
        f
        for s in scenarios
        for f in epreuve.rejouer(url, s, llms=llms, config=cfg, disjoncteur=disjoncteur)["fiches"]
    ]


def _bornes(fiches: list[dict[str, Any]], reference: list[dict[str, Any]]) -> dict[str, Any]:
    equipe = kaldera.metriques_equipe(fiches)
    duree, etapes = equipe["duree_ms"], equipe["etapes"]["max"]
    replis_budget = sum(e.get("cause") == "budget" for f in fiches for e in f["trace"])
    arrets_duree = equipe["arrets"].get("duree_max_s", 0)
    # la référence (sans LLM) fixe les arrêts de durée « normaux » ; ses fiches = une passe
    arrets_ref = kaldera.metriques_equipe(reference)["arrets"].get("duree_max_s", 0)
    arrets_ref *= len(fiches) / len(reference) if reference else 1
    return {
        "duree_p95_ms": duree["p95"],
        "duree_max_ms": duree["max"],
        "duree_max_s": BORNES.duree_max_s,
        "etapes_max": etapes,
        "etapes_borne": BORNES.etapes_max,
        "arrets": equipe["arrets"],
        "disjoncteur": sum(e.get("cause") == "disjoncteur" for f in fiches for e in f["trace"]),
        "replis_budget": replis_budget,
        "ok": duree["max"] < BORNES.duree_max_s * 1000
        and etapes <= BORNES.etapes_max
        and replis_budget == 0
        and arrets_duree <= arrets_ref,
    }


def evaluer(
    scenarios: list[dict[str, Any]] | None = None,
    *,
    cfg: ConfigAgents | None = None,
    brut_modeles: str | None = None,
    fabrique: Fabrique = fabrique_llm,
    repetitions: int = REPETITIONS,
) -> dict[str, Any]:
    cfg = cfg if cfg is not None else _config()
    brut = brut_modeles if brut_modeles is not None else ConfigEval().modeles
    liste = modeles(cfg, brut)
    configs = {m: config_pour(cfg, m) for m in liste}
    clients = {m: {nom: fabrique(c, nom) for nom in AGENTS_LLM} for m, c in configs.items()}
    entete = {"date": date.today().isoformat(), "modeles": liste, "repetitions": repetitions}
    if not any(llm for par_agent in clients.values() for llm in par_agent.values()):
        return {**entete, "mesure": False, "reussi": False, "cause": SANS_MODELE}
    scenarios = scenarios if scenarios is not None else _scenarios()
    debut = time.monotonic()
    with epreuve.partenaire_simule() as url:
        reference = _passe(url, scenarios, {}, ConfigAgents.model_construct())
        passes = {
            m: [_passe(url, scenarios, clients[m], configs[m]) for _ in range(repetitions)]
            for m in liste
        }
    par_modele = {m: [f for p in ps for f in p] for m, ps in passes.items()}
    mat = matrice(par_modele, cfg)
    inv = {m: invariance(reference, ps) for m, ps in passes.items()}
    bornes = {m: _bornes(fiches, reference) for m, fiches in par_modele.items()}
    reussi = (
        all(not c["alertes"] for cases in mat.values() for c in cases.values())
        and all(i["taux"] == 1.0 for i in inv.values())
        and all(b["ok"] for b in bornes.values())
    )
    return {
        **entete,
        "mesure": True,
        "reussi": reussi,
        "scenarios": len(scenarios),
        "duree_s": round(time.monotonic() - debut, 1),
        "matrice": mat,
        "recommandation": recommandation(mat, inv),
        "invariance": inv,
        "bornes": bornes,
    }


def _pct(valeur: float | None) -> str:
    return "—" if valeur is None else f"{valeur * 100:.1f} %"


def _nombre(valeur: float | None, unite: str = "") -> str:
    return "—" if valeur is None else f"{valeur:g}{unite}"


def _verdict(c: dict[str, Any]) -> str:
    if not c["etapes"]:
        return "—"
    return "⚠️ " + ", ".join(c["alertes"]) if c["alertes"] else "✅"


def _ligne_invariance(m: str, i: dict[str, Any]) -> str:
    ecarts = f" — {'; '.join(i['ecarts'][:10])}" if i["ecarts"] else ""
    return f"- {m} : {_pct(i['taux'])}{ecarts}"


def ecrire_rapport(rapport: dict[str, Any], dossier: Path | None = None) -> Path:
    dossier = dossier or RAPPORTS
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"eval-{rapport['date']}.md"
    chemin.with_suffix(".json").write_text(
        json.dumps(rapport, ensure_ascii=False, indent=2, default=str), "utf-8"
    )
    entete = (
        f"# Évaluation LLM — {rapport['date']} · modèles : "
        f"{', '.join(rapport['modeles']) or 'aucun'} · {rapport['repetitions']} répétitions"
    )
    if not rapport["mesure"]:
        lignes = [entete, "", f"**Résultat : non mesuré** · {rapport['cause']}"]
        chemin.write_text("\n".join(lignes) + "\n", "utf-8")
        return chemin
    lignes = [
        entete + f" · {rapport['scenarios']} scénarios",
        "",
        f"**Résultat : {'tout vert' if rapport['reussi'] else 'alertes'}** · "
        f"durée : {rapport['duree_s']} s",
        "",
        "## Matrice agent × modèle",
        "",
        "| Agent | Modèle | Replis | Rejetées | Latence p95 | Tours | Jetons/dem. | Verdict |",
        "|---|---|---|---|---|---|---|---|",
        *(
            f"| {agent} | {m} | {_pct(c['replis'])} | {_pct(c['sorties_rejetees'])} | "
            f"{_nombre(c['latence_llm_p95_ms'], ' ms')} | {_nombre(c['tours_moyen'])} | "
            f"{_nombre(c['jetons_par_demande'])} | {_verdict(c)} |"
            for agent, cases in rapport["matrice"].items()
            for m, c in cases.items()
        ),
        "",
        "## Modèle recommandé par rôle",
        "",
        *(
            f"- {agent} : {m or 'aucun modèle ne passe les seuils'}"
            for agent, m in rapport["recommandation"].items()
        ),
        "",
        "Avis seulement : le `.env` n'est pas modifié ; "
        "un changement de modèle se consigne au journal.",
        "",
        "## Invariance",
        "",
        *(_ligne_invariance(m, i) for m, i in rapport["invariance"].items()),
        "",
        "## Bornes remesurées",
        "",
        "| Modèle | Durée p95 | Durée max | duree_max_s | Étapes max | Arrêts | Disjoncteur | Replis budget | |",
        "|---|---|---|---|---|---|---|---|---|",
        *(
            f"| {m} | {b['duree_p95_ms']} ms | {b['duree_max_ms']} ms | {b['duree_max_s']} s | "
            f"{b['etapes_max']} / {b['etapes_borne']} | {b['arrets'] or '—'} | "
            f"{b['disjoncteur']} | {b['replis_budget']} | {'✅' if b['ok'] else '⚠️'} |"
            for m, b in rapport["bornes"].items()
        ),
    ]
    chemin.write_text("\n".join(lignes) + "\n", "utf-8")
    return chemin


def main() -> None:
    rapport = evaluer()
    chemin = ecrire_rapport(rapport)
    print(chemin.read_text("utf-8"))
    if not rapport["mesure"]:
        raise SystemExit(2)
    if not rapport["reussi"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
