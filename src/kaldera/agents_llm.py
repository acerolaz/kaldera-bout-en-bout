"""Agents LLM (dossier 1.4 → 1.4 ter) : « le LLM raisonne, l'outil calcule, le code vérifie ».

Chaque agent calcule d'abord la référence déterministe (la classe d'``agents.py``, qui sert
de repli), expose cette référence au LLM par ses outils, puis compare la sortie du LLM à la
référence (``gardes_fous``). Toute défaillance renvoie la référence, tracée ``mode = repli``.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib import resources
from time import monotonic, perf_counter
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel

from . import espace_assure, regles
from .agents import AgentAntifraude, AgentDecision, AgentEstimation, AgentPieces, Evaluateur
from .disjoncteur import Disjoncteur
from .etat import AvisFraude, Bornes, Estimation, Issue, Pieces
from .gardes_fous import (
    Controle,
    controle_antifraude,
    controle_decision,
    controle_estimation,
    controle_pieces,
    verifier_sortie,
)
from .llm import ClientLLM, ConfigLLM, ErreurLLM

Vue = dict[str, Any]
Repli = Callable[[Vue], dict[str, Any]]
IDENTITE = ("id_client", "nom", "prenom", "email", "telephone", "iban", "adresse")


class OutilRefuse(Exception):
    """Outil hors allowlist, ou trop d'appels d'outils."""


class ToursEpuises(Exception):
    """Le LLM n'a pas conclu dans ``tours_max`` tours."""


class MesureAgent(BaseModel):
    mode: Literal["llm", "repli"]
    cause: str | None = None
    violations: list[str] = []
    modele: str | None = None
    version_prompt: str
    tours_llm: int = 0
    jetons: int = 0
    latence_llm_ms: float = 0.0
    sortie_rejetee: bool = False


@dataclass(frozen=True)
class Outil:
    nom: str
    description: str
    fn: Callable[[dict[str, Any]], Any]
    parametres: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.nom,
                "description": self.description,
                "parameters": self.parametres,
            },
        }


@dataclass(frozen=True)
class SpecAgent:
    """Ce qui distingue un agent des autres : uniquement des données (fabrique, EX-D36)."""

    section: str
    modele_section: type[BaseModel]
    champ: str  # champ rédigé par le LLM
    gabarit: Callable[[dict[str, Any]], str | None]  # texte du repli
    outils: Callable[[Vue, dict[str, Any]], list[Outil]]  # (vue, référence) → outils exclusifs
    controle: Controle
    fabrique_repli: Callable[[Bornes, Evaluateur | None], Repli]
    prives: tuple[str, ...] = ()  # champs jamais montrés au LLM, recopiés de la référence


# ------------------------------------------------------------------ outils par agent


def _outils_pieces(vue: Vue, ref: dict[str, Any]) -> list[Outil]:
    demande, relances, depots = vue["demande"], vue["relances"], vue["depots"]
    requises = regles.PIECES_EXIGEES[demande["sinistre"]["type"]]

    def lire_depot(args: dict[str, Any]) -> Any:
        k = args.get("k")
        if not isinstance(k, int) or isinstance(k, bool) or k != relances or relances < 1:
            return {"refus": f"seul le dépôt n°{relances} est lisible"}
        return [d for t in requises if (d := espace_assure.depot_pour(depots, t, k - 1))]

    entier = {"type": "object", "properties": {"k": {"type": "integer"}}, "required": ["k"]}
    return [
        Outil("verifier_completude", "Statut des pièces (fait foi).", lambda a: ref),
        Outil(
            "pieces_requises", "Types de pièces exigés pour ce sinistre.", lambda a: list(requises)
        ),
        Outil("lister_pieces", "Pièces jointes à la demande.", lambda a: vue["initiales"]),
        Outil(
            "lire_depot", "Dépôt n°k de l'espace assuré (k = relance en cours).", lire_depot, entier
        ),
    ]


def _outils_estimation(vue: Vue, ref: dict[str, Any]) -> list[Outil]:
    formule = vue["demande"]["contrat"]["formule"]
    bareme = {k: v for k, v in regles.FORMULES[formule].items() if k in ("franchise", "plafond")}
    return [
        Outil("calculer_estimation", "Montant estimé (fait foi).", lambda a: ref),
        Outil("bareme", "Franchise et plafond de la formule du contrat.", lambda a: bareme),
    ]


def _outils_antifraude(vue: Vue, ref: dict[str, Any]) -> list[Outil]:
    avis = ref.get("avis") or {}
    public = {k: v for k, v in ref.items() if k != "avis"}
    resume = {**public, "niveau": avis.get("niveau"), "score": avis.get("score")}

    def consulter(args: dict[str, Any]) -> Any:
        if not ref["requis"]:
            return {**public, "refus": "aucun indicateur F1–F4 : appel au partenaire interdit"}
        return resume  # avis mémorisé : le partenaire n'est jamais rappelé (EX-D19)

    return [
        Outil("consulter_partenaire", "Avis du partenaire anti-fraude (fait foi).", consulter),
        Outil(
            "calculer_indicateurs", "Indicateurs F1–F4 levés.", lambda a: ref.get("indicateurs", [])
        ),
    ]


def _outils_decision(vue: Vue, ref: dict[str, Any]) -> list[Outil]:
    return [
        Outil("appliquer_regles_s10", "Issue selon les règles §10 (fait foi).", lambda a: ref),
        Outil("gabarit_motif", "Motif type de la règle appliquée.", lambda a: ref["motif"]),
    ]


# ------------------------------------------------------------------ gabarits (repli)


def _gabarit_pieces(ref: dict[str, Any]) -> str | None:
    if ref["statut"] != "incomplet":
        return None
    return (
        f"Bonjour, il nous manque encore : {', '.join(ref['manquantes'])}. "
        "Merci de les déposer dans votre espace assuré."
    )


def _gabarit_estimation(ref: dict[str, Any]) -> str:
    return (
        f"Montant retenu {ref['retenu']:.2f} € moins la franchise de {ref['franchise']:.2f} €, "
        f"dans la limite du plafond de {ref['plafond']:.2f} € : {ref['estime']:.2f} € estimés."
    )


def _gabarit_antifraude(ref: dict[str, Any]) -> str:
    if not ref["requis"]:
        return "Aucun indicateur F1–F4 levé : partenaire non consulté."
    # `niveau` : résumé vu par le LLM (sans l'avis brut) ; `avis` : référence complète
    niveau = ref.get("niveau") or (ref.get("avis") or {}).get("niveau")
    niveau = niveau or "indisponible (mode dégradé §9)"
    return f"Indicateurs levés : {', '.join(ref['indicateurs'])}. Avis du partenaire : {niveau}."


def _sans_partenaire(demande: dict[str, Any], timeout: float) -> None:
    """Évaluateur absent : partenaire indisponible (mode dégradé §9)."""


SPECS: Mapping[str, SpecAgent] = MappingProxyType(
    {
        "pieces": SpecAgent(
            "pieces",
            Pieces,
            "message_relance",
            _gabarit_pieces,
            _outils_pieces,
            controle_pieces,
            lambda b, e: AgentPieces(),
        ),
        "estimation": SpecAgent(
            "estimation",
            Estimation,
            "explication",
            _gabarit_estimation,
            _outils_estimation,
            controle_estimation,
            lambda b, e: AgentEstimation(),
        ),
        "antifraude": SpecAgent(
            "avis_fraude",
            AvisFraude,
            "note",
            _gabarit_antifraude,
            _outils_antifraude,
            controle_antifraude,
            lambda b, e: AgentAntifraude(e or _sans_partenaire, b.delai_partenaire_s),
            prives=("avis", "cause"),
        ),
        "decision": SpecAgent(
            "issue",
            Issue,
            "motif",
            lambda ref: ref["motif"],
            _outils_decision,
            controle_decision,
            lambda b, e: AgentDecision(),
        ),
    }
)


# ------------------------------------------------------------------ agent


class AgentLLM:
    """Un agent métier : son LLM, son prompt, ses outils, son garde-fou, son repli."""

    def __init__(
        self,
        nom: str,
        spec: SpecAgent,
        repli: Repli,
        llm: ClientLLM | None,
        config: ConfigLLM,
        bornes: Bornes,
        disjoncteur: Disjoncteur | None = None,
    ) -> None:
        self.nom, self.spec, self.repli, self.llm = nom, spec, repli, llm
        self.config, self.bornes = config, bornes
        self.disjoncteur = disjoncteur
        self.prompt = (resources.files("kaldera") / "prompts" / f"{nom}.md").read_text("utf-8")
        self.version_prompt = hashlib.sha256(self.prompt.encode()).hexdigest()[:8]

    def executer(self, vue: Vue, budget_s: float) -> tuple[dict[str, Any], MesureAgent]:
        debut = monotonic()
        ref = self._reference(vue)
        mesure = MesureAgent(
            mode="repli",
            modele=self.llm.modele if self.llm else None,
            version_prompt=self.version_prompt,
        )
        if self.llm is None:
            mesure.cause = "llm_non_configure"
            return {self.spec.section: ref}, mesure
        if self.disjoncteur is not None and self.disjoncteur.ouvert():
            mesure.cause = "disjoncteur"  # LLM en panne pour tous : aucun appel, rien de noté
            return {self.spec.section: ref}, mesure
        # le temps des outils (dont l'A2A de la référence) ne compte pas dans le budget LLM
        budget = min(self.config.delai_agent_s, budget_s - (monotonic() - debut))
        if budget < self.bornes.delai_min_llm_s:
            mesure.cause = "budget"
            return {self.spec.section: ref}, mesure
        patch = self._tenter(self.llm, vue, ref, budget, mesure)
        if self.disjoncteur is not None:
            self.disjoncteur.noter(repli=patch is None)
        return {self.spec.section: ref if patch is None else patch}, mesure

    def _tenter(
        self, llm: ClientLLM, vue: Vue, ref: dict[str, Any], budget: float, mesure: MesureAgent
    ) -> dict[str, Any] | None:
        """Une tentative LLM : le patch accepté, ou None (repli, cause dans ``mesure``)."""
        try:
            patch = self._boucle(llm, vue, ref, budget, mesure)
        except ErreurLLM:
            mesure.cause = "erreur_llm"
        except (
            ValueError
        ):  # JSON invalide ou patch non conforme (ValidationError hérite de ValueError)
            mesure.cause, mesure.sortie_rejetee = "sortie_invalide", True
        except OutilRefuse:
            mesure.cause = "outil_refuse"
        except ToursEpuises:
            mesure.cause = "tours_max"
        else:
            mesure.violations = verifier_sortie(
                patch, ref, vue, self.spec.champ, self.spec.prives, self.spec.controle
            )
            if not mesure.violations:
                mesure.mode = "llm"
                return patch
            mesure.cause, mesure.sortie_rejetee = "garde_fou", True
        return None

    def _reference(self, vue: Vue) -> dict[str, Any]:
        section: dict[str, Any] = self.repli(copy.deepcopy(vue))[self.spec.section]
        ref = self.spec.modele_section.model_validate(section).model_dump()
        return {**ref, self.spec.champ: self.spec.gabarit(ref)}

    def _boucle(
        self, llm: ClientLLM, vue: Vue, ref: dict[str, Any], budget: float, mesure: MesureAgent
    ) -> dict[str, Any]:
        outils = {o.nom: o for o in self.spec.outils(vue, ref)}
        schemas = [o.schema() for o in outils.values()]
        messages: list[dict[str, Any]] = [{"role": "user", "content": _message(vue)}]
        echeance, appels = monotonic() + budget, 0
        for _ in range(self.config.tours_max):
            restant = echeance - monotonic()
            if restant <= 0:
                raise ErreurLLM("budget épuisé")
            top = perf_counter()
            try:
                reponse = llm.completer(self.prompt, messages, schemas, restant)
            finally:  # un appel hors délai compte : sa latence est le signal d'alerte
                mesure.tours_llm += 1
                mesure.latence_llm_ms = round(
                    mesure.latence_llm_ms + (perf_counter() - top) * 1000, 2
                )
            mesure.jetons += reponse.jetons
            if not reponse.appels_outils:
                return self._patch(reponse.texte, ref)
            messages.append(
                {
                    "role": "assistant",
                    "content": reponse.texte,
                    "appels": [a.model_dump() for a in reponse.appels_outils],
                }
            )
            for appel in reponse.appels_outils:
                appels += 1
                if appel.nom not in outils or appels > self.bornes.appels_outil_max:
                    raise OutilRefuse(appel.nom)
                try:
                    resultat = outils[appel.nom].fn(appel.arguments)
                except (TypeError, KeyError, IndexError, AttributeError) as exc:
                    raise OutilRefuse(appel.nom) from exc
                messages.append(
                    {
                        "role": "tool",
                        "id": appel.id,
                        "nom": appel.nom,
                        "content": json.dumps(resultat, ensure_ascii=False, default=str),
                    }
                )
        raise ToursEpuises()

    def _patch(self, texte: str | None, ref: dict[str, Any]) -> dict[str, Any]:
        brut = json.loads(_sans_balises(texte or ""))
        if not isinstance(brut, dict):
            raise ValueError("la sortie du LLM n'est pas un objet JSON")
        complet = {**brut, **{p: ref[p] for p in self.spec.prives}}
        patch: dict[str, Any] = self.spec.modele_section.model_validate(complet).model_dump()
        return patch


def _sans_balises(texte: str) -> str:
    """Retire les balises ```json … ``` dont les LLM entourent souvent leur réponse."""
    return re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", texte)


def _message(vue: Vue) -> str:
    """La vue, sans identité ni coordonnées (EX-D34), balisée comme donnée non fiable."""
    vue = copy.deepcopy(vue)
    if "demande" in vue:
        assure = vue["demande"].get("assure", {})
        vue["demande"]["assure"] = {k: v for k, v in assure.items() if k not in IDENTITE}
        # minimisation locale du numéro de contrat et du texte libre (cf. orchestrateur._minimisee)
        vue["demande"].get("contrat", {}).pop("numero", None)
        vue["demande"].get("sinistre", {}).pop("description", None)
    avis = vue.get("avis_fraude")
    if isinstance(avis, dict) and avis.get("avis"):
        brut = avis["avis"]
        avis["avis"] = {"niveau": brut.get("niveau"), "score": brut.get("score")}
    contenu = json.dumps(vue, ensure_ascii=False, default=str)
    return f"<donnees_non_fiables>{contenu}</donnees_non_fiables>"


def creer_agent(
    nom: str,
    llm: ClientLLM | None,
    config: ConfigLLM | None,
    bornes: Bornes,
    evaluer: Evaluateur | None = None,
    disjoncteur: Disjoncteur | None = None,
) -> AgentLLM:
    """Fabrique d'agents (EX-D36) : tout ce qui varie vient de ``SPECS[nom]``."""
    spec = SPECS[nom]
    return AgentLLM(
        nom,
        spec,
        spec.fabrique_repli(bornes, evaluer),
        llm,
        config or ConfigLLM(modele="aucun"),
        bornes,
        disjoncteur,
    )
