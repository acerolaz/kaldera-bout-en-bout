"""Intégration — API de dépôt : contrôles, déduplication, statuts HTTP (dossier 2.4 ter)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fabrique_pdf import PNG, pdf_texte
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
NOM_01 = json.loads((RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])


def _creer(client: TestClient) -> str:
    demande = json_demande(NOM_01["demandes"][0])
    assert client.post("/demandes", json=demande).status_code == 201
    return str(demande["reference"])


def _deposer(
    client: TestClient, reference: str, octets: bytes, role: str = "initiale", **form: Any
) -> Any:
    donnees = {"role": role, **{k: str(v) for k, v in form.items()}}
    return client.post(
        f"/demandes/{reference}/pieces",
        files={"fichier": ("piece.pdf", octets)},
        data=donnees,
    )


def _compter(base: Any) -> tuple[int, int, int]:
    with base.connection() as conn:
        return tuple(  # type: ignore[return-value]
            conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("blobs", "pieces", "file_ingestion")
        )


def test_creer_puis_lire(client: TestClient) -> None:
    reference = _creer(client)
    assert client.post("/demandes", json=json_demande(NOM_01["demandes"][0])).status_code == 409
    assert client.get(f"/demandes/{reference}").json() == {
        "reference": reference,
        "statut": "admission",
        "fiche": None,
    }
    assert client.get("/demandes/KAL-26-9999").status_code == 404


def test_termes_du_contrat_refuses_dans_le_json(client: TestClient) -> None:
    demande = json_demande(NOM_01["demandes"][0])
    demande["contrat"]["formule"] = "premium"  # le PDF seul fait foi
    assert client.post("/demandes", json=demande).status_code == 422


def test_ing04_meme_fichier_depose_deux_fois(client: TestClient, base: Any) -> None:
    reference = _creer(client)
    facture = pdf_texte("Total 1850.00 EUR")
    premier = _deposer(client, reference, facture, type="facture")
    second = _deposer(client, reference, facture, type="facture")
    assert (premier.status_code, second.status_code) == (202, 200)
    assert premier.json()["piece_id"] == second.json()["piece_id"]
    assert _compter(base) == (1, 1, 1)


def test_ing05_executable_renomme_en_pdf(client: TestClient, base: Any) -> None:
    reference = _creer(client)
    assert _deposer(client, reference, b"MZ\x90\x00 programme", type="facture").status_code == 415
    assert _compter(base) == (0, 0, 0)


def test_fichier_vide_et_trop_gros(client: TestClient, base: Any) -> None:
    reference = _creer(client)
    assert _deposer(client, reference, b"", type="photo").status_code == 415
    trop_gros = PNG + b"x" * (1024 * 1024)
    assert _deposer(client, reference, trop_gros, type="photo").status_code == 413
    assert _compter(base) == (0, 0, 0)


def test_formulaire_incoherent(client: TestClient) -> None:
    reference = _creer(client)
    facture = pdf_texte("Total 1850.00 EUR")
    assert _deposer(client, reference, facture).status_code == 422  # type manquant
    assert _deposer(client, reference, facture, role="depot", type="facture").status_code == 422
    assert (
        _deposer(client, reference, facture, type="facture", relance=1).status_code == 422
    )  # relance hors dépôt
    assert _deposer(client, "KAL-26-9999", facture, type="facture").status_code == 404


def test_contrat_doit_etre_un_pdf(client: TestClient) -> None:
    reference = _creer(client)
    assert _deposer(client, reference, PNG + b"x", role="contrat").status_code == 415
    assert _deposer(client, reference, pdf_texte("Contrat"), role="contrat").status_code == 202


def test_soumettre(client: TestClient, base: Any) -> None:
    reference = _creer(client)
    assert client.post(f"/demandes/{reference}/soumettre").status_code == 202
    assert client.post("/demandes/KAL-26-9999/soumettre").status_code == 404
    with base.connection() as conn:
        conn.execute("UPDATE demandes SET statut = 'terminee' WHERE reference = %s", (reference,))
    assert client.post(f"/demandes/{reference}/soumettre").status_code == 409
    facture = pdf_texte("Total 1850.00 EUR")
    assert _deposer(client, reference, facture, type="facture").status_code == 409
