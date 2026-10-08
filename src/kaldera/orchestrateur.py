"""Orchestrateur : moteur de la machine à états d'une demande (dossier 2.2 bis).

Le moteur ne contient aucune règle métier : il lit la table de transitions, évalue la
garde globale, donne à chaque agent une vue filtrée, contrôle et fusionne son patch,
puis trace l'étape. « Les agents proposent, l'orchestration impose. »
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from time import monotonic, perf_counter
from typing import Any

from . import partenaire
from .agents import (
    AgentAntifraude,
    AgentDecision,
    AgentEstimation,
    AgentPieces,
    Evaluateur,
    is_eligible,
)
from .etat import BORNES, PROPRIETAIRES, Arret, Bornes, EtatDemande
from .machine import TERMINAUX, Etat, TransitionInconnue, transition

Action = Callable[[dict[str, Any]], dict[str, Any]]

# état de la machine → section métier que son action écrit
SECTION_DE: dict[Etat, str] = {
    Etat.ELIGIBILITE: "eligibilite",
    Etat.PIECES: "pieces",
    Etat.ESTIMATION: "estimation",
    Etat.ANTIFRAUDE: "avis_fraude",
    Etat.DECISION: "issue",
}


class ErreurEcriture(Exception):
    """Patch refusé : section d'un autre agent, ou section déjà écrite."""


class Orchestrateur:
    def __init__(
        self,
        partenaire_url: str | None = None,
        bornes: Bornes | None = None,
        evaluer: Evaluateur | None = None,
    ) -> None:
        self.bornes = bornes or BORNES

        def evaluer_partenaire(demande: dict[str, Any], timeout: float) -> dict[str, Any] | None:
            return partenaire.evaluer_risque(demande, partenaire_url, timeout=timeout)

        # état → action (agent-as-tool) ; l'éligibilité est un tool appelé directement
        self.actions: dict[Etat, Action] = {
            Etat.ELIGIBILITE: lambda vue: {"eligibilite": is_eligible(vue["demande"])},
            Etat.PIECES: AgentPieces(),
            Etat.ESTIMATION: AgentEstimation(),
            Etat.ANTIFRAUDE: AgentAntifraude(
                evaluer or evaluer_partenaire, self.bornes.delai_partenaire_s
            ),
            Etat.DECISION: AgentDecision(),
        }

    def traiter(self, demande: dict[str, Any]) -> dict[str, Any]:
        return construire_fiche(self.executer(demande))

    def executer(self, demande: dict[str, Any]) -> EtatDemande:
        etat = EtatDemande(demande=copy.deepcopy(demande))
        courant = Etat.ELIGIBILITE
        while courant not in TERMINAUX:
            if courant is not Etat.DECISION and self._garde_globale(etat, courant):
                courant = Etat.DECISION  # TG : escalade forcée, l'issue reste à decision
                continue
            courant = self._etape(etat, courant)
        return etat

    # ------------------------------------------------------------------ un tour

    def _etape(self, etat: EtatDemande, courant: Etat) -> Etat:
        section = SECTION_DE[courant]
        agent = PROPRIETAIRES[section]
        debut, statut, ecrit = perf_counter(), "ok", []
        try:
            patch = self.actions[courant](vue_filtree(etat, courant, self.bornes))
            fusionner(etat, patch, section)
            ecrit = [section]
            suivant, garde = transition(courant, etat, self.bornes)
        except (
            KeyError,
            ValueError,  # couvre la ValidationError de Pydantic
            TypeError,
            AttributeError,
            ErreurEcriture,
            TransitionInconnue,  # table incomplète : bruyant dans la trace, jamais bloquant
        ) as exc:
            statut, garde = "echec", "echec"
            etat.escalade_forcee = f"échec de l'agent {agent} ({type(exc).__name__})"
            # decision en échec : plus personne pour conclure → fiche de secours
            suivant = Etat.ESCALADE if courant is Etat.DECISION else Etat.DECISION

        externes = 0
        if statut == "ok" and courant is Etat.ANTIFRAUDE and etat.avis_fraude is not None:
            externes = int(etat.avis_fraude.requis)
            if etat.avis_fraude.statut == "indisponible":
                statut = "echec"  # avis non obtenu : compté en échec, mode dégradé en aval
        if courant is Etat.PIECES and statut == "ok":
            self._suivre_relances(etat, suivant)

        etat.compteurs.etapes += 1
        etat.compteurs.appels_externes += externes
        etat.trace.append(
            {
                "agent": agent,
                "action": courant.value,
                "ecrit": ecrit,
                "statut": statut,
                "duree_ms": round((perf_counter() - debut) * 1000, 2),
                "de": courant.value,
                "vers": suivant.value,
                "garde": garde,
                "appels_externes": externes,
            }
        )
        etat.etat_courant = suivant.value
        return suivant

    def _suivre_relances(self, etat: EtatDemande, suivant: Etat) -> None:
        if suivant is Etat.PIECES:  # T4
            etat.compteurs.relances += 1
        elif (
            suivant is Etat.DECISION
            and etat.pieces is not None
            and etat.pieces.statut == "incomplet"
        ):  # T5 sur borne
            etat.arret = Arret(
                borne="relances_pieces_max",
                valeur=etat.compteurs.relances,
                etape=etat.compteurs.etapes + 1,
                etat=Etat.PIECES.value,
            )

    def _garde_globale(self, etat: EtatDemande, courant: Etat) -> bool:
        """TG : une étape reste toujours réservée à decision, la trace ne dépasse pas etapes_max."""
        ecoule = monotonic() - etat.debut
        if etat.compteurs.etapes + 1 >= self.bornes.etapes_max:
            # valeur = étapes consommées ; la dernière restante est réservée à decision
            borne, valeur = "etapes_max", float(etat.compteurs.etapes)
        elif ecoule >= self.bornes.duree_max_s:
            borne, valeur = "duree_max_s", round(ecoule, 3)
        else:
            return False
        etat.arret = Arret(
            borne=borne, valeur=valeur, etape=etat.compteurs.etapes, etat=courant.value
        )
        etat.escalade_forcee = f"borne {borne} atteinte (état {courant.value})"
        return True


# ---------------------------------------------------------------- contrôle d'écriture


def fusionner(etat: EtatDemande, patch: dict[str, Any], section: str) -> None:
    """Applique le patch d'un agent : uniquement sa section, jamais deux fois (sauf relance)."""
    if set(patch) != {section}:
        raise ErreurEcriture(f"patch hors de la section {section!r} : {sorted(patch)}")
    if patch[section] is None:
        raise ErreurEcriture(f"section {section!r} vide")
    if getattr(etat, section) is not None and section != "pieces":
        raise ErreurEcriture(f"section {section!r} déjà écrite")
    setattr(etat, section, patch[section])  # validation Pydantic à l'affectation


# ---------------------------------------------------------------- vues filtrées


def vue_filtree(etat: EtatDemande, courant: Etat, bornes: Bornes = BORNES) -> dict[str, Any]:
    """Ce que voit l'action de l'état courant — des copies : la demande reste immuable."""
    demande = copy.deepcopy(etat.demande)
    if courant is Etat.ELIGIBILITE:
        return {"demande": demande}
    if courant is Etat.PIECES:
        return {"demande": demande, "relances": etat.compteurs.relances}
    if courant is Etat.ESTIMATION:
        return {"demande": demande, "pieces": _section(etat, "pieces")}
    if courant is Etat.ANTIFRAUDE:
        # l'appel partenaire ne doit pas faire dépasser duree_max_s (engagement des 10 s)
        restant = bornes.duree_max_s - (monotonic() - etat.debut)
        return {
            "demande": _minimisee(demande),
            "estimation": _section(etat, "estimation"),
            "delai_s": max(0.0, min(bornes.delai_partenaire_s, restant)),
        }
    return {
        **{
            section: (valeur.model_dump() if (valeur := getattr(etat, section)) else None)
            for section in ("eligibilite", "pieces", "estimation", "avis_fraude")
        },
        "arret": etat.arret.model_dump() if etat.arret else None,
        "escalade_forcee": etat.escalade_forcee,
    }


def _section(etat: EtatDemande, section: str) -> dict[str, Any]:
    valeur = getattr(etat, section)
    if valeur is None:
        raise ErreurEcriture(f"section {section!r} requise mais absente")
    return dict(valeur.model_dump())


def _minimisee(demande: dict[str, Any]) -> dict[str, Any]:
    """Ni identité, ni coordonnées, ni n° de contrat, ni texte libre, ni pièces (EX-03)."""
    contrat = {k: v for k, v in demande["contrat"].items() if k != "numero"}
    sinistre = {k: v for k, v in demande["sinistre"].items() if k != "description"}
    return {
        "reference": demande["reference"],
        "contrat": contrat,
        "sinistre": sinistre,
        "historique": demande.get("historique", {}),
        "assure": {"code_postal": demande.get("assure", {}).get("code_postal")},
    }


# ---------------------------------------------------------------- fiche de décision


def construire_fiche(etat: EtatDemande) -> dict[str, Any]:
    if etat.issue is not None:
        issue = etat.issue.model_dump()
    else:  # filet de sécurité : decision n'a pas conclu
        issue = {
            "issue": "escalade",
            "decision": None,
            "montant_rembourse": None,
            "motif": f"Escalade de secours : {etat.escalade_forcee or 'aucune issue produite'}",
            "file": "gestionnaire",
            "mode_degrade": False,
        }
    return {
        "reference": etat.demande["reference"],
        **issue,
        "avis_fraude": etat.avis_fraude.avis if etat.avis_fraude else None,
        "trace": etat.trace,
        "arret": etat.arret.model_dump() if etat.arret else None,
    }
