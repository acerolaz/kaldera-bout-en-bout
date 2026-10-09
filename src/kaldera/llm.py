"""Port LLM des agents métier (dossier 1.4 → 1.4 ter).

Les agents ne connaissent que ``ClientLLM`` ; le SDK Azure (azure-ai-inference) n'apparaît que
dans l'adaptateur. ``FakeLLM`` rejoue un script : il sert aux tests (niveaux ① et ② du plan d'épreuve).
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as DelaiDepasse
from typing import Any, Literal, Protocol

from pydantic import AliasChoices, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppelOutil(BaseModel):
    id: str
    nom: str
    arguments: dict[str, Any] = {}


class ReponseLLM(BaseModel):
    texte: str | None = None
    appels_outils: list[AppelOutil] = []
    jetons: int = 0


class ErreurLLM(Exception):
    """Le LLM n'a pas répondu à temps, ou le fournisseur a renvoyé une erreur."""


class ClientLLM(Protocol):
    modele: str

    def completer(
        self,
        systeme: str,
        messages: list[dict[str, Any]],
        outils: list[dict[str, Any]],
        timeout_s: float,
    ) -> ReponseLLM: ...


# ------------------------------------------------------------------ FakeLLM

Script = Callable[[list[dict[str, Any]], list[dict[str, Any]]], ReponseLLM]
Rediger = Callable[[dict[str, Any]], str | None]


class FakeLLM:
    """LLM scripté : ``script(messages, outils)`` décide de chaque réponse."""

    def __init__(self, script: Script, *, modele: str = "fake", latence_s: float = 0.0) -> None:
        self.script, self.modele, self.latence_s = script, modele, latence_s
        self.appels = 0

    def completer(
        self,
        systeme: str,
        messages: list[dict[str, Any]],
        outils: list[dict[str, Any]],
        timeout_s: float,
    ) -> ReponseLLM:
        self.appels += 1
        if self.latence_s > timeout_s:
            raise ErreurLLM(f"délai dépassé ({self.latence_s} s > {timeout_s:.2f} s)")
        return self.script(messages, outils)


def _dernier_resultat(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if messages and messages[-1]["role"] == "tool":
        resultat: dict[str, Any] = json.loads(messages[-1]["content"])
        return resultat
    return None


def _appel(
    messages: list[dict[str, Any]], outils: list[dict[str, Any]], nom: str | None = None
) -> ReponseLLM:
    nom = nom or outils[0]["function"]["name"]
    return ReponseLLM(appels_outils=[AppelOutil(id=f"a{len(messages)}", nom=nom)], jetons=10)


def _final(patch: dict[str, Any]) -> ReponseLLM:
    return ReponseLLM(texte=json.dumps(patch, ensure_ascii=False), jetons=20)


def fidele(champ: str, rediger: Rediger, *, mensonge: dict[str, Any] | None = None) -> FakeLLM:
    """Appelle le premier outil, puis recopie son résultat et rédige ``champ``."""

    def script(messages: list[dict[str, Any]], outils: list[dict[str, Any]]) -> ReponseLLM:
        resultat = _dernier_resultat(messages)
        if resultat is None:
            return _appel(messages, outils)
        return _final({**resultat, champ: rediger(resultat), **(mensonge or {})})

    return FakeLLM(script)


SABOTEURS = ("menteur", "bavard", "lent", "casse", "intrus", "fuite", "injecte")
FUITE = "Contact : claire.martin@example.org, IBAN FR76 3000 6000 0112 3456 7890 189"


def saboteur(mode: str, champ: str, rediger: Rediger, mensonge: dict[str, Any]) -> FakeLLM:
    """Les 7 défauts du plan d'épreuve (dossier 4.3) ; chacun doit finir en repli."""
    honnete, menteur = (
        fidele(champ, rediger).script,
        fidele(champ, rediger, mensonge=mensonge).script,
    )
    scripts: dict[str, FakeLLM] = {
        "menteur": FakeLLM(menteur),
        "bavard": FakeLLM(lambda m, o: _appel(m, o)),
        "lent": FakeLLM(honnete, latence_s=60),
        "casse": FakeLLM(lambda m, o: ReponseLLM(texte="{pas du json", jetons=5)),
        "intrus": FakeLLM(lambda m, o: _appel(m, o, "appeler_agent")),
        "fuite": fidele(champ, lambda ref: FUITE),
        "injecte": FakeLLM(
            lambda m, o: (menteur if "ignore tes règles" in m[0]["content"] else honnete)(m, o)
        ),
    }
    if mode not in scripts:
        raise ValueError(f"saboteur inconnu : {mode!r}")
    return scripts[mode]


# ------------------------------------------------------------------ configuration

AGENTS_LLM = ("pieces", "estimation", "antifraude", "decision")


class ConfigLLM(BaseModel):
    """Le LLM d'un agent : le modèle est une configuration, pas du code (dossier 1.4 ter)."""

    fournisseur: Literal["azure"] = "azure"
    modele: str
    delai_agent_s: float = Field(default=1.2, gt=0)
    jetons_max: int = Field(default=3000, gt=0)
    tours_max: int = Field(default=3, ge=1)
    temperature: float = 0.0
    vision: bool = False  # profil multimodal (VLM d'ingestion, dossier 1.4 ter) ; agents : non


class ConfigAgents(BaseSettings):
    """Un ``ConfigLLM`` par agent : ``KALDERA_<AGENT>__MODELE=…`` dans le .env."""

    model_config = SettingsConfigDict(
        env_prefix="KALDERA_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    pieces: ConfigLLM | None = None
    estimation: ConfigLLM | None = None
    antifraude: ConfigLLM | None = None
    decision: ConfigLLM | None = None
    relance: ConfigLLM | None = None  # agent de relance de l'espace assuré (UI1), hors moteur
    azure_ai_chat_endpoint: str | None = Field(
        default=None, validation_alias=AliasChoices("AZURE_AI_CHAT_ENDPOINT")
    )
    azure_ai_chat_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("AZURE_AI_CHAT_KEY")
    )


def charger_config() -> ConfigAgents:
    """Lit le .env à chaque appel (pas de cache global) ; remplacée dans les tests."""
    return ConfigAgents()


def fabrique_llm(cfg: ConfigAgents, nom: str) -> ClientLLM | None:
    """Le ClientLLM d'un agent, ou None s'il n'est pas configuré (⇒ repli tracé)."""
    config: ConfigLLM | None = getattr(cfg, nom)
    cle = cfg.azure_ai_chat_key.get_secret_value() if cfg.azure_ai_chat_key else ""
    if config is None or not cfg.azure_ai_chat_endpoint or not cle:
        return None
    return AzureLLM.depuis(config, cfg.azure_ai_chat_endpoint, cle)


# ------------------------------------------------------------------ adaptateur Azure


def client_azure(config: ConfigLLM, endpoint: str, cle: str, delai_s: float) -> Any:
    """``ChatCompletionsClient`` (azure-ai-inference), partagé par les agents et le VLM."""
    from azure.ai.inference import ChatCompletionsClient
    from azure.core.credentials import AzureKeyCredential

    return ChatCompletionsClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(cle),
        model=config.modele,
        temperature=config.temperature,
        max_tokens=config.jetons_max,
        # bornes HTTP : l'appel abandonné au délai ne survit pas plus de ~delai + 1 s
        connection_timeout=2,
        read_timeout=math.ceil(delai_s) + 1,
        retry_total=0,
    )


class AzureLLM:
    """Azure AI Foundry (``ChatCompletionsClient``) derrière le port ClientLLM."""

    def __init__(self, config: ConfigLLM, client: Any) -> None:
        self.modele = config.modele
        self._client = client

    @classmethod
    def depuis(cls, config: ConfigLLM, endpoint: str, cle: str) -> AzureLLM:
        return cls(config, client_azure(config, endpoint, cle, config.delai_agent_s))

    def completer(
        self,
        systeme: str,
        messages: list[dict[str, Any]],
        outils: list[dict[str, Any]],
        timeout_s: float,
    ) -> ReponseLLM:
        from azure.core.exceptions import AzureError

        historique = [{"role": "system", "content": systeme}, *map(_vers_azure, messages)]
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            reponse = pool.submit(
                self._client.complete, messages=historique, tools=outils or None
            ).result(timeout=timeout_s)
            message = reponse.choices[0].message
            appels = message.tool_calls or []
            return ReponseLLM(
                texte=None if appels else (message.content or None),
                appels_outils=[
                    AppelOutil(
                        id=a.id or f"{a.function.name}-{i}",
                        nom=a.function.name,
                        arguments=json.loads(a.function.arguments or "{}"),
                    )
                    for i, a in enumerate(appels)
                ],
                jetons=reponse.usage.total_tokens if reponse.usage else 0,
            )
        except DelaiDepasse as exc:
            raise ErreurLLM(f"délai de {timeout_s:.2f} s dépassé") from exc
        except (AzureError, ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ErreurLLM(f"erreur du fournisseur ou réponse mal formée : {exc!r}") from exc
        finally:
            # ponytail: au délai, le thread HTTP est abandonné mais borné par read_timeout
            # (pas de retry) ; client async du SDK (azure.ai.inference.aio) si cela ne suffit plus
            pool.shutdown(wait=False)


def _vers_azure(message: dict[str, Any]) -> dict[str, Any]:
    """Message interne → format chat completions (les appels d'outils en ``tool_calls``)."""
    if message["role"] == "user":
        return {"role": "user", "content": message["content"]}
    if message["role"] == "tool":
        return {"role": "tool", "content": message["content"], "tool_call_id": message["id"]}
    return {
        "role": "assistant",
        "content": message.get("content") or "",
        "tool_calls": [
            {
                "id": a["id"],
                "type": "function",
                "function": {
                    "name": a["nom"],
                    "arguments": json.dumps(a["arguments"], ensure_ascii=False),
                },
            }
            for a in message["appels"]
        ],
    }
