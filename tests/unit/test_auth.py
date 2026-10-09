"""Unitaires — authentification de l'espace assuré : argon2, blocage, cookie signé."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from kaldera import auth
from kaldera.assure_postgres import Compte

CONFIG = auth.ConfigAssure(_env_file=None, session_secret="secret-de-test")


class FauxDepot:
    def __init__(self, compte: Compte | None) -> None:
        self.c, self.echecs, self.remis = compte, 0, 0

    def compte(self, identifiant: str) -> Compte | None:
        return self.c if self.c and self.c.identifiant == identifiant else None

    def noter_echec(self, id_: UUID, seuil: int, blocage_s: float) -> None:
        assert (seuil, blocage_s) == (auth.SEUIL_ECHECS, auth.BLOCAGE_S)
        self.echecs += 1

    def remettre_a_zero(self, id_: UUID) -> None:
        self.remis += 1


def _compte(bloque_jusqu: datetime | None = None) -> Compte:
    return Compte(uuid4(), "claire", auth.hacher("bon-mot"), "assure", 0, bloque_jusqu)


def test_bon_mot_de_passe() -> None:
    depot = FauxDepot(_compte())
    assert auth.authentifier(depot, "claire", "bon-mot") == depot.c and depot.remis == 1


@pytest.mark.parametrize("identifiant, mot", [("claire", "mauvais"), ("inconnu", "bon-mot")])
def test_echec_meme_reponse(identifiant: str, mot: str) -> None:
    depot = FauxDepot(_compte())
    assert auth.authentifier(depot, identifiant, mot) is None
    assert depot.echecs == (1 if identifiant == "claire" else 0)


def test_compte_bloque_refuse_meme_le_bon_mot_de_passe() -> None:
    depot = FauxDepot(_compte(datetime.now(UTC) + timedelta(minutes=5)))
    assert auth.authentifier(depot, "claire", "bon-mot") is None and depot.remis == 0


def test_blocage_expire() -> None:
    depot = FauxDepot(_compte(datetime.now(UTC) - timedelta(seconds=1)))
    assert auth.authentifier(depot, "claire", "bon-mot") is not None


def test_hash_argon2_jamais_le_mot_en_clair() -> None:
    h = auth.hacher("bon-mot")
    assert h.startswith("$argon2") and "bon-mot" not in h


def test_jeton_aller_retour_et_falsification() -> None:
    uid = uuid4()
    jeton = auth.jeton_session(CONFIG, uid)
    assert auth.lire_session(CONFIG, jeton) == uid
    assert auth.lire_session(CONFIG, jeton[:-2] + "xx") is None
    assert auth.lire_session(CONFIG, None) is None and auth.lire_session(CONFIG, "") is None
    autre = auth.ConfigAssure(_env_file=None, session_secret="autre-secret")
    assert auth.lire_session(autre, jeton) is None


def test_jeton_expire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("itsdangerous.timed.TimestampSigner.get_timestamp", lambda self: 0)
    jeton = auth.jeton_session(CONFIG, uuid4())  # signé en 1970
    monkeypatch.undo()
    assert auth.lire_session(CONFIG, jeton) is None


def test_configuration_par_defaut() -> None:
    config = auth.ConfigAssure(_env_file=None)
    assert config.session_secret is None and config.cookie_secure is True
    assert config.front_origin == "http://localhost:5173" and config.duree_session_h == 8
