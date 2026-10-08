"""Unitaires — la mémoire partagée d'une demande (dossier 2.4)."""

from __future__ import annotations

from collections import Counter

import pytest
from pydantic import ValidationError

from kaldera.etat import (
    PROPRIETAIRES,
    SECTIONS,
    AvisFraude,
    Bornes,
    Estimation,
    EtatDemande,
    Pieces,
)

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


@pytest.mark.parametrize(
    "issue",
    [
        {"issue": "decision", "decision": None, "motif": "motif valable", "montant_rembourse": 0},
        {"issue": "decision", "decision": "acceptee", "motif": "motif valable"},  # sans montant
        {"issue": "escalade", "motif": "motif valable", "file": None},
        {"issue": "decision", "decision": "acceptee", "motif": "ok !", "montant_rembourse": -1},
    ],
)
def test_une_issue_incoherente_est_refusee(issue: dict[str, object]) -> None:
    etat = _etat()
    with pytest.raises(ValidationError):
        etat.issue = issue  # type: ignore[assignment]


def test_un_arret_ne_demande_que_la_borne() -> None:
    etat = _etat()
    etat.arret = {"borne": "etapes_max", "valeur": 12, "etape": 11}  # type: ignore[assignment]
    assert etat.arret is not None and etat.arret.borne == "etapes_max"


@pytest.mark.parametrize("duree", [0, 10.5])
def test_duree_max_dans_l_engagement_de_service(duree: float) -> None:
    with pytest.raises(ValidationError):
        Bornes(duree_max_s=duree)


def test_les_bornes_ne_se_modifient_pas() -> None:
    with pytest.raises(ValidationError):
        Bornes().etapes_max = 99  # type: ignore[misc]


def test_une_estimation_negative_est_refusee() -> None:
    etat = _etat()
    with pytest.raises(ValidationError):
        etat.estimation = {  # type: ignore[assignment]
            "justifie": 0,
            "retenu": 0,
            "franchise": 0,
            "plafond": 0,
            "estime": -5,
        }


def test_etat_neuf_sans_section_ni_arret() -> None:
    etat = _etat()
    assert all(getattr(etat, s) is None for s in SECTIONS_METIER)
    assert etat.arret is None and etat.trace == []
    assert etat.compteurs.etapes == etat.compteurs.relances == 0


def test_champs_rediges_optionnels() -> None:
    assert Pieces(statut="complet").message_relance is None
    assert Estimation(justifie=1, retenu=1, franchise=0, plafond=5, estime=1).explication is None
    assert AvisFraude(requis=False, statut="non_requis").note is None
    assert Pieces(statut="incomplet", message_relance="Merci").message_relance == "Merci"


def test_bornes_llm() -> None:
    bornes = Bornes()
    assert (bornes.delai_min_llm_s, bornes.reserve_decision_s, bornes.appels_outil_max) == (
        0.3,
        1.0,
        4,
    )


def test_bornes_llm_refusent_les_valeurs_nulles() -> None:
    with pytest.raises(ValidationError):
        Bornes(delai_min_llm_s=0)
    with pytest.raises(ValidationError):
        Bornes(appels_outil_max=0)
