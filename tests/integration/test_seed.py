"""Intégration — seed : le manifeste rejoué par l'API, codes HTTP contrôlés (dossier 2.7)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kaldera.api import app, config_ingestion, depot_ingestion
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.vlm import ConfigIngestion, FakeVLM
from kaldera.worker import travailler
from tools.seed import EchecSeed, attendre, deposer, lire_manifeste, verites_fake

pytestmark = pytest.mark.integration
CONFIG = ConfigIngestion(_env_file=None, delai_analyse_s=0.05)


@pytest.fixture
def api(base: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")  # partenaire indisponible
    app.dependency_overrides[depot_ingestion] = lambda: IngestionPostgres(base)
    app.dependency_overrides[config_ingestion] = lambda: ConfigIngestion(_env_file=None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def _extrait(manifeste: list[dict[str, Any]], *references: str) -> list[dict[str, Any]]:
    return [x for x in manifeste if x["reference"] in references]


def test_seed_puis_traitement(api: TestClient, base: Any) -> None:
    manifeste = _extrait(lire_manifeste(), "KAL-26-0101", "KAL-26-0904", "KAL-26-0905")
    references = deposer(api, manifeste)
    assert references == ["KAL-26-0101", "KAL-26-0904", "KAL-26-0905"]
    with pytest.raises(EchecSeed, match="délai"):
        attendre(api, references, attente_s=0, pause_s=0)  # rien n'est encore traité
    ingestion, vlm = IngestionPostgres(base), FakeVLM(verites_fake(manifeste))
    while travailler(ingestion, vlm, CONFIG):
        pass
    attendre(api, references, attente_s=0, pause_s=0)


def test_base_deja_semee(api: TestClient) -> None:
    manifeste = _extrait(lire_manifeste(), "KAL-26-0101")
    deposer(api, manifeste)
    with pytest.raises(EchecSeed, match="base déjà semée"):
        deposer(api, manifeste)


def test_code_http_inattendu(api: TestClient) -> None:
    manifeste = _extrait(lire_manifeste(), "KAL-26-0905")
    for ligne in manifeste:
        if ligne.get("http") == 415:
            ligne["http"] = 202  # on prétend que l'exécutable doit passer
    with pytest.raises(EchecSeed, match="415"):
        deposer(api, manifeste)


def test_verites_fake() -> None:
    verites = verites_fake(lire_manifeste())
    contrats = [x for x in lire_manifeste() if x["role"] == "contrat"]
    floue = next(x for x in contrats if x["variante"] == "scannee_floue")
    nette = next(x for x in contrats if x["variante"] == "nette")
    assert verites[floue["sha256"]] == {"illisible": True}
    assert verites[nette["sha256"]] == nette["attendu"]
