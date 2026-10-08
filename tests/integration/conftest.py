"""Fixtures d'intégration de l'API : dépôt sur la base de test, config de dépôt réduite."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from kaldera.api import app, config_ingestion, depot_ingestion
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.vlm import ConfigIngestion


@pytest.fixture
def client(base: Any) -> Iterator[TestClient]:
    app.dependency_overrides[depot_ingestion] = lambda: IngestionPostgres(base)
    app.dependency_overrides[config_ingestion] = lambda: ConfigIngestion(
        _env_file=None, taille_max_mo=1
    )
    yield TestClient(app)
    app.dependency_overrides.clear()
