"""Unitaires — garde-fous de sortie des agents LLM (dossier 1.4 bis, EX-D31)."""

from __future__ import annotations

from typing import Any

from kaldera.gardes_fous import (
    champs_differents,
    controle_antifraude,
    controle_decision,
    controle_estimation,
    controle_pieces,
    donnees_sensibles,
    verifier_sortie,
)

VUE = {"demande": {"assure": {"nom": "Martin", "prenom": "Claire"}}}
REF_ESTIM = {
    "justifie": 900.0,
    "retenu": 900.0,
    "franchise": 150.0,
    "plafond": 3000.0,
    "estime": 750.0,
    "explication": "gabarit",
}


def test_champs_differents_ignore_texte_et_prives() -> None:
    patch = {**REF_ESTIM, "estime": 999.0, "explication": "autre"}
    assert champs_differents(patch, REF_ESTIM, {"explication"}) == ["estime"]
    assert champs_differents(REF_ESTIM, REF_ESTIM, {"explication"}) == []


def test_donnees_sensibles_detectees() -> None:
    assert donnees_sensibles("écrire à claire.martin@example.org", VUE) == ["email"]
    assert donnees_sensibles("IBAN FR76 3000 6000 0112 3456 7890 189", VUE) == ["iban"]
    assert donnees_sensibles("appeler le +33 6 12 34 56 78", VUE) == ["telephone"]
    assert donnees_sensibles("Madame Claire Martin", VUE) == ["identite"]
    assert donnees_sensibles("Montant retenu 900 €", VUE) == []
    assert donnees_sensibles(None, VUE) == []


def test_controle_pieces() -> None:
    assert controle_pieces("Merci de déposer la photo", {"statut": "incomplet"}) == []
    assert controle_pieces(None, {"statut": "incomplet"}) == ["message_relance vide"]
    assert controle_pieces("Merci", {"statut": "complet"}) == ["relance sans pièce à relancer"]
    assert controle_pieces(None, {"statut": "complet"}) == []


def test_controle_estimation_cite_franchise_et_plafond() -> None:
    assert controle_estimation("franchise 150 €, plafond 3 000 €", REF_ESTIM) == []
    assert controle_estimation("franchise 150,00 €", REF_ESTIM) == ["explication sans le plafond"]
    assert controle_estimation("", REF_ESTIM) == ["explication vide"]


def test_controle_antifraude() -> None:
    assert controle_antifraude("Indicateurs levés : F1", {}) == []
    assert controle_antifraude('avis {"score": 0.2}', {}) == ["note avec réponse brute"]
    assert controle_antifraude(None, {}) == ["note vide"]


def test_controle_decision_cite_la_regle() -> None:
    ref = {"motif": "Pièces manquantes : photo (borne relances_pieces_max atteinte)"}
    assert controle_decision("Pièces manquantes : la photo n'a pas été reçue.", ref) == []
    assert controle_decision("Dossier à revoir.", ref) == [
        "motif sans la règle « Pièces manquantes »"
    ]
    accorde = {"motif": "Remboursement accordé : 750.00 € — avis indisponible"}
    assert controle_decision("Remboursement accordé de 750 €.", accorde) == []


def test_verifier_sortie_cumule_les_violations() -> None:
    patch = {**REF_ESTIM, "estime": 1.0, "explication": "écrire à claire.martin@example.org"}
    violations = verifier_sortie(patch, REF_ESTIM, VUE, "explication", (), controle_estimation)
    assert violations == [
        "champ décisif modifié : estime",
        "donnée sensible : email",
        "explication sans la franchise",
        "explication sans le plafond",
    ]


def test_le_gabarit_passe_son_propre_garde_fou() -> None:
    ref: dict[str, Any] = {**REF_ESTIM, "explication": "Franchise 150.00 €, plafond 3000.00 €."}
    assert verifier_sortie(ref, ref, VUE, "explication", (), controle_estimation) == []


def test_controle_estimation_compare_les_nombres_entiers() -> None:
    ref_decimale = {"franchise": 12.5, "plafond": 3000.0}
    assert controle_estimation("franchise 12,5 €, plafond 3 000 €", ref_decimale) == []
    assert controle_estimation("plafond 1500 €", REF_ESTIM) == [
        "explication sans la franchise",
        "explication sans le plafond",
    ]


def test_controle_estimation_franchise_nulle() -> None:
    ref_nulle = {"franchise": 0.0, "plafond": 3000.0}
    assert controle_estimation("plafond 3 000 €", ref_nulle) == ["explication sans la franchise"]
    assert controle_estimation("sans franchise, plafond 3 000 €", ref_nulle) == []


def test_donnees_sensibles_variantes() -> None:
    assert donnees_sensibles("iban fr76 3000 6000 0112 3456 7890 189", VUE) == ["iban"]
    assert donnees_sensibles("appeler le 0033 6 12 34 56 78", VUE) == ["telephone"]
    assert donnees_sensibles("appeler le +33 (0)6 12 34 56 78", VUE) == ["telephone"]
