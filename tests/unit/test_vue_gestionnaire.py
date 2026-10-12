"""Unitaires — projection de l'état vers l'IHM gestionnaire (spec C3-2 §2)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import AvisFraude, Eligibilite, Estimation, EtatDemande, Issue, Piece, Pieces
from kaldera.vue_gestionnaire import LigneDemande, dossier, euros, filtrer, ligne, lignes

RACINE = Path(__file__).resolve().parents[2]
NOM_01 = json.loads((RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])


def _demande(**contrat: Any) -> dict[str, Any]:
    demande = copy.deepcopy(NOM_01["demandes"][0])
    demande["contrat"].update(contrat)
    return demande


def _entree(
    action: str, vers: str, *, statut: str = "ok", ecrit: list[str] | None = None, **extra: Any
) -> dict[str, Any]:
    return {
        "agent": "agent",
        "action": action,
        "ecrit": [action] if ecrit is None else ecrit,
        "statut": statut,
        "duree_ms": 12.5,
        "de": action,
        "vers": vers,
        "garde": "ok",
        "appels_externes": 0,
        **extra,
    }


def _llm(mode: str = "llm", cause: str | None = None) -> dict[str, Any]:
    return {
        "mode": mode,
        "cause": cause,
        "violations": [],
        "modele": "gpt-test",
        "version_prompt": "v1",
        "tours_llm": 2,
        "jetons": 340,
        "latence_llm_ms": 410.0,
        "sortie_rejetee": False,
    }


def _complet() -> EtatDemande:
    """Dossier accepté : 5 étapes, estimation 1 230 €, anti-fraude non requis."""
    return EtatDemande(
        demande=_demande(),
        eligibilite=Eligibilite(eligible=True),
        pieces=Pieces(
            statut="complet", retenues=[Piece(type="facture", lisible=True, montant=1380)] * 3
        ),
        estimation=Estimation(justifie=1380, retenu=1380, franchise=150, plafond=8000, estime=1230),
        avis_fraude=AvisFraude(requis=False, statut="non_requis"),
        issue=Issue(
            issue="decision", decision="acceptee", montant_rembourse=1230, motif="Dossier conforme"
        ),
        trace=[
            _entree("eligibilite", "pieces"),
            _entree("pieces", "estimation", **_llm()),
            _entree("estimation", "antifraude", **_llm()),
            _entree("antifraude", "decision", ecrit=["avis_fraude"]),
            _entree("decision", "acceptee", ecrit=["issue"], **_llm()),
        ],
    )


def _carte(vue: Any, nom: str) -> Any:
    return next(e for e in vue.etapes if e.etat == nom)


# ------------------------------------------------------------------ ligne (E1)


def test_ligne_reprend_les_champs_de_la_liste() -> None:
    lg = ligne("KAL-26-0101", "terminee", None, _complet())
    assert lg.model_dump() == {
        "reference": "KAL-26-0101",
        "nom": "Martin",
        "prenom": "Claire",
        "police": "CTR-778801",
        "type_sinistre": "degat_des_eaux",
        "montant_declare": 1850.0,
        "statut": "terminee",
        "issue": "acceptee",
        "file": None,
        "mode_degrade": False,
    }


def test_ligne_escalade_degradee() -> None:
    etat = _complet()
    etat.issue = Issue(
        issue="escalade",
        motif="Avis anti-fraude indisponible",
        file="cellule_fraude",
        mode_degrade=True,
    )
    lg = ligne("KAL-26-0203", "terminee", None, etat)
    assert (lg.issue, lg.file, lg.mode_degrade) == ("escalade", "cellule_fraude", True)


FICHE_SECOURS = {
    "issue": "escalade",
    "decision": None,
    "montant_rembourse": None,
    "motif": "Escalade de secours : panne (dernier état : estimation)",
    "file": "gestionnaire",
    "mode_degrade": False,
}


def _sans_issue() -> EtatDemande:
    return EtatDemande(demande=_demande())


def test_escalade_de_secours_lue_dans_la_fiche() -> None:
    etat = _sans_issue()
    lg = ligne("KAL-26-0301", "terminee", FICHE_SECOURS, etat)
    assert (lg.issue, lg.file) == ("escalade", "gestionnaire")
    d = dossier("KAL-26-0301", "terminee", FICHE_SECOURS, etat)
    assert (d.issue, d.file, d.motif) == ("escalade", "gestionnaire", FICHE_SECOURS["motif"])
    assert d.mode_degrade is False


def test_etat_issue_prime_sur_la_fiche() -> None:
    etat = _complet()  # accepté
    d = dossier("KAL-26-0101", "terminee", FICHE_SECOURS, etat)
    assert (d.issue, d.file) == ("acceptee", None)


def test_filtre_escalade_garde_le_dossier_de_secours() -> None:
    lg = ligne("KAL-26-0301", "terminee", FICHE_SECOURS, _sans_issue())
    assert filtrer([lg], issue="escalade") == [lg]
    assert filtrer([lg], file="gestionnaire") == [lg]


def test_une_ligne_illisible_ne_fait_pas_tomber_la_liste() -> None:
    mauvais = _complet()
    mauvais.demande["assure"]["nom"] = 12
    res = lignes(
        [("KAL-26-0101", "terminee", None, _complet()), ("KAL-26-0102", "terminee", None, mauvais)]
    )
    assert [lg.reference for lg in res] == ["KAL-26-0101", "KAL-26-0102"]
    assert res[0].nom == "Martin"
    assert res[1].model_dump() == {
        **dict.fromkeys(LigneDemande.model_fields),
        "reference": "KAL-26-0102",
        "statut": "terminee",
        "mode_degrade": False,
    }


# --------------------------------------------------------- statut d'une étape


def test_etat_minimal_admission_tout_en_attente() -> None:
    vue = dossier(
        "KAL-26-0101", "admission", None, EtatDemande(demande={"reference": "KAL-26-0101"})
    )
    assert [e.etat for e in vue.etapes] == [
        "eligibilite",
        "pieces",
        "estimation",
        "antifraude",
        "decision",
    ]
    assert {e.statut for e in vue.etapes} == {"en_attente"}
    assert (vue.avancement, vue.duree_ms, vue.nom, vue.issue, vue.antifraude) == (
        0,
        0.0,
        None,
        None,
        None,
    )
    assert vue.garanties.formule is None and vue.garanties.franchise is None
    assert all(e.resume == "" and e.duree_ms is None for e in vue.etapes)


def test_statuts_termine_sautee_repli_echec_degrade() -> None:
    etat = _complet()
    etat.avis_fraude = AvisFraude(
        requis=True, statut="indisponible", indicateurs=["F2"], cause="transport:timeout"
    )
    etat.trace = [
        _entree("eligibilite", "pieces"),
        _entree("pieces", "estimation", statut="echec", **_llm()),
        _entree("estimation", "antifraude", **_llm(mode="repli", cause="disjoncteur")),
        _entree("antifraude", "decision", statut="echec", ecrit=["avis_fraude"]),
        _entree("decision", "escalade", ecrit=[], duree_ms=0.0),  # garde d'entrée
    ]
    vue = dossier("KAL-26-0203", "terminee", None, etat)
    assert [e.statut for e in vue.etapes] == ["termine", "echec", "repli", "degrade", "sautee"]


def test_court_circuit_etapes_non_tracees_sautees() -> None:
    etat = _complet()  # refus à l'éligibilité : la machine saute de eligibilite à decision
    etat.trace = [
        _entree("eligibilite", "decision"),
        _entree("decision", "refusee", ecrit=["issue"]),
    ]
    vue = dossier("KAL-26-0103", "terminee", None, etat)
    assert [e.statut for e in vue.etapes] == ["termine", "sautee", "sautee", "sautee", "termine"]
    assert {e.resume for e in vue.etapes[1:4]} == {"Sautée (court-circuit)"}
    assert all(e.avancement == 100 and e.passages == 0 for e in vue.etapes[1:4])


def test_filet_de_securite_marque_l_etape_en_echec() -> None:
    etat = EtatDemande(demande=_demande())
    etat.trace = [
        _entree("eligibilite", "pieces"),
        {
            "agent": "orchestrateur",
            "action": "filet_securite",
            "ecrit": [],
            "statut": "echec",
            "duree_ms": 0.0,
            "de": "pieces",
            "vers": "escalade",
            "garde": "filet",
            "appels_externes": 0,
            "erreur": "KeyError",
        },
    ]
    pieces = _carte(dossier("KAL-26-0101", "terminee", None, etat), "pieces")
    assert (pieces.statut, pieces.resume) == ("echec", "Filet de sécurité : KeyError")


def test_relance_de_pieces_derniere_entree_et_passages() -> None:
    etat = _complet()
    etat.trace.insert(1, _entree("pieces", "pieces", **_llm(mode="repli", cause="timeout")))
    pieces = _carte(dossier("KAL-26-0101", "terminee", None, etat), "pieces")
    assert (pieces.passages, pieces.statut, pieces.mode) == (2, "termine", "llm")


def test_carte_reprend_la_mesure_et_la_transition() -> None:
    estimation = _carte(dossier("KAL-26-0101", "terminee", None, _complet()), "estimation")
    assert estimation.model_dump(exclude={"resume"}) == {
        "etat": "estimation",
        "statut": "termine",
        "avancement": 100,
        "passages": 1,
        "duree_ms": 12.5,
        "latence_llm_ms": 410.0,
        "modele": "gpt-test",
        "mode": "llm",
        "cause": None,
        "tours_llm": 2,
        "jetons": 340,
        "sortie_rejetee": False,
        "de": "estimation",
        "vers": "antifraude",
        "garde": "ok",
    }


# ---------------------------------------------------------- avancement, durée


def test_avancement_et_duree() -> None:
    etat = _complet()
    etat.trace = etat.trace[:3]  # eligibilite, pieces, estimation
    vue = dossier("KAL-26-0101", "en_cours", None, etat)
    assert (vue.avancement, vue.duree_ms, vue.budget_ms) == (60, 37.5, 8000.0)
    assert dossier("KAL-26-0101", "secours", None, etat).avancement == 100


# ------------------------------------------------------------------- résumés


def test_resumes_dossier_accepte() -> None:
    vue = dossier("KAL-26-0101", "terminee", None, _complet())
    assert [e.resume for e in vue.etapes] == [
        "Éligible",
        "Pièces complètes (3 retenues)",
        "Estimé 1\u202f230 € = min(déclaré 1\u202f850 €, justifié 1\u202f380 €) − franchise "
        "150 €, plafond 8\u202f000 € non atteint",
        "Avis non requis",
        "Acceptée : 1\u202f230 €",
    ]


@pytest.mark.parametrize(
    ("section", "valeur", "etape", "attendu"),
    [
        (
            "eligibilite",
            Eligibilite(eligible=False, conditions_ko=["E2", "E4"]),
            "eligibilite",
            "Non éligible : E2, E4",
        ),
        (
            "pieces",
            Pieces(statut="incomplet", manquantes=["facture"]),
            "pieces",
            "Incomplet : manque facture",
        ),
        (
            "pieces",
            Pieces(statut="manquant", manquantes=["facture", "photo"]),
            "pieces",
            "Pièces manquantes : facture, photo",
        ),
        (
            "estimation",
            Estimation(justifie=9000, retenu=9000, franchise=150, plafond=8000, estime=8000),
            "estimation",
            "Estimé 8\u202f000 € = min(déclaré 1\u202f850 €, justifié 9\u202f000 €) − franchise "
            "150 €, plafond 8\u202f000 € atteint",
        ),
        (
            "avis_fraude",
            AvisFraude(requis=True, statut="avis", avis={"niveau": "faible", "score": 12}),
            "antifraude",
            "Avis obtenu : niveau faible, score 12",
        ),
        (
            "avis_fraude",
            AvisFraude(requis=True, statut="indisponible", cause="transport:timeout"),
            "antifraude",
            "Avis indisponible : transport:timeout",
        ),
        (
            "issue",
            Issue(
                issue="decision",
                decision="refusee",
                montant_rembourse=0,
                motif="Garantie non souscrite",
            ),
            "decision",
            "Refusée : Garantie non souscrite",
        ),
        (
            "issue",
            Issue(issue="escalade", motif="Montant au-delà du seuil", file="gestionnaire"),
            "decision",
            "Escaladée vers gestionnaire : Montant au-delà du seuil",
        ),
    ],
)
def test_gabarits(section: str, valeur: Any, etape: str, attendu: str) -> None:
    etat = _complet()
    setattr(etat, section, valeur)
    assert _carte(dossier("KAL-26-0101", "terminee", None, etat), etape).resume == attendu


def test_resume_d_une_etape_sautee() -> None:
    etat = _complet()
    etat.trace[3] = _entree("antifraude", "decision", ecrit=[], duree_ms=0.0, garde="non_requis")
    assert _carte(dossier("KAL-26-0101", "terminee", None, etat), "antifraude").resume == (
        "Sautée (garde non_requis)"
    )


def test_euros() -> None:
    assert (euros(1230), euros(12.5), euros(0)) == ("1\u202f230 €", "12,50 €", "0 €")
    assert euros(1230)[1] == "\u202f"


# ---------------------------------------------------- garanties, anti-fraude


def test_garanties_du_bareme_et_provenance() -> None:
    etat = EtatDemande(demande=_demande(formule="confort", date_souscription="2024-01-15"))
    garanties = dossier("KAL-26-0101", "terminee", None, etat).garanties
    assert garanties.model_dump() == {
        "formule": "confort",
        "franchise": 150.0,
        "plafond": 8000.0,
        "date_souscription": "2024-01-15",
        "statut_contrat": "actif",
        "cotisations_a_jour": True,
        "statut_extraction": "valide",
        "source": "demande_json",
        "modele": None,
        "sha256": None,
    }


def test_carte_antifraude_avis_obtenu() -> None:
    etat = _complet()
    etat.avis_fraude = AvisFraude(
        requis=True,
        statut="avis",
        indicateurs=["F1", "F3"],
        note="Montant élevé",
        avis={
            "niveau": "modere",
            "score": 47,
            "evaluation_id": "EVA-1",
            "version_modele": "m2",
            "reference": "KAL-26-0101",
        },
    )
    carte = dossier("KAL-26-0101", "terminee", None, etat).antifraude
    assert carte is not None and carte.model_dump() == {
        "requis": True,
        "indicateurs": ["F1", "F3"],
        "statut": "ok",
        "niveau": "modere",
        "score": 47.0,
        "evaluation_id": "EVA-1",
        "version_modele": "m2",
        "note": "Montant élevé",
        "cause": None,
    }


def test_compatibilite_reference_statut_fiche() -> None:
    vue = dossier("KAL-26-0101", "secours", {"issue": "escalade"}, _complet())
    assert (vue.reference, vue.statut, vue.fiche) == (
        "KAL-26-0101",
        "secours",
        {"issue": "escalade"},
    )


# ------------------------------------------------------------- liste blanche


def test_aucune_donnee_personnelle_hors_liste_blanche() -> None:
    etat = _complet()
    assure = etat.demande["assure"]
    sorties = (
        ligne("KAL-26-0101", "terminee", None, etat).model_dump_json()
        + dossier("KAL-26-0101", "terminee", None, etat).model_dump_json()
    )
    for cle in ("email", "telephone", "iban", "adresse", "id_client"):
        assert str(assure[cle]) not in sorties, cle


# ------------------------------------------------------------------- filtrer

LIGNES = [
    LigneDemande(
        reference="KAL-26-0203",
        nom="Durand",
        prenom="Paul",
        police="CTR-1",
        type_sinistre="incendie",
        montant_declare=9000,
        statut="terminee",
        issue="escalade",
        file="cellule_fraude",
        mode_degrade=True,
    ),
    LigneDemande(
        reference="KAL-26-0103",
        nom="Martin",
        prenom="Léa",
        police="CTR-2",
        type_sinistre="vol",
        montant_declare=None,
        statut="terminee",
        issue="refusee",
        file=None,
        mode_degrade=False,
    ),
    LigneDemande(
        reference="KAL-26-0101",
        nom=None,
        prenom=None,
        police=None,
        type_sinistre=None,
        montant_declare=None,
        statut="admission",
        issue=None,
        file=None,
        mode_degrade=False,
    ),
]


@pytest.mark.parametrize(
    ("filtres", "attendu"),
    [
        ({}, ["KAL-26-0203", "KAL-26-0103", "KAL-26-0101"]),
        ({"statut": "terminee"}, ["KAL-26-0203", "KAL-26-0103"]),
        ({"statut": ""}, ["KAL-26-0203", "KAL-26-0103", "KAL-26-0101"]),
        ({"issue": "escalade", "mode_degrade": True}, ["KAL-26-0203"]),
        ({"file": "cellule_fraude"}, ["KAL-26-0203"]),
        ({"mode_degrade": False}, ["KAL-26-0103", "KAL-26-0101"]),
        ({"q": "martin"}, ["KAL-26-0103"]),
        ({"q": "  kal-26-0103 "}, ["KAL-26-0103"]),
        ({"q": "ctr-1"}, ["KAL-26-0203"]),
        ({"statut": "terminee", "q": "durand", "issue": "refusee"}, []),
    ],
)
def test_filtrer(filtres: dict[str, Any], attendu: list[str]) -> None:
    assert [lg.reference for lg in filtrer(LIGNES, **filtres)] == attendu
