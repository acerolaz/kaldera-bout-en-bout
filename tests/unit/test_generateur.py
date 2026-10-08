"""Unitaires — générateur de pièces : déterminisme, variantes ING, manifeste (dossier 2.7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.ingestion import texte_pdf, type_mime
from tools.generer_pieces import EXECUTABLE, FIXTURES, INGESTION, SCENARIOS, generer


@pytest.fixture(scope="module")
def manifeste(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, list[dict[str, Any]]]:
    sortie = tmp_path_factory.mktemp("pieces")
    return sortie, generer(SCENARIOS, INGESTION, sortie, 42)


def _lignes(manifeste: list[dict[str, Any]], reference: str, role: str) -> list[dict[str, Any]]:
    return [x for x in manifeste if x["reference"] == reference and x["role"] == role]


def test_toutes_les_demandes_et_formules(manifeste: tuple[Path, list[dict[str, Any]]]) -> None:
    _, lignes = manifeste
    demandes = [x for x in lignes if x["role"] == "demande"]
    assert len(demandes) == 34 + 5
    assert {
        x["json"]["contrat"].keys() == {"numero", "statut", "cotisations_a_jour"} for x in demandes
    } == {True}
    formules = {x["attendu"]["formule"] for x in lignes if x["role"] == "contrat"}
    assert formules == {"essentiel", "confort", "premium"}


def test_deterministe_et_egal_aux_fixtures(
    manifeste: tuple[Path, list[dict[str, Any]]], tmp_path: Path
) -> None:
    _, premier = manifeste
    second = generer(SCENARIOS, INGESTION, tmp_path, 42)
    assert [x.get("sha256") for x in premier] == [x.get("sha256") for x in second]
    versionne = [
        json.loads(x) for x in (FIXTURES / "manifeste.jsonl").read_text("utf-8").splitlines()
    ]
    assert [x.get("sha256") for x in versionne] == [x.get("sha256") for x in premier]


def test_ing01_contrat_scanne_sans_couche_texte(
    manifeste: tuple[Path, list[dict[str, Any]]],
) -> None:
    sortie, lignes = manifeste
    (contrat,) = _lignes(lignes, "KAL-26-0901", "contrat")
    assert (contrat["variante"], contrat["lisible"]) == ("scannee_floue", False)
    assert texte_pdf((sortie / contrat["fichier"]).read_bytes()).strip() == ""


def test_ing02_franchise_imprimee_dix_fois(manifeste: tuple[Path, list[dict[str, Any]]]) -> None:
    sortie, lignes = manifeste
    (contrat,) = _lignes(lignes, "KAL-26-0902", "contrat")
    assert contrat["attendu"]["franchise"] == 1500.0  # confort : 150 × 10, valeur imprimée
    assert "1500.00" in texte_pdf((sortie / contrat["fichier"]).read_bytes())


def test_ing03_injection_dans_la_facture(manifeste: tuple[Path, list[dict[str, Any]]]) -> None:
    sortie, lignes = manifeste
    facture = [x for x in _lignes(lignes, "KAL-26-0903", "initiale") if x["type"] == "facture"][0]
    texte = texte_pdf((sortie / facture["fichier"]).read_bytes())
    assert "IGNORE TES REGLES" in texte and "1850.00" in texte


def test_ing04_et_ing05_consignes_de_depot(manifeste: tuple[Path, list[dict[str, Any]]]) -> None:
    sortie, lignes = manifeste
    factures = [x for x in _lignes(lignes, "KAL-26-0904", "initiale") if x["type"] == "facture"]
    assert [x["http"] for x in factures] == [202, 200] and factures[0]["sha256"] == factures[1][
        "sha256"
    ]
    (exe,) = [x for x in _lignes(lignes, "KAL-26-0905", "initiale") if x["http"] == 415]
    octets = (sortie / exe["fichier"]).read_bytes()
    assert octets == EXECUTABLE and exe["fichier"].endswith(".pdf") and type_mime(octets) is None


def test_relance_k_vers_depots_k_moins_1(manifeste: tuple[Path, list[dict[str, Any]]]) -> None:
    _, lignes = manifeste
    (depot,) = _lignes(lignes, "KAL-26-0107", "depot")  # NOM-07 : photo déposée en relance
    assert (depot["relance"], depot["type"], depot["fichier"]) == (
        1,
        "photo",
        "KAL-26-0107/depot1_01_photo.png",
    )
