"""traiter_lot : un fil par dossier, un dossier sans anti-fraude ne fait pas la queue (U-07)."""

from __future__ import annotations

import threading
from typing import Any

from kaldera import traiter_lot


class _Orchestrateur:
    def __init__(self) -> None:
        self.rapide_parti = threading.Event()

    def traiter(self, demande: dict[str, Any]) -> dict[str, Any]:
        if demande["lent"]:
            # attend que le dossier rapide soit passé (échoue si tous les fils sont déjà pris)
            assert self.rapide_parti.wait(2), "dossier rapide jamais lancé : pool trop petit"
        else:
            self.rapide_parti.set()
        return {"trace": []}


def test_dossier_rapide_ne_attend_pas_derriere_les_dossiers_lents() -> None:
    demandes = [{"lent": True} for _ in range(40)] + [{"lent": False}]
    lot = traiter_lot(demandes, orchestrateur=_Orchestrateur())  # type: ignore[arg-type]
    assert len(lot["fiches"]) == 41
