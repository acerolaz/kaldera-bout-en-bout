"""Critère d'invariance (dossier 4.3) : même issue en mode fake et en mode repli."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.agents_llm import SPECS
from kaldera.llm import fidele
from kaldera.orchestrateur import Orchestrateur

RACINE = Path(__file__).resolve().parents[2]
DEMANDES = [
    pytest.param(d, id=f"{s['id']}-{i}")
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
    for i, d in enumerate(s["demandes"])
]
DECISIFS = ("issue", "decision", "montant_rembourse", "file", "mode_degrade")


def _avis(demande: dict[str, Any], timeout: float) -> dict[str, Any]:
    return {
        "reference_dossier": demande["reference"],
        "score": 0.2,
        "niveau": "faible",
        "indicateurs": [],
        "evaluation_id": "EV-1",
        "version_modele": "v1",
    }


@pytest.mark.parametrize("demande", DEMANDES)
def test_meme_issue_en_fake_et_en_repli(demande: dict[str, Any]) -> None:
    repli = Orchestrateur(evaluer=_avis).traiter(copy.deepcopy(demande))
    llms = {nom: fidele(SPECS[nom].champ, SPECS[nom].gabarit) for nom in SPECS}
    fake = Orchestrateur(evaluer=_avis, llms=llms).traiter(copy.deepcopy(demande))
    assert {k: fake[k] for k in DECISIFS} == {k: repli[k] for k in DECISIFS}
    etapes_llm = [e for e in fake["trace"] if "mode" in e]
    assert etapes_llm, "aucune étape d'agent LLM tracée"
    assert all(e["mode"] == "llm" for e in etapes_llm), [e.get("violations") for e in etapes_llm]
