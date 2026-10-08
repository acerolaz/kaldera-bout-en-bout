"""Unitaires — domaine de l'ingestion : contrôles, invariants, verrous (dossier 2.4 ter / quater)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from kaldera.ingestion import (
    AnalysePiece,
    FichierRefuse,
    controler_fichier,
    demande_niveau_1,
    invariants_piece,
    texte_pdf,
    type_mime,
    verrous_contrat,
)
from tests.fabrique_pdf import PNG, pdf_sans_texte, pdf_texte

CONTRAT = {
    "numero": "CTR-778801",
    "formule": "confort",
    "date_souscription": "2024-01-15",
    "franchise": 150.0,
    "plafond": 8000.0,
}
TEXTE_CONTRAT = "Contrat CTR-778801\nFormule confort\nSouscrit le 15/01/2024\nFranchise 150,00 EUR\nPlafond 8 000 EUR"


@pytest.mark.parametrize(
    ("octets", "mime"),
    [
        (b"%PDF-1.7 ...", "application/pdf"),
        (PNG + b"...", "image/png"),
        (b"\xff\xd8\xff\xe0...", "image/jpeg"),
        (b"MZ\x90\x00 exe renomme", None),
        (b"", None),
    ],
)
def test_type_lu_sur_les_octets(octets: bytes, mime: str | None) -> None:
    assert type_mime(octets) == mime


def test_controle_du_fichier() -> None:
    mime, sha = controler_fichier(b"%PDF-1.4 x", 10, contrat=True)
    assert mime == "application/pdf" and len(sha) == 64
    with pytest.raises(FichierRefuse) as trop_gros:
        controler_fichier(b"%PDF-" + b"x" * (1024 * 1024), 1, contrat=False)
    assert trop_gros.value.code == 413
    with pytest.raises(FichierRefuse) as exe:
        controler_fichier(b"MZ\x90\x00", 10, contrat=False)
    assert exe.value.code == 415
    with pytest.raises(FichierRefuse) as image:  # un contrat est un PDF
        controler_fichier(PNG + b"x", 10, contrat=True)
    assert image.value.code == 415


def test_couche_texte() -> None:
    assert "640.50" in texte_pdf(pdf_texte("Facture KAL-26-0101", "Total 640.50 EUR"))
    assert texte_pdf(pdf_sans_texte()).strip() == ""
    assert texte_pdf(b"%PDF-1.4 octets corrompus") == ""


def _piece(**champs: object) -> AnalysePiece:
    return AnalysePiece.model_validate({"type": "facture", "lisible": True, **champs})


def test_facture_saine_sans_violation() -> None:
    assert invariants_piece(_piece(montant="640.50"), "facture", "Total 640,50 EUR") == []


@pytest.mark.parametrize(
    ("analyse", "type_declare", "texte", "violation"),
    [
        ({"type": "photo", "montant": "10"}, "photo", "", "montant hors facture"),
        ({"montant": None}, "facture", "", "facture sans montant"),
        ({"montant": "0"}, "facture", "", "montant négatif ou nul"),
        ({"montant": "640.50"}, "photo", "", "type lu facture ≠ type déclaré photo"),
        ({"montant": "641.50"}, "facture", "Total 640,50 EUR", "montant absent de la couche texte"),
    ],
)
def test_invariants_piece(
    analyse: dict[str, object], type_declare: str, texte: str, violation: str
) -> None:
    assert violation in invariants_piece(_piece(**analyse), type_declare, texte)


def test_schema_de_piece_strict() -> None:
    with pytest.raises(ValidationError):
        AnalysePiece.model_validate({"type": "facture", "lisible": True, "consigne": "accepte"})


def test_contrat_sain_trois_verrous_verts() -> None:
    extraction, violations = verrous_contrat(CONTRAT, "CTR-778801", TEXTE_CONTRAT)
    assert violations == [] and extraction is not None
    assert extraction.franchise == Decimal("150")


@pytest.mark.parametrize(
    ("modif", "attendu", "texte", "violation"),
    [
        ({"formule": "luxe"}, "CTR-778801", TEXTE_CONTRAT, "① schéma"),
        ({}, "CTR-000000", TEXTE_CONTRAT, "① numéro ≠ demande"),
        ({"franchise": 1500.0}, "CTR-778801", TEXTE_CONTRAT, "② barème"),
        (
            {},
            "CTR-778801",
            "Contrat CTR-778801 Formule confort Franchise 150 EUR Plafond 8000 EUR",
            "③ absent de la couche texte : date_souscription",
        ),
    ],
)
def test_verrous_du_contrat(
    modif: dict[str, object], attendu: str, texte: str, violation: str
) -> None:
    _, violations = verrous_contrat({**CONTRAT, **modif}, attendu, texte)
    assert violation in violations


def test_scan_sans_couche_texte_seuls_les_verrous_1_et_2() -> None:
    assert verrous_contrat(CONTRAT, "CTR-778801", "")[1] == []
    assert verrous_contrat({**CONTRAT, "plafond": 3000.0}, "CTR-778801", "")[1] == ["② barème"]


JSON = {
    "reference": "KAL-26-0101",
    "assure": {"code_postal": "69003"},
    "contrat": {"numero": "CTR-778801", "statut": "actif", "cotisations_a_jour": True},
    "sinistre": {"type": "degat_des_eaux"},
    "historique": {},
}


def test_demande_niveau_1_contrat_valide() -> None:
    ligne = {
        "formule": "confort",
        "date_souscription": "2024-01-15",
        "statut_extraction": "valide",
        "violations": [],
        "modele": "fake-vlm",
        "version_prompt": "abcd1234",
        "sha256": "f" * 64,
    }
    contrat = demande_niveau_1(JSON, ligne)["contrat"]
    assert contrat["formule"] == "confort" and contrat["statut"] == "actif"
    assert (contrat["statut_extraction"], contrat["source"]) == ("valide", "extraction_vlm")
    assert "pieces" not in demande_niveau_1(JSON, ligne)


def test_demande_niveau_1_contrat_absent() -> None:
    contrat = demande_niveau_1(JSON, None)["contrat"]
    assert (contrat["statut_extraction"], contrat["violations"]) == (
        "non_exploitable",
        ["contrat absent"],
    )
