"""Test de fumée manuel (hors CI) : 3 demandes nominales avec les vrais LLM du .env.

Usage : uv run python scripts/fumee_llm.py
"""

from __future__ import annotations

import json
from pathlib import Path

from kaldera.llm import AGENTS_LLM, charger_config, fabrique_llm
from kaldera.orchestrateur import Orchestrateur

RACINE = Path(__file__).resolve().parents[1]


def main() -> None:
    cfg = charger_config()
    llms = {nom: fabrique_llm(cfg, nom) for nom in AGENTS_LLM}
    if not any(llms.values()):
        print(
            "Aucun agent configuré : renseigner AZURE_AI_CHAT_* et KALDERA_<AGENT>__MODELE "
            "dans .env"
        )
        return
    scenarios = map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
    nominaux = [d for s in scenarios if s["categorie"] == "nominal" for d in s["demandes"]][:3]
    orchestrateur = Orchestrateur(config=cfg, llms=llms)
    for demande in nominaux:
        fiche = orchestrateur.traiter(demande)
        print(f"\n{fiche['reference']} → {fiche['issue']} ({fiche['file'] or fiche['decision']})")
        for e in (e for e in fiche["trace"] if "mode" in e):
            print(
                f"  {e['agent']:<11} {e['mode']:<6} {e['cause'] or '':<18} "
                f"{e['modele'] or '-':<12} {e['latence_llm_ms']:>8.1f} ms  {e['violations']}"
            )


if __name__ == "__main__":
    main()
