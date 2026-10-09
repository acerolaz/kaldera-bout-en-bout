"""Authentification de l'espace assuré (UI1) : session simple, remplaçable par OIDC.

Mot de passe haché argon2 ; cookie signé (itsdangerous) portant l'id du compte ; 5 échecs ⇒
blocage 5 min. Les routes ne connaissent que ``api_assure.utilisateur_courant``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .assure_postgres import Compte

COOKIE = "kaldera_session"
SEUIL_ECHECS = 5
BLOCAGE_S = 300.0
_HACHEUR = PasswordHasher()


class ConfigAssure(BaseSettings):
    """``KALDERA_SESSION_SECRET`` (requis), ``KALDERA_FRONT_ORIGIN``, ``KALDERA_COOKIE_SECURE``."""

    model_config = SettingsConfigDict(env_prefix="KALDERA_", env_file=".env", extra="ignore")

    session_secret: SecretStr | None = None
    front_origin: str = "http://localhost:5173"
    cookie_secure: bool = True
    duree_session_h: float = Field(default=8, gt=0)


class Comptes(Protocol):
    def compte(self, identifiant: str) -> Compte | None: ...
    def noter_echec(self, id_: UUID, seuil: int, blocage_s: float) -> None: ...
    def remettre_a_zero(self, id_: UUID) -> None: ...


def hacher(mot_de_passe: str) -> str:
    return _HACHEUR.hash(mot_de_passe)


def authentifier(depot: Comptes, identifiant: str, mot_de_passe: str) -> Compte | None:
    """Le compte si le mot de passe est bon et le compte non bloqué ; None sinon (même réponse)."""
    compte = depot.compte(identifiant)
    if compte is None:
        _HACHEUR.hash(mot_de_passe)  # même coût qu'un vrai essai : pas d'oracle de temps
        return None
    if compte.bloque_jusqu is not None and compte.bloque_jusqu > datetime.now(UTC):
        return None
    try:
        _HACHEUR.verify(compte.hash, mot_de_passe)
    except (VerificationError, InvalidHashError):
        depot.noter_echec(compte.id, SEUIL_ECHECS, BLOCAGE_S)
        return None
    depot.remettre_a_zero(compte.id)
    return compte


def _serialiseur(config: ConfigAssure) -> URLSafeTimedSerializer:
    if config.session_secret is None:
        raise ValueError("KALDERA_SESSION_SECRET absente")
    return URLSafeTimedSerializer(config.session_secret.get_secret_value(), salt="kaldera-session")


def jeton_session(config: ConfigAssure, compte_id: UUID) -> str:
    return str(_serialiseur(config).dumps(str(compte_id)))


def lire_session(config: ConfigAssure, jeton: str | None) -> UUID | None:
    if not jeton:
        return None
    try:  # SignatureExpired hérite de BadSignature
        valeur = _serialiseur(config).loads(jeton, max_age=int(config.duree_session_h * 3600))
        return UUID(str(valeur))
    except (BadSignature, ValueError):
        return None
