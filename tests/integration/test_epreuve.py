"""Intégration — chaîne complète avec un FakeVLM fidèle : seed → worker → épreuve verte."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kaldera.api import app, config_ingestion, depot_ingestion
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.vlm import ConfigIngestion, FakeVLM
from kaldera.worker import travailler
from kaldera.disjoncteur import Disjoncteur
from kaldera.etat import BORNES
from tools.eval_ingestion import ecrire_rapport, evaluer
from tools.seed import attendre, deposer, lire_manifeste, verites_fake

pytestmark = pytest.mark.integration
CONFIG = ConfigIngestion(_env_file=None, delai_analyse_s=0.05)


@pytest.fixture
def api(base: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")  # partenaire indisponible
    app.dependency_overrides[depot_ingestion] = lambda: IngestionPostgres(base)
    app.dependency_overrides[config_ingestion] = lambda: ConfigIngestion(_env_file=None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_chaine_complete_fakevlm(api: TestClient, base: Any, tmp_path: Path) -> None:
    manifeste = lire_manifeste()
    references = deposer(api, manifeste)
    ingestion, vlm = IngestionPostgres(base), FakeVLM(verites_fake(manifeste))
    while travailler(ingestion, vlm, CONFIG, Disjoncteur.depuis(BORNES)):
        pass
    attendre(api, references, attente_s=0, pause_s=0)
    rapport = evaluer(base, manifeste)
    assert rapport["invariance"]["divergences"] == []
    assert rapport["invariance"]["scenarios_ok"] == rapport["invariance"]["scenarios"] == 28
    assert all(ok == total for ok, total in rapport["contrats"].values()), rapport["contrats"]
    assert rapport["ing"] == {f"ING-0{i}": True for i in range(1, 6)}, rapport["ing"]
    assert rapport["protocole"] is True and rapport["reussi"] is True
    chemin = ecrire_rapport(rapport, tmp_path)
    assert chemin.suffix == ".md" and chemin.with_suffix(".json").exists()
    assert "28/28" in chemin.read_text("utf-8")


def test_epreuve_sur_base_vide(base: Any) -> None:
    rapport = evaluer(base, lire_manifeste())
    assert rapport["reussi"] is False
    assert rapport["invariance"]["scenarios_ok"] == 0
    assert any("absente" in d["raison"] for d in rapport["invariance"]["divergences"])


def test_numero_mesure_par_le_verrou_1(api: TestClient, base: Any) -> None:
    manifeste = [x for x in lire_manifeste() if x["reference"] == "KAL-26-0101"]
    deposer(api, manifeste)
    ingestion, vlm = IngestionPostgres(base), FakeVLM(verites_fake(manifeste))
    while travailler(ingestion, vlm, CONFIG, Disjoncteur.depuis(BORNES)):
        pass
    with base.connection() as conn:  # le VLM a lu un autre numéro que celui de la demande
        conn.execute("UPDATE contrats SET violations = '{\"① numéro ≠ demande\"}'")
    assert evaluer(base, manifeste)["contrats"]["numero"] == (0, 1)
