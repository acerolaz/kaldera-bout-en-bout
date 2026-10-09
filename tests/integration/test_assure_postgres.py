"""Intégration — dépôt de l'espace assuré : comptes, blocage, rattachement, événements, ordre."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.assure_postgres import DepotAssure
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.postgres import DepotPostgres
from tests.fabrique_pdf import pdf_texte
from tests.integration.dossiers import json_demande

pytestmark = pytest.mark.integration
RACINE = Path(__file__).resolve().parents[2]
NOM01 = next(
    json.loads(x)["demandes"][0]
    for x in (RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()
    if json.loads(x)["id"] == "NOM-01"
)


def _demande(base: Any) -> str:
    IngestionPostgres(base).creer_demande(json_demande(NOM01))
    return str(NOM01["reference"])


def test_compte_cree_puis_lu(base: Any) -> None:
    depot = DepotAssure(base)
    uid = depot.creer_compte("claire", "hash", "assure")
    compte = depot.compte("claire")
    assert compte is not None and compte.id == uid and compte.role == "assure"
    assert depot.compte_par_id(uid) == compte and depot.compte("inconnu") is None


def test_cinq_echecs_bloquent(base: Any) -> None:
    depot = DepotAssure(base)
    uid = depot.creer_compte("claire", "hash", "assure")
    for _ in range(4):
        depot.noter_echec(uid, 5, 300)
    compte = depot.compte("claire")
    assert compte is not None and compte.echecs == 4 and compte.bloque_jusqu is None
    depot.noter_echec(uid, 5, 300)
    compte = depot.compte("claire")
    assert compte is not None and compte.bloque_jusqu is not None
    depot.remettre_a_zero(uid)
    compte = depot.compte("claire")
    assert compte is not None and (compte.echecs, compte.bloque_jusqu) == (0, None)


def test_rattachement(base: Any) -> None:
    reference, depot = _demande(base), DepotAssure(base)
    uid, autre = (
        depot.creer_compte("claire", "h", "assure"),
        depot.creer_compte("paul", "h", "assure"),
    )
    depot.rattacher(uid, reference)
    depot.rattacher(uid, reference)  # idempotent
    assert depot.demandes_de(uid) == [reference] and depot.demandes_de(autre) == []
    assert depot.appartient(uid, reference) and not depot.appartient(autre, reference)


def test_les_pieces_sont_lues_dans_l_ordre_du_depot(base: Any) -> None:
    reference, ingestion = _demande(base), IngestionPostgres(base)
    shas = []
    for i in range(10):  # 10 ! ordres possibles : un ordre par UUID aléatoire échoue
        octets = pdf_texte(f"Facture {i}")
        sha = f"{i:064x}"
        ingestion.deposer_piece(reference, octets, "application/pdf", sha, "facture", None)
        shas.append(sha)
    assert [p.sha256 for p in DepotPostgres(base).initiales({"reference": reference})] == shas
    assert [p["type"] for p in DepotAssure(base).donnees(reference)["pieces"]] == ["facture"] * 10


def test_donnees_et_evenements(base: Any) -> None:
    reference, depot = _demande(base), DepotAssure(base)
    d = depot.donnees(reference)
    assert d is not None and d["statut"] == "admission" and d["cree_le"] is not None
    assert d["etat"]["demande"]["sinistre"]["type"] == "degat_des_eaux" and d["horodatages"] == {}
    premier = depot.inserer_evenement(reference, "etape", 2, {"etape": 2})
    depot.inserer_evenement(reference, "message", None, {"auteur": "assure", "texte": "?"})
    assert set(depot.donnees(reference)["horodatages"]) == {2}
    assert [e["type"] for e in depot.evenements_depuis(reference, 0)] == ["etape", "message"]
    assert [e["type"] for e in depot.evenements_depuis(reference, premier)] == ["message"]
    assert depot.messages_assure(reference) == 1 and depot.statut(reference) == "admission"
    assert depot.donnees("KAL-26-9999") is None and depot.statut("KAL-26-9999") is None
