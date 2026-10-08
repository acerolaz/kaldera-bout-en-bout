"""Unitaires — la mémoire partagée d'une demande (dossier 2.4)."""

from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from kaldera.etat import PROPRIETAIRES, SECTIONS, Bornes, EtatDemande

SECTIONS_METIER = ("eligibilite", "pieces", "estimation", "avis_fraude", "issue")


def _etat() -> EtatDemande:
    return EtatDemande(demande={"reference": "KAL-26-0001"})


def test_bornes_par_defaut_du_dossier() -> None:
    bornes = Bornes()
    assert (
        bornes.etapes_max,
        bornes.duree_max_s,
        bornes.relances_pieces_max,
        bornes.delai_partenaire_s,
    ) == (12, 8, 1, 3)
    assert 0 < bornes.duree_max_s <= 10  # engagement de service §12


def test_une_section_par_ecrivain_et_un_ecrivain_par_section() -> None:
    assert set(PROPRIETAIRES) == set(SECTIONS_METIER) == set(SECTIONS)
    assert max(Counter(PROPRIETAIRES.values()).values()) == 1


def test_une_section_mal_formee_est_refusee() -> None:
    etat = _etat()
    with pytest.raises(ValidationError):
        etat.pieces = {"statut": "peut-etre", "manquantes": [], "retenues": []}  # type: ignore[assignment]


def test_une_section_bien_formee_est_convertie_en_modele() -> None:
    etat = _etat()
    etat.eligibilite = {"eligible": True, "conditions_ko": []}  # type: ignore[assignment]
    assert etat.eligibilite is not None and etat.eligibilite.eligible is True


def test_une_issue_sans_motif_est_refusee() -> None:
    etat = _etat()
    with pytest.raises(ValidationError):
        etat.issue = {"issue": "decision", "decision": "acceptee", "motif": ""}  # type: ignore[assignment]


def test_etat_neuf_sans_section_ni_arret() -> None:
    etat = _etat()
    assert all(getattr(etat, s) is None for s in SECTIONS_METIER)
    assert etat.arret is None and etat.trace == []
    assert etat.compteurs.etapes == etat.compteurs.relances == 0
