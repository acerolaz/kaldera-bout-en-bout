"""Intégration — le worker et le reaper publient des événements déjà projetés (spec §2, §4)."""

from __future__ import annotations

from typing import Any, cast

import pytest

from kaldera import reaper
from kaldera.assure_postgres import DepotAssure
from kaldera.evenements import publier_vue
from kaldera.ingestion import controler_fichier
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.ports import ErreurPersistance
from kaldera.vlm import ConfigIngestion, FakeVLM
from kaldera.worker import travailler
from tools.seed import MANIFESTE, lire_manifeste, verites_fake

pytestmark = pytest.mark.integration
CONFIG = ConfigIngestion(_env_file=None, delai_analyse_s=0.05)
MANIF = lire_manifeste()


def _fichier(reference: str, nom: str) -> bytes:
    return (MANIFESTE.parent / reference / nom).read_bytes()


def _deposer(ingestion: IngestionPostgres, octets: bytes, type_piece: str) -> None:
    mime, sha = controler_fichier(octets, 10, contrat=False)
    ingestion.deposer_piece("KAL-26-0101", octets, mime, sha, type_piece, None)


def _vider(ingestion: IngestionPostgres, vlm: FakeVLM) -> None:
    while travailler(ingestion, vlm, CONFIG):
        pass


def test_parcours_publie_dans_l_ordre(base: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")  # partenaire indisponible
    ingestion, depot = IngestionPostgres(base), DepotAssure(base)
    demande = next(
        x["json"] for x in MANIF if x["reference"] == "KAL-26-0101" and x["role"] == "demande"
    )
    ingestion.creer_demande(demande)
    contrat = _fichier("KAL-26-0101", "contrat.pdf")
    mime, sha = controler_fichier(contrat, 10, contrat=True)
    ingestion.deposer_contrat("KAL-26-0101", contrat, mime, sha)
    vlm = FakeVLM(verites_fake(MANIF))

    _deposer(ingestion, _fichier("KAL-26-0601", "initiale_01_facture.pdf"), "facture")  # illisible
    _vider(ingestion, vlm)
    evts = depot.evenements_depuis("KAL-26-0101", 0)
    pieces = [e for e in evts if e["type"] == "piece"]
    assert pieces and pieces[-1]["contenu"]["pieces"][0]["statut"] == "a_refaire"
    messages = [e["contenu"] for e in evts if e["type"] == "message"]
    assert messages and "n'a pas pu être lu" in messages[-1]["texte"]
    assert messages[-1]["auteur"] == "agent" and messages[-1]["actions"] == ["deposer"]

    _deposer(ingestion, _fichier("KAL-26-0101", "initiale_01_facture.pdf"), "facture")
    _deposer(ingestion, _fichier("KAL-26-0101", "initiale_02_photo.png"), "photo")
    _vider(ingestion, vlm)
    assert "soumettre" in depot.evenements_depuis("KAL-26-0101", 0)[-1]["contenu"]["texte"]

    ingestion.soumettre("KAL-26-0101")
    _vider(ingestion, vlm)
    evts = depot.evenements_depuis("KAL-26-0101", 0)
    # colonne etape = 2 (admission), puis 3 et 4 (trace) ; contenu = vue finale, déjà projetée
    assert [e["type"] for e in evts[-4:]] == ["etape", "etape", "etape", "verdict"]
    final = evts[-1]
    assert final["type"] == "verdict" and final["contenu"]["verdict"]["issue"] == "acceptee"
    assert final["contenu"]["verdict"]["montant"] == 1700.0
    assert set(depot.donnees("KAL-26-0101")["horodatages"]) == {1, 2, 3, 4, 5}


def test_reaper_publie_la_transmission(base: Any) -> None:
    ingestion, depot = IngestionPostgres(base), DepotAssure(base)
    demande = next(
        x["json"] for x in MANIF if x["reference"] == "KAL-26-0101" and x["role"] == "demande"
    )
    ingestion.creer_demande(demande)
    with base.connection() as conn:
        conn.execute("UPDATE demandes SET statut = 'secours' WHERE reference = 'KAL-26-0101'")
    reaper.publier(base, [{"reference": "KAL-26-0101", "file": "cellule_fraude"}])
    (evt,) = depot.evenements_depuis("KAL-26-0101", 0)
    assert evt["type"] == "verdict" and evt["contenu"]["branche"] == "gestionnaire"
    assert (
        "cellule" not in str(evt["contenu"]) and evt["contenu"]["verdict"]["issue"] == "transmise"
    )


def test_publication_en_echec_ne_bloque_pas_le_traitement(
    base: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """EX-01 : un événement perdu ne change jamais l'issue d'une demande."""
    monkeypatch.setenv("PARTENAIRE_URL", "http://127.0.0.1:9")
    ingestion, depot = IngestionPostgres(base), DepotAssure(base)
    demande = next(
        x["json"] for x in MANIF if x["reference"] == "KAL-26-0101" and x["role"] == "demande"
    )
    ingestion.creer_demande(demande)
    contrat = _fichier("KAL-26-0101", "contrat.pdf")
    mime, sha = controler_fichier(contrat, 10, contrat=True)
    ingestion.deposer_contrat("KAL-26-0101", contrat, mime, sha)
    vlm = FakeVLM(verites_fake(MANIF))

    def _panne(*_: Any, **__: Any) -> int:
        raise ErreurPersistance("base indisponible")

    monkeypatch.setattr(DepotAssure, "inserer_evenement", _panne)
    _deposer(ingestion, _fichier("KAL-26-0101", "initiale_01_facture.pdf"), "facture")
    _deposer(ingestion, _fichier("KAL-26-0101", "initiale_02_photo.png"), "photo")
    ingestion.soumettre("KAL-26-0101")
    _vider(ingestion, vlm)

    donnees = depot.donnees("KAL-26-0101")
    assert donnees is not None and donnees["statut"] == "terminee" and donnees["fiche"]


def test_projection_impossible_renvoie_none(caplog: pytest.LogCaptureFixture) -> None:
    class DepotSansEtat:
        def donnees(self, reference: str) -> dict[str, Any]:
            return {"etat": None}  # comme le snapshot illisible du reaper : pas de demande

    with caplog.at_level("WARNING"):
        assert publier_vue(cast(DepotAssure, DepotSansEtat()), "KAL-X", "verdict", 0.0) is None
    assert "KAL-X" in caplog.text and "KeyError" in caplog.text
