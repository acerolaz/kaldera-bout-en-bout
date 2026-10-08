"""Port LLM des agents métier (dossier 1.4 → 1.4 ter).

Les agents ne connaissent que ``ClientLLM`` ; LangChain n'apparaît que dans l'adaptateur
Azure. ``FakeLLM`` rejoue un script : il sert aux tests (niveaux ① et ② du plan d'épreuve).
"""

from __future__ import annotations

import json
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


class ConfigAgents(BaseSettings):
    """Un ``ConfigLLM`` par agent : ``KALDERA_<AGENT>__MODELE=…`` dans le .env."""

    model_config = SettingsConfigDict(
        env_prefix="KALDERA_", env_nested_delimiter="__", env_file=".env", extra="ignore"
    )

    pieces: ConfigLLM | None = None
    estimation: ConfigLLM | None = None
    antifraude: ConfigLLM | None = None
    decision: ConfigLLM | None = None
    azure_ai_endpoint: str | None = Field(
        default=None, validation_alias=AliasChoices("AZURE_AI_ENDPOINT")
    )
    azure_ai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("AZURE_AI_API_KEY")
    )


def charger_config() -> ConfigAgents:
    """Lit le .env à chaque appel (pas de cache global) ; remplacée dans les tests."""
    return ConfigAgents()


def fabrique_llm(cfg: ConfigAgents, nom: str) -> ClientLLM | None:
    """Le ClientLLM d'un agent, ou None s'il n'est pas configuré (⇒ repli tracé)."""
    config: ConfigLLM | None = getattr(cfg, nom)
    if config is None or not cfg.azure_ai_endpoint or cfg.azure_ai_api_key is None:
        return None
    return AzureLLM.depuis(config, cfg.azure_ai_endpoint, cfg.azure_ai_api_key.get_secret_value())


# ------------------------------------------------------------------ adaptateur Azure


class AzureLLM:
    """Azure AI (langchain-azure-ai) derrière le port ClientLLM."""

    def __init__(self, config: ConfigLLM, chat_model: Any) -> None:
        self.modele = config.modele
        self._chat = chat_model

    @classmethod
    def depuis(cls, config: ConfigLLM, endpoint: str, cle: str) -> AzureLLM:
        from langchain_azure_ai.chat_models import AzureAIChatCompletionsModel

        chat = AzureAIChatCompletionsModel(
            endpoint=endpoint,
            credential=cle,
            model=config.modele,
            temperature=config.temperature,
            max_tokens=config.jetons_max,
        )
        return cls(config, chat)

    def completer(
        self,
        systeme: str,
        messages: list[dict[str, Any]],
        outils: list[dict[str, Any]],
        timeout_s: float,
    ) -> ReponseLLM:
        from azure.core.exceptions import AzureError
        from langchain_core.messages import SystemMessage

        historique = [SystemMessage(systeme), *map(_vers_langchain, messages)]
        modele = self._chat.bind_tools(outils) if outils else self._chat
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            reponse = pool.submit(modele.invoke, historique).result(timeout=timeout_s)
        except DelaiDepasse as exc:
            raise ErreurLLM(f"délai de {timeout_s:.2f} s dépassé") from exc
        except AzureError as exc:
            raise ErreurLLM(f"erreur du fournisseur : {exc}") from exc
        finally:
            # ponytail: au délai, le thread de l'appel HTTP est abandonné (il finit seul) ;
            # passer à l'API async du SDK si les threads orphelins deviennent un problème
            pool.shutdown(wait=False)
        contenu = (
            reponse.content if isinstance(reponse.content, str) else json.dumps(reponse.content)
        )
        return ReponseLLM(
            texte=None if reponse.tool_calls else (contenu or None),
            appels_outils=[
                AppelOutil(id=a.get("id") or a["name"], nom=a["name"], arguments=a["args"])
                for a in reponse.tool_calls
            ],
            jetons=(reponse.usage_metadata or {}).get("total_tokens", 0),
        )


def _vers_langchain(message: dict[str, Any]) -> Any:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    if message["role"] == "user":
        return HumanMessage(message["content"])
    if message["role"] == "tool":
        return ToolMessage(message["content"], tool_call_id=message["id"])
    return AIMessage(
        content=message.get("content") or "",
        tool_calls=[
            {"name": a["nom"], "args": a["arguments"], "id": a["id"]} for a in message["appels"]
        ],
    )
