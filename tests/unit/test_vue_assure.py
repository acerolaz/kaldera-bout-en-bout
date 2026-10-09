"""Unitaires — projection vers l'assuré : étapes, pièces attendues, verdict, liste blanche."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from kaldera.vue_assure import (
    TEXTE_TRANSMISE,
    PieceAttendue,
    VueDemande,
    construire,
    etape_et_branche,
    pieces_attendues,
    verdict,
)

MAINTENANT = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def _p(type_: str, statut: str = "ok", lisible: bool | None = True) -> dict[str, Any]:
    return {
        "type": type_,
        "statut_analyse": statut,
        "lisible": lisible,
        "montant": None,
        "depose_le": MAINTENANT,
    }


def _attendues(*statuts: str) -> list[PieceAttendue]:
    return [PieceAttendue(type="facture", libelle="Facture", statut=s) for s in statuts]


def test_pieces_attendues_la_derniere_du_type_fait_foi() -> None:
    pieces = [_p("facture", "ok", False), _p("facture", "ok", True), _p("photo", "en_attente")]
    attendues = pieces_attendues("degat_des_eaux", pieces)
    assert [(p.type, p.statut) for p in attendues] == [
        ("facture", "validee"),
        ("photo", "en_analyse"),
    ]
    assert pieces_attendues("vol", [])[1].statut == "a_fournir"
    refaite = pieces_attendues("incendie", [_p("facture", "echec", False)])[0]
    assert refaite.statut == "a_refaire" and refaite.raison


@pytest.mark.parametrize(
    "statut, etat_courant, soumise, fiche, pieces, attendu",
    [
        ("admission", "eligibilite", False, None, _attendues("a_fournir"), (1, "attente_pieces")),
        ("admission", "eligibilite", False, None, _attendues("en_analyse", "a_refaire"), (1, None)),
        ("admission", "eligibilite", True, None, _attendues("a_fournir"), (1, None)),
        ("admission", "eligibilite", False, None, _attendues("validee"), (1, None)),
        ("en_cours", "eligibilite", True, None, [], (2, None)),
        ("en_cours", "pieces", True, None, [], (2, None)),
        ("en_cours", "estimation", True, None, [], (3, None)),
        ("en_cours", "antifraude", True, None, [], (4, None)),
        ("en_cours", "decision", True, None, [], (5, None)),
        ("terminee", "acceptee", True, {"issue": "decision"}, [], (5, None)),
        ("terminee", "escalade", True, {"issue": "escalade"}, [], (5, "gestionnaire")),
        ("secours", "estimation", True, None, [], (5, "gestionnaire")),
    ],
)
def test_etape_et_branche(
    statut: str, etat_courant: str, soumise: bool, fiche: Any, pieces: Any, attendu: Any
) -> None:
    assert etape_et_branche(statut, etat_courant, soumise, fiche, pieces) == attendu


def _escalade(file: str, motif: str) -> dict[str, Any]:
    return {
        "issue": "escalade",
        "decision": None,
        "montant_rembourse": None,
        "file": file,
        "motif": motif,
        "mode_degrade": file == "cellule_fraude",
    }


def test_cellule_fraude_identique_a_gestionnaire() -> None:
    etat = {"demande": {"sinistre": {"montant_declare": 900.0}}}
    a = verdict("terminee", _escalade("cellule_fraude", "Suspicion de fraude"), etat)
    b = verdict("terminee", _escalade("gestionnaire", "Seuil de délégation dépassé"), etat)
    c = verdict(
        "terminee", _escalade("gestionnaire", "Contrôle renforcé : risque de fraude modéré"), etat
    )
    assert a == b == c and a is not None and a.issue == "transmise"
    assert a.explication == TEXTE_TRANSMISE and a.montant is None


def _accordee(montant: float) -> dict[str, Any]:
    return {
        "issue": "decision",
        "decision": "acceptee",
        "montant_rembourse": montant,
        "file": None,
        "motif": f"Remboursement accordé : {montant:.2f} € — avis anti-fraude indisponible, "
        "décision en mode dégradé (§9)",
        "mode_degrade": True,
    }


def _etat(declare: float, retenu: float, estime: float, plafond: float = 8000.0) -> dict[str, Any]:
    return {
        "demande": {"sinistre": {"montant_declare": declare}},
        "estimation": {
            "justifie": retenu,
            "retenu": retenu,
            "franchise": 150.0,
            "plafond": plafond,
            "estime": estime,
        },
        "pieces": {"retenues": [{"type": "facture"}, {"type": "photo"}]},
    }


def test_verdict_accorde_sans_recopier_le_motif() -> None:
    v = verdict("terminee", _accordee(1700.0), _etat(1850.0, 1850.0, 1700.0))
    assert v is not None and v.issue == "acceptee" and (v.montant, v.franchise) == (1700.0, 150.0)
    assert "1\u00a0700,00\u00a0€" in v.explication and "150,00\u00a0€" in v.explication
    assert "dégradé" not in v.explication and "fraude" not in v.explication
    assert v.pieces_retenues == ["Facture", "Photos des dommages"]


def test_verdict_partiel() -> None:
    v = verdict("terminee", _accordee(1050.0), _etat(1850.0, 1200.0, 1050.0))
    assert v is not None and v.issue == "partielle" and "1\u00a0200,00\u00a0€" in v.explication
    plafonne = verdict("terminee", _accordee(3000.0), _etat(5000.0, 5000.0, 3000.0, 3000.0))
    assert plafonne is not None and plafonne.issue == "partielle"


def test_verdict_refuse_conditions_en_clair() -> None:
    fiche = {
        "issue": "decision",
        "decision": "refusee",
        "montant_rembourse": 0.0,
        "file": None,
        "motif": "Demande non éligible : déclaration hors délai",
        "mode_degrade": False,
    }
    etat = {
        "demande": {"sinistre": {"montant_declare": 900.0}},
        "eligibilite": {"eligible": False, "conditions_ko": ["déclaration hors délai"]},
    }
    v = verdict("terminee", fiche, etat)
    assert v is not None and v.issue == "refusee" and "déclaré hors délai" in v.explication
    franchise = verdict(
        "terminee",
        {**fiche, "motif": "Dommage inférieur ou égal à la franchise"},
        {**_etat(100.0, 100.0, 0.0), "eligibilite": {"eligible": True, "conditions_ko": []}},
    )
    assert franchise is not None and "franchise" in franchise.explication


def test_pas_de_verdict_avant_la_fin_et_secours_transmis() -> None:
    assert verdict("en_cours", None, {}) is None and verdict("admission", None, {}) is None
    secours = verdict("secours", None, {})
    assert secours is not None and secours.issue == "transmise"


def _donnees(**champs: Any) -> dict[str, Any]:
    return {
        "reference": "KAL-26-0101",
        "statut": "admission",
        "etat_courant": "eligibilite",
        "etat": {"demande": {"sinistre": {"type": "degat_des_eaux", "montant_declare": 1850.0}}},
        "fiche": None,
        "soumise_le": None,
        "cree_le": MAINTENANT,
        "pieces": [],
        "horodatages": {},
        **champs,
    }


def test_construire() -> None:
    vue = construire(_donnees(pieces=[_p("facture", "en_attente")]), 60.0)
    assert (vue.etape, vue.branche, vue.soumise, vue.verdict) == (1, None, False, None)
    assert vue.restant_estime_s == 60.0 and vue.horodatages == {1: MAINTENANT}
    en_cours = construire(
        _donnees(
            statut="en_cours",
            etat_courant="estimation",
            soumise_le=MAINTENANT,
            horodatages={2: MAINTENANT},
        ),
        60.0,
    )
    assert (en_cours.etape, en_cours.restant_estime_s, set(en_cours.horodatages)) == (
        3,
        10.0,
        {1, 2},
    )


def test_liste_blanche() -> None:
    vue = construire(_donnees(), 60.0)
    with pytest.raises(ValidationError):
        VueDemande.model_validate({**vue.model_dump(), "avis_fraude": {"score": 0.9}})
    assert set(vue.model_dump()) == {
        "reference",
        "cree_le",
        "etape",
        "branche",
        "horodatages",
        "restant_estime_s",
        "pieces",
        "soumise",
        "verdict",
    }
