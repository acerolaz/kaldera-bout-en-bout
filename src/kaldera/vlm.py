"""VLM d'ingestion (dossier 2.4 ter) : un outil, pas un agent — 1 fichier, 1 tâche, 1 sortie.

Le port ``ClientVLM`` reçoit les octets et une consigne versionnée ; sa sortie est vérifiée par le
code (``ingestion``). ``FakeVLM`` rend une vérité scriptée par sha256, ou un défaut (4 modes).
"""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from importlib import resources
from typing import Any, Protocol

import pypdfium2 as pdfium
from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .agents_llm import _sans_balises
from .llm import ConfigLLM, DelaiDepasse, client_azure

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
    azure_ai_chat_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AZURE_AI_CHAT_ENDPOINT", "azure_ai_chat_endpoint"),
    )
    azure_ai_chat_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("AZURE_AI_CHAT_KEY", "azure_ai_chat_key")
    )


RESOLUTION_DPI = 150
PX_MAX = 2000  # côté maximal du rendu : la taille de page vient d'un fichier non fiable


def en_image(contenu: bytes, mime: str) -> tuple[bytes, str]:
    """Ce que voit le VLM : l'image du document ; PDF ⇒ page 1 en PNG. Jamais son texte."""
    if mime != "application/pdf":
        return contenu, mime
    try:
        document = pdfium.PdfDocument(contenu)
        try:
            page = document[0]
            echelle = min(RESOLUTION_DPI / 72, PX_MAX / max(page.get_size()))
            image = page.render(scale=echelle).to_pil()
        finally:
            document.close()
    except (
        pdfium.PdfiumError,
        IndexError,
        ZeroDivisionError,
    ) as exc:  # PDF illisible, ou sans page
        raise ErreurVLM(f"PDF illisible pour le rendu : {exc}") from exc
    tampon = io.BytesIO()
    image.save(tampon, format="PNG")
    return tampon.getvalue(), "image/png"


class AzureVLM:
    """Azure AI Foundry (``ChatCompletionsClient``), déploiement capable de vision, derrière
    ``ClientVLM``."""

    def __init__(self, config: ConfigLLM, client: Any) -> None:
        self.modele = config.modele
        self._client = client

    @classmethod
    def depuis(cls, config: ConfigLLM, endpoint: str, cle: str, delai_s: float) -> AzureVLM:
        return cls(config, client_azure(config, endpoint, cle, delai_s))

    def analyser(
        self,
        contenu: bytes,
        mime: str,
        consigne: str,
        schema: type[BaseModel],
        timeout_s: float,
    ) -> dict[str, Any]:
        from azure.core.exceptions import AzureError

        image, type_image = en_image(contenu, mime)
        url = f"data:{type_image};base64,{base64.b64encode(image).decode()}"
        messages = [
            {"role": "system", "content": consigne},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]},
        ]
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            reponse = pool.submit(self._client.complete, messages=messages).result(
                timeout=timeout_s
            )
            sortie = json.loads(_sans_balises(reponse.choices[0].message.content))
        except DelaiDepasse as exc:
            raise ErreurVLM(f"délai de {timeout_s:.0f} s dépassé") from exc
        except (AzureError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ErreurVLM(f"erreur du fournisseur ou réponse mal formée : {exc!r}") from exc
        finally:
            pool.shutdown(wait=False)  # au délai, le thread HTTP est borné par read_timeout
        if not isinstance(sortie, dict):
            raise ErreurVLM("la sortie du VLM n'est pas un objet JSON")
        return sortie


def fabrique_vlm(config: ConfigIngestion) -> ClientVLM | None:
    """Le VLM d'ingestion, ou None s'il n'est pas configuré (le worker refuse alors de démarrer)."""
    cle = config.azure_ai_chat_key.get_secret_value() if config.azure_ai_chat_key else ""
    if config.vlm is None or not config.vlm.vision or not config.azure_ai_chat_endpoint or not cle:
        return None
    return AzureVLM.depuis(config.vlm, config.azure_ai_chat_endpoint, cle, config.delai_analyse_s)
