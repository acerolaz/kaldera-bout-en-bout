"""Unitaires — projection C3-3 : sélection, étape en cours, % agent, lot, événements (spec §2.4, §3.3)."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from kaldera.etat import EtatDemande, Issue
from kaldera.vue_gestionnaire import avancement_agent, dossier, evenement, ligne, lot

RACINE = Path(__file__).resolve().parents[2]
NOM_01 = json.loads((RACINE / "eval/scenarios.jsonl").read_text("utf-8").splitlines()[0])
T0 = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)


def _etat(**champs: Any) -> EtatDemande:
    return EtatDemande(demande=copy.deepcopy(NOM_01["demandes"][0]), **champs)


@pytest.mark.parametrize(
    ("statut", "selectionnable", "motif"),
    [
        ("prete", True, None),
        ("admission", False, "Pièces en cours d'analyse"),
        ("en_cours", False, "Traitement en cours"),
        ("terminee", False, "Déjà traité"),
        ("secours", False, "Déjà traité"),
    ],
)
def test_selection_par_statut(statut: str, selectionnable: bool, motif: str | None) -> None:
    vue = ligne("KAL-26-0101", statut, None, _etat())
    assert (vue.selectionnable, vue.motif_non_selectionnable) == (selectionnable, motif)


def test_dossier_en_cours_etape_courante_en_cours() -> None:
    etat = _etat(etat_courant="pieces")
    etat.trace = [
        {
            "action": "eligibilite",
            "ecrit": ["eligibilite"],
            "statut": "ok",
            "duree_ms": 1.0,
            "de": "eligibilite",
            "vers": "pieces",
            "garde": "ok",
        }
    ]
    vue = dossier("KAL-26-0101", "en_cours", None, etat)
    assert [(e.etat, e.statut, e.avancement) for e in vue.etapes] == [
        ("eligibilite", "termine", 100),
        ("pieces", "en_cours", 0),
        ("estimation", "en_attente", 0),
        ("antifraude", "en_attente", 0),
        ("decision", "en_attente", 0),
    ]
    assert vue.avancement == 20


def test_dossier_prete_aucune_etape_en_cours() -> None:
    vue = dossier("KAL-26-0101", "prete", None, _etat())
    assert {e.statut for e in vue.etapes} == {"en_attente"} and vue.avancement == 0


@pytest.mark.parametrize(
    ("sous_etape", "tour", "attendu"),
    [
        ("vue", 0, 17),
        ("tour", 1, 33),
        ("outil", 1, 33),
        ("tour", 2, 50),
        ("garde_fou", 2, 83),
        ("garde_fou", 0, 83),  # repli : directement au garde-fou
    ],
)
def test_avancement_agent(sous_etape: str, tour: int, attendu: int) -> None:
    assert avancement_agent(sous_etape, tour, tours_max=3) == attendu


def test_evenements_traduits() -> None:
    base = {"reference": "KAL-26-0101", "etat": "pieces"}
    debut = evenement({"type": "etape_debut", **base})
    assert debut is not None and (debut.statut, debut.avancement_agent) == ("en_cours", 0)
    sous = evenement(
        {"type": "sous_etape", **base, "sous_etape": "tour", "tour": 1, "tours_max": 3}
    )
    assert sous is not None and (sous.statut, sous.avancement_agent) == ("en_cours", 33)
    fin = evenement({"type": "etape_fin", **base})
    assert fin is not None and (fin.statut, fin.avancement_agent) == (None, 100)
    clos = evenement({"type": "dossier_fin", "reference": "KAL-26-0101"})
    assert clos is not None and (clos.etat, clos.avancement_agent) == (None, None)


@pytest.mark.parametrize(
    "brut",
    [
        {"type": "inconnu", "reference": "KAL-26-0101"},
        {"type": "etape_debut"},
        {"type": "sous_etape", "reference": "KAL-26-0101", "etat": "pieces", "tour": "x"},
        {"type": "etape_fin", "reference": 12},
    ],
)
def test_evenement_malforme_ignore(brut: dict[str, Any]) -> None:
    assert evenement(brut) is None


def _termine(decision: str, file: str | None = None, degrade: bool = False) -> EtatDemande:
    """Escalade si ``file``, sinon décision (une décision porte toujours un montant)."""
    etat = _etat(etat_courant="fin")
    if file:
        etat.issue = Issue(issue="escalade", motif="motif", file=file, mode_degrade=degrade)
    else:
        montant = 100.0 if decision == "acceptee" else 0.0
        etat.issue = Issue.model_validate(
            {
                "issue": "decision",
                "decision": decision,
                "montant_rembourse": montant,
                "motif": "motif",
            }
        )
    return etat


def test_lot_en_cours_puis_clos() -> None:
    en_cours = _etat(etat_courant="estimation")
    demandes = [
        ("KAL-26-0101", "terminee", None, _termine("acceptee")),
        ("KAL-26-0102", "en_cours", None, en_cours),
        ("KAL-26-0103", "terminee", None, _termine("refusee")),
        ("KAL-26-0104", "secours", None, _termine("", file="cellule_fraude", degrade=True)),
    ]
    vue = lot(7, T0, T0 + timedelta(seconds=3), demandes)
    assert (vue.id, vue.avancement, vue.fin) == (7, 75, None)
    assert vue.compteurs.model_dump() == {
        "acceptee": 1,
        "refusee": 1,
        "escalade": {"cellule_fraude": 1},
        "mode_degrade": 1,
    }
    ligne_en_cours = vue.dossiers[1]
    assert (ligne_en_cours.etape_en_cours, ligne_en_cours.statut) == ("estimation", "en_cours")
    assert vue.dossiers[0].etape_en_cours is None
    clos = lot(7, T0, T0 + timedelta(seconds=3), [demandes[0], demandes[2]])
    assert (clos.avancement, clos.fin) == (100, T0 + timedelta(seconds=3))


def test_lot_sans_donnee_personnelle() -> None:
    etat = _etat()
    etat.demande["assure"].update(
        email="claire@example.org",
        telephone="0600000000",
        iban="FR7630006000011234567890189",
    )
    texte = lot(1, T0, T0, [("KAL-26-0101", "prete", None, etat)]).model_dump_json()
    assert not any(x in texte for x in ("claire@example.org", "0600000000", "FR7630006"))
