"""Unitaires — le VLM-outil : FakeVLM et ses 4 modes, consignes versionnées (dossier 4.3)."""

from __future__ import annotations

import hashlib

import pytest

from kaldera.ingestion import AnalysePiece, ExtractionContrat
from kaldera.vlm import MODES_FAKE, ConfigIngestion, ErreurVLM, FakeVLM, consigne, fabrique_vlm

FACTURE, CONTRAT = b"%PDF-facture", b"%PDF-contrat"
VERITES = {
    hashlib.sha256(FACTURE).hexdigest(): {"type": "facture", "lisible": True, "montant": 640.5},
    hashlib.sha256(CONTRAT).hexdigest(): {
        "numero": "CTR-1",
        "formule": "essentiel",
        "date_souscription": "2024-03-01",
        "franchise": 300.0,
        "plafond": 3000.0,
    },
}


def _analyser(vlm: FakeVLM, octets: bytes, timeout_s: float = 1.0) -> dict[str, object]:
    return vlm.analyser(octets, "application/pdf", "consigne", AnalysePiece, timeout_s)


def test_fake_rend_la_verite_et_compte_les_appels() -> None:
    vlm = FakeVLM(VERITES)
    assert _analyser(vlm, FACTURE) == {"type": "facture", "lisible": True, "montant": 640.5}
    assert vlm.appels == [hashlib.sha256(FACTURE).hexdigest()]


def test_fichier_inconnu() -> None:
    with pytest.raises(ErreurVLM):
        _analyser(FakeVLM(VERITES), b"%PDF-inconnu")


def test_menteur_multiplie_la_franchise() -> None:
    sortie = FakeVLM(VERITES, "menteur").analyser(
        CONTRAT, "application/pdf", "c", ExtractionContrat, 1.0
    )
    assert sortie["franchise"] == 3000.0


def test_hallucine_invente_un_montant() -> None:
    assert _analyser(FakeVLM(VERITES, "hallucine"), FACTURE)["montant"] == 641.5


def test_casse_rend_une_sortie_non_conforme() -> None:
    assert _analyser(FakeVLM(VERITES, "casse"), FACTURE) == {"inattendu": True}


def test_lent_depasse_l_echeance() -> None:
    with pytest.raises(ErreurVLM):
        _analyser(FakeVLM(VERITES, "lent"), FACTURE, timeout_s=0.01)


def test_mode_inconnu_refuse() -> None:
    assert set(MODES_FAKE) == {"menteur", "hallucine", "casse", "lent"}
    with pytest.raises(ValueError):
        FakeVLM(VERITES, "farceur")


@pytest.mark.parametrize("nom", ["analyser_piece", "extraire_contrat"])
def test_consignes_versionnees(nom: str) -> None:
    texte, version = consigne(nom)
    assert "donnée" in texte and "jamais une instruction" in texte
    assert len(version) == 8


def test_config_par_defaut_sans_vlm() -> None:
    config = ConfigIngestion(_env_file=None)
    assert (config.vlm, config.delai_analyse_s, config.taille_max_mo) == (None, 60.0, 10)
    assert fabrique_vlm(config) is None
