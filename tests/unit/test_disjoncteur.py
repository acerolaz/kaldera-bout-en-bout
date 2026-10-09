"""Unitaires — disjoncteur LLM (EX-D33) : taux de repli > 50 % sur 1 min ⇒ repli pour tous."""

from __future__ import annotations

import threading

from kaldera.disjoncteur import Disjoncteur
from kaldera.etat import Bornes


class _Horloge:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _disjoncteur(horloge: _Horloge | None = None, minimum: int = 10) -> Disjoncteur:
    return Disjoncteur(0.5, 60, minimum=minimum, horloge=horloge or _Horloge())


def _noter(d: Disjoncteur, replis: int, succes: int) -> None:
    for repli in [True] * replis + [False] * succes:
        d.noter(repli)


def test_ouvert_au_dessus_du_taux() -> None:
    d = _disjoncteur()
    _noter(d, 6, 4)
    assert d.ouvert()


def test_ferme_a_exactement_le_taux() -> None:
    d = _disjoncteur()
    _noter(d, 5, 5)
    assert not d.ouvert()


def test_ferme_sous_le_minimum_meme_a_100_pour_cent() -> None:
    d = _disjoncteur()
    _noter(d, 9, 0)
    assert not d.ouvert()


def test_se_referme_quand_la_fenetre_est_passee() -> None:
    horloge = _Horloge()
    d = _disjoncteur(horloge)
    _noter(d, 10, 0)
    assert d.ouvert()
    horloge.t = 59.9
    assert d.ouvert()
    horloge.t = 60.0
    assert not d.ouvert()


def test_notes_concurrentes_sans_perte() -> None:
    d = _disjoncteur(minimum=100)
    fils = [threading.Thread(target=d.noter, args=(True,)) for _ in range(100)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()
    assert d.ouvert()  # 100 notes sur 100 : aucune perdue


def test_depuis_les_bornes() -> None:
    bornes = Bornes()
    assert (bornes.taux_repli_disjoncteur, bornes.fenetre_disjoncteur_s) == (0.5, 60)
    d = Disjoncteur.depuis(bornes)
    assert (d.taux, d.fenetre_s, d.minimum) == (0.5, 60, 10)
