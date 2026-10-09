"""Intégration — démonstration : une demande, son contrat en analyse, un compte assuré rattaché."""

from __future__ import annotations

from typing import Any

import pytest

from kaldera import auth
from kaldera.assure_postgres import DepotAssure
from tools.demo_assure import MOT_DE_PASSE, preparer

pytestmark = pytest.mark.integration


def test_preparer_puis_refuser_une_seconde_fois(base: Any) -> None:
    assert preparer(base) is True
    depot = DepotAssure(base)
    compte = auth.authentifier(depot, "claire", MOT_DE_PASSE)
    assert compte is not None and depot.demandes_de(compte.id) == ["KAL-26-0101"]
    with base.connection() as conn:
        (taches,) = conn.execute(
            "SELECT count(*) FROM file_ingestion WHERE tache = 'extraire_contrat'"
        ).fetchone()
    assert taches == 1 and preparer(base) is False
