"""Intégration — lots (spec C3-3 §2.2, §2.3) : lancement tout ou rien, lecture, pièces mixtes."""

from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.lots_postgres import DepotLots, DossiersNonLancables, ReferencesInconnues
from kaldera.postgres import DepotPostgres
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


def _demande(scenario: str) -> dict[str, Any]:
    return copy.deepcopy(SCENARIOS[scenario]["demandes"][0])


def _statuts(base: Any) -> dict[str, str]:
    with base.connection() as conn:
        return dict(conn.execute("SELECT reference, statut FROM demandes").fetchall())


def test_charger_puis_lancer(base: Any) -> None:
    ingestion = IngestionPostgres(base)
    assert ingestion.charger(_demande("NOM-02")) and ingestion.charger(_demande("NOM-03"))
    assert ingestion.charger(_demande("NOM-02")) is False  # déjà en base
    lot_id, demandes = DepotLots(base).lancer(["KAL-26-0103", "KAL-26-0102"])
    assert [d["reference"] for d in demandes] == ["KAL-26-0103", "KAL-26-0102"]
    assert demandes[0]["pieces"] == _demande("NOM-03")["pieces"]  # niveau 0 : pièces incluses
    assert _statuts(base) == {"KAL-26-0102": "en_cours", "KAL-26-0103": "en_cours"}
    lu = DepotLots(base).lire(lot_id)
    assert lu is not None and [d.reference for d in lu.demandes] == ["KAL-26-0102", "KAL-26-0103"]
    assert DepotLots(base).references(lot_id) == ["KAL-26-0102", "KAL-26-0103"]


def test_tout_ou_rien(base: Any) -> None:
    ingestion = IngestionPostgres(base)
    ingestion.charger(_demande("NOM-02"))
    assert ingestion.creer_demande(json_demande(_demande("NOM-03")))  # admission
    with pytest.raises(DossiersNonLancables) as refus:
        DepotLots(base).lancer(["KAL-26-0102", "KAL-26-0103"])
    assert refus.value.references == ["KAL-26-0103"]
    assert _statuts(base) == {"KAL-26-0102": "prete", "KAL-26-0103": "admission"}
    with base.connection() as conn:
        assert conn.execute("SELECT count(*) FROM lots").fetchone() == (0,)
    with pytest.raises(ReferencesInconnues) as inconnues:
        DepotLots(base).lancer(["KAL-26-0102", "KAL-26-9999"])
    assert inconnues.value.references == ["KAL-26-9999"]


def test_un_seul_lancement_concurrent(base: Any) -> None:
    IngestionPostgres(base).charger(_demande("NOM-02"))

    def essai(_: int) -> bool:
        try:
            DepotLots(base).lancer(["KAL-26-0102"])
        except DossiersNonLancables:
            return False
        return True

    with ThreadPoolExecutor(4) as pool:
        assert sum(pool.map(essai, range(4))) == 1


def test_lot_inconnu(base: Any) -> None:
    assert DepotLots(base).lire(999) is None and DepotLots(base).references(999) is None


def test_pieces_de_la_demande_si_table_vide(base: Any) -> None:
    demande = _demande("NOM-01")
    pieces = DepotPostgres(base).initiales(demande)
    assert [(p.type, p.lisible, p.montant) for p in pieces] == [
        (p["type"], p["lisible"], p.get("montant")) for p in demande["pieces"]
    ]
    assert DepotPostgres(base).initiales(json_demande(demande)) == []  # niveau 1 : jamais inline
