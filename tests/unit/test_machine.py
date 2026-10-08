"""Unitaires — la table de transitions, prouvée sans agent (dossier 2.3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kaldera.machine import (
    TERMINAUX,
    TOUJOURS,
    TRANSITIONS,
    Etat,
    TransitionInconnue,
    peut_atteindre,
    transition,
)

BORNES = SimpleNamespace(relances_pieces_max=1)


def _etat(**sections: object) -> SimpleNamespace:
    return SimpleNamespace(compteurs=SimpleNamespace(relances=0), **sections)


def test_tout_etat_non_terminal_atteint_un_terminal() -> None:
    for etat in set(Etat) - TERMINAUX:
        assert peut_atteindre(etat, TERMINAUX), etat


def test_tout_etat_non_terminal_mene_a_decision() -> None:
    for etat in set(Etat) - TERMINAUX - {Etat.DECISION}:
        assert peut_atteindre(etat, {Etat.DECISION}), etat


def test_la_seule_boucle_est_la_relance_des_pieces() -> None:
    boucles = {(depart, suivant) for depart, _, suivant in TRANSITIONS if depart == suivant}
    assert boucles == {(Etat.PIECES, Etat.PIECES)}


def test_etat_terminal_sans_transition_leve_une_erreur() -> None:
    with pytest.raises(TransitionInconnue):
        transition(Etat.ACCEPTEE, _etat(), BORNES)


def test_chaque_etat_non_terminal_finit_par_une_garde_toujours() -> None:
    for etat in set(Etat) - TERMINAUX:
        gardes = [garde for depart, garde, _ in TRANSITIONS if depart == etat]
        assert gardes and gardes[-1] is TOUJOURS, etat


def test_premiere_garde_vraie_gagne() -> None:
    non_eligible = _etat(eligibilite=SimpleNamespace(eligible=False))
    eligible = _etat(eligibilite=SimpleNamespace(eligible=True))
    assert transition(Etat.ELIGIBILITE, non_eligible, BORNES)[0] is Etat.DECISION  # T1
    assert transition(Etat.ELIGIBILITE, eligible, BORNES)[0] is Etat.PIECES  # T2


def test_transition_indique_son_numero_pour_la_trace() -> None:
    etat = _etat(eligibilite=SimpleNamespace(eligible=False))
    assert transition(Etat.ELIGIBILITE, etat, BORNES) == (Etat.DECISION, "T1")


@pytest.mark.parametrize(
    ("statut", "relances", "attendu"),
    [
        ("complet", 0, Etat.ESTIMATION),  # T3
        ("incomplet", 0, Etat.PIECES),  # T4
        ("incomplet", 1, Etat.DECISION),  # T5 — borne atteinte
        ("manquant", 0, Etat.DECISION),  # T5 — rien à relancer
    ],
)
def test_transitions_des_pieces(statut: str, relances: int, attendu: Etat) -> None:
    etat = _etat(pieces=SimpleNamespace(statut=statut))
    etat.compteurs.relances = relances
    assert transition(Etat.PIECES, etat, BORNES)[0] is attendu


@pytest.mark.parametrize(
    ("decision", "attendu"),
    [("acceptee", Etat.ACCEPTEE), ("refusee", Etat.REFUSEE), (None, Etat.ESCALADE)],
)
def test_transitions_de_la_decision(decision: str | None, attendu: Etat) -> None:
    etat = _etat(issue=SimpleNamespace(decision=decision))
    assert transition(Etat.DECISION, etat, BORNES)[0] is attendu


def test_numeros_tn_figes_sur_le_dossier() -> None:
    """Tn = position dans la table : insérer ou réordonner une ligne doit casser ce test."""
    assert [(depart, suivant) for depart, _, suivant in TRANSITIONS] == [
        (Etat.ELIGIBILITE, Etat.DECISION),  # T1
        (Etat.ELIGIBILITE, Etat.PIECES),  # T2
        (Etat.PIECES, Etat.ESTIMATION),  # T3
        (Etat.PIECES, Etat.PIECES),  # T4
        (Etat.PIECES, Etat.DECISION),  # T5
        (Etat.ESTIMATION, Etat.DECISION),  # T6
        (Etat.ESTIMATION, Etat.ANTIFRAUDE),  # T7
        (Etat.ANTIFRAUDE, Etat.DECISION),  # T8
        (Etat.DECISION, Etat.ACCEPTEE),  # T9
        (Etat.DECISION, Etat.REFUSEE),  # T10
        (Etat.DECISION, Etat.ESCALADE),  # T11
    ]


@pytest.mark.parametrize(
    ("estime", "attendu"),
    [(0.0, (Etat.DECISION, "T6")), (12.5, (Etat.ANTIFRAUDE, "T7"))],
)
def test_transitions_de_l_estimation(estime: float, attendu: tuple[Etat, str]) -> None:
    etat = _etat(estimation=SimpleNamespace(estime=estime))
    assert transition(Etat.ESTIMATION, etat, BORNES) == attendu


def test_antifraude_mene_toujours_a_la_decision() -> None:
    assert transition(Etat.ANTIFRAUDE, _etat(), BORNES) == (Etat.DECISION, "T8")
