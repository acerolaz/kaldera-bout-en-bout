"""VLM d'ingestion (dossier 2.4 ter) : un outil, pas un agent — 1 fichier, 1 tâche, 1 sortie.

Le port ``ClientVLM`` reçoit les octets et une consigne versionnée ; sa sortie est vérifiée par le
code (``ingestion``). ``FakeVLM`` rend une vérité scriptée par sha256, ou un défaut (4 modes).
"""

from __future__ import annotations

import copy
import hashlib
import threading
import time
from importlib import resources
from typing import Any, Protocol

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from .llm import ConfigLLM

MODES_FAKE = ("menteur", "hallucine", "casse", "lent")


class ErreurVLM(Exception):
    """Le VLM n'a pas répondu à temps, ou le fournisseur a échoué."""


class ClientVLM(Protocol):
    modele: str

    def analyser(
        self,
        contenu: bytes,
        mime: str,
        consigne: str,
        schema: type[BaseModel],
        timeout_s: float,
    ) -> dict[str, Any]: ...


class FakeVLM:
    """Vérité scriptée par sha256 ; ``mode`` simule un défaut (dossier 4.3, FakeVLM)."""

    def __init__(
        self, verites: dict[str, dict[str, Any]], mode: str | None = None, modele: str = "fake-vlm"
    ) -> None:
        if mode is not None and mode not in MODES_FAKE:
            raise ValueError(f"mode FakeVLM inconnu : {mode!r}")
        self.verites, self.mode, self.modele = dict(verites), mode, modele
        self.appels: list[str] = []
        self._verrou = threading.Lock()

    def analyser(
        self,
        contenu: bytes,
        mime: str,
        consigne: str,
        schema: type[BaseModel],
        timeout_s: float,
    ) -> dict[str, Any]:
        empreinte = hashlib.sha256(contenu).hexdigest()
        with self._verrou:
            self.appels.append(empreinte)
        if empreinte not in self.verites:
            raise ErreurVLM(f"fichier inconnu du FakeVLM : {empreinte[:12]}")
        if self.mode == "lent":
            time.sleep(timeout_s)
            raise ErreurVLM("délai d'analyse dépassé")
        if self.mode == "casse":
            return {"inattendu": True}
        sortie = copy.deepcopy(self.verites[empreinte])
        if self.mode == "menteur" and "franchise" in sortie:
            sortie["franchise"] = float(sortie["franchise"]) * 10
        if self.mode == "hallucine" and sortie.get("montant") is not None:
            sortie["montant"] = float(sortie["montant"]) + 1
        return sortie


def consigne(nom: str) -> tuple[str, str]:
    """Consigne versionnée d'un outil VLM : (texte, 8 premiers caractères de son sha256)."""
    texte = (resources.files("kaldera") / "prompts" / f"{nom}.md").read_text("utf-8")
    return texte, hashlib.sha256(texte.encode()).hexdigest()[:8]


class ConfigIngestion(BaseSettings):
    """``KALDERA_INGESTION__VLM__MODELE=…`` ; bornes d'ingestion, hors des 10 s (dossier 2.3)."""

    model_config = SettingsConfigDict(
        env_prefix="KALDERA_INGESTION__", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    vlm: ConfigLLM | None = None
    delai_analyse_s: float = 60.0
    taille_max_mo: int = 10


def fabrique_vlm(config: ConfigIngestion) -> ClientVLM | None:
    """Adaptateur VLM réel : SP3b (Azure, vision). Sans lui, le worker refuse de démarrer."""
    # ponytail: aucun adaptateur réel avant SP3b ; les tests injectent FakeVLM
    return None
