"""Unitaires — pièces par référence (dossier 2.4 bis)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from kaldera.espace_assure import depot_pour
from kaldera.memoire import DepotDepuisDemande
from kaldera.ports import PieceRef

DEMANDE = {
    "reference": "KAL-26-0107",
    "pieces": [{"type": "facture", "lisible": True, "montant": 640.0}],
    "espace_assure": {
        "depots": [
            {"type": "photo", "lisible": False},
            {"type": "photo", "lisible": True},
        ]
    },
}


def test_piece_en_echec_d_analyse_est_illisible() -> None:
    piece = PieceRef(type="photo", lisible=True, statut_analyse="echec")
    assert piece.lisible is False


def test_piece_de_type_inconnu_refusee() -> None:
    with pytest.raises(ValidationError):
        PieceRef.model_validate({"type": "devis", "lisible": True})


def test_depot_niveau_0_lit_la_demande() -> None:
    depot = DepotDepuisDemande()
    assert depot.initiales(DEMANDE) == [PieceRef(type="facture", lisible=True, montant=640.0)]
    assert [p.lisible for p in depot.depots(DEMANDE)] == [False, True]
    assert depot.initiales({}) == [] and depot.depots({}) == []


@pytest.mark.parametrize(
    ("tentative", "lisible"),
    [(0, False), (1, True), (5, True)],  # au-delà : l'assuré re-soumet son dernier dépôt
)
def test_depot_pour_la_tentative(tentative: int, lisible: bool) -> None:
    depots = DEMANDE["espace_assure"]["depots"]
    assert depot_pour(depots, "photo", tentative) == {"type": "photo", "lisible": lisible}


def test_depot_pour_un_type_jamais_depose() -> None:
    assert depot_pour(DEMANDE["espace_assure"]["depots"], "facture", 0) is None
