"""Intégration — POST /traitements et GET /lots (spec C3-3 §2.2, §2.3, §5)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kaldera.ingestion_postgres import IngestionPostgres
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
SCENARIOS = {
    s["id"]: s
    for s in map(json.loads, (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines())
}


@pytest.fixture(autouse=True)
def _partenaire_coupe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")  # jamais le partenaire du poste


def _charger(base: Any, *scenarios: str) -> list[str]:
    ingestion = IngestionPostgres(base)
    demandes = [copy.deepcopy(SCENARIOS[s]["demandes"][0]) for s in scenarios]
    assert all(ingestion.charger(d) for d in demandes)
    return [d["reference"] for d in demandes]


def test_lancer_un_lot_puis_le_lire(client: TestClient, base: Any) -> None:
    references = _charger(base, "NOM-02", "NOM-03")
    reponse = client.post("/traitements", json={"references": references})
    assert reponse.status_code == 202, reponse.text
    assert reponse.json()["references"] == references
    # TestClient exécute la tâche de fond avant de rendre la main
    vue = client.get(f"/lots/{reponse.json()['lot_id']}").json()
    assert vue["avancement"] == 100 and vue["fin"] is not None
    assert {d["reference"]: d["statut"] for d in vue["dossiers"]} == dict.fromkeys(
        references, "terminee"
    )
    assert vue["compteurs"]["refusee"] == 2
    lignes = {lg["reference"]: lg for lg in client.get("/demandes").json()}
    assert lignes["KAL-26-0102"]["selectionnable"] is False
    assert lignes["KAL-26-0102"]["motif_non_selectionnable"] == "Déjà traité"


def test_dossier_seul(client: TestClient, base: Any) -> None:
    (reference,) = _charger(base, "NOM-02")
    reponse = client.post("/traitements", json={"references": [reference]})
    assert reponse.status_code == 202
    vue = client.get(f"/demandes/{reference}").json()
    assert vue["statut"] == "terminee" and vue["avancement"] == 100


def test_tout_ou_rien_409(client: TestClient, base: Any) -> None:
    (prete,) = _charger(base, "NOM-02")
    demande = json_demande(SCENARIOS["NOM-03"]["demandes"][0])
    assert client.post("/demandes", json=demande).status_code == 201  # admission
    reponse = client.post("/traitements", json={"references": [prete, demande["reference"]]})
    assert reponse.status_code == 409
    assert reponse.json() == {"detail": "dossiers non lançables", "references": ["KAL-26-0103"]}
    assert client.get(f"/demandes/{prete}").json()["statut"] == "prete"


def test_relancer_un_dossier_lance_409(client: TestClient, base: Any) -> None:
    (reference,) = _charger(base, "NOM-02")
    assert client.post("/traitements", json={"references": [reference]}).status_code == 202
    second = client.post("/traitements", json={"references": [reference]})
    assert second.status_code == 409 and second.json()["references"] == [reference]
    with base.connection() as conn:
        assert conn.execute("SELECT count(*) FROM lots").fetchone() == (1,)


def test_reference_inconnue_404(client: TestClient) -> None:
    reponse = client.post("/traitements", json={"references": ["KAL-26-9999"]})
    assert reponse.status_code == 404
    assert reponse.json() == {"detail": "demande inconnue", "references": ["KAL-26-9999"]}


@pytest.mark.parametrize(
    "corps",
    [
        {"references": []},
        {"references": ["KAL-26-0102", "KAL-26-0102"]},
        {"references": ["pas-une-reference"]},
        {"references": ["KAL-26-0102"], "auteur": "x"},
    ],
)
def test_corps_invalide_422(client: TestClient, corps: dict[str, Any]) -> None:
    assert client.post("/traitements", json=corps).status_code == 422


def test_lot_inconnu_404(client: TestClient) -> None:
    assert client.get("/lots/999").status_code == 404
    assert client.get("/lots/abc").status_code == 422


def test_filtre_statut_prete(client: TestClient, base: Any) -> None:
    _charger(base, "NOM-02")
    lignes = client.get("/demandes", params={"statut": "prete"}).json()
    assert [(lg["reference"], lg["selectionnable"]) for lg in lignes] == [("KAL-26-0102", True)]
