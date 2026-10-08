"""Port LLM des agents métier (dossier 1.4 → 1.4 ter).

Les agents ne connaissent que ``ClientLLM`` ; LangChain n'apparaît que dans l'adaptateur
Azure. ``FakeLLM`` rejoue un script : il sert aux tests (niveaux ① et ② du plan d'épreuve).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel


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
