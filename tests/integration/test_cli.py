"""Intégration — make scenarios ARGS=--charger : les scénarios en « prete », sans traitement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.cli import charger
from kaldera.ingestion_postgres import IngestionPostgres
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = [
    json.loads(x) for x in (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines() if x
]


def test_charger_les_scenarios(base: Any) -> None:
    ingestion = IngestionPostgres(base)
    assert ingestion.creer_demande(json_demande(SCENARIOS[0]["demandes"][0]))  # make demo
    chargees, ignorees = charger(SCENARIOS, ingestion)
    assert (chargees, ignorees) == (33, ["KAL-26-0101"])
    with base.connection() as conn:
        statuts = dict(
            conn.execute("SELECT statut, count(*) FROM demandes GROUP BY statut").fetchall()
        )
    assert statuts == {"prete": 33, "admission": 1}
