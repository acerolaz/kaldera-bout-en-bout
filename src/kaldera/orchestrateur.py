"""Orchestrateur : moteur de la machine à états d'une demande (dossier 2.2 bis).

Le moteur ne contient aucune règle métier : il lit la table de transitions, évalue la
garde globale, donne à chaque agent une vue filtrée, contrôle et fusionne son patch,
puis trace l'étape. « Les agents proposent, l'orchestration impose. »
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping
from time import monotonic, perf_counter
from typing import Any

from . import llm, partenaire, postgres, regles
from .agents import NIVEAUX_AVIS, Evaluateur, is_eligible
from .agents_llm import AgentLLM, MesureAgent, creer_agent
from .llm import ClientLLM, ConfigAgents
from .etat import BORNES, PROPRIETAIRES, Arret, Bornes, ContratDemande, EtatDemande
from .memoire import DepotDepuisDemande
from .ports import DepotPieces, ErreurPersistance, Snapshots
from .machine import TERMINAUX, Etat, TransitionInconnue, garde_entree, transition

LOGGER = logging.getLogger(__name__)
NIVEAU_0 = DepotDepuisDemande()  # sans état : partagé

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
        llms: Mapping[str, ClientLLM | None] | None = None,
        config: ConfigAgents | None = None,
        depot: DepotPieces | None = None,
        snapshots: Snapshots | None = None,
    ) -> None:
        self.bornes = bornes or BORNES
        self.depot = depot or NIVEAU_0
        # sans base configurée : aucune persistance ; les pièces restent lues dans la demande
        # (niveau 0) tant que l'ingestion (SP3) ne remplit pas la table pieces
        self.snapshots = snapshots if snapshots is not None else postgres.snapshots_par_defaut()
        cfg = config or self._charger_config()
        if llms is None:
            llms = {nom: llm.fabrique_llm(cfg, nom) for nom in llm.AGENTS_LLM}

        def evaluer_partenaire(demande: dict[str, Any], timeout: float) -> dict[str, Any] | None:
            return partenaire.evaluer_risque(demande, partenaire_url, timeout=timeout)

        def agent(nom: str) -> AgentLLM:
            return creer_agent(
                nom, llms.get(nom), getattr(cfg, nom), self.bornes, evaluer or evaluer_partenaire
            )

        # état → action (agent-as-tool) ; l'éligibilité est un tool appelé directement
        self.actions: dict[Etat, Action | AgentLLM] = {
            Etat.ELIGIBILITE: lambda vue: {"eligibilite": is_eligible(vue["demande"])},
            Etat.PIECES: agent("pieces"),
            Etat.ESTIMATION: agent("estimation"),
            Etat.ANTIFRAUDE: agent("antifraude"),
            Etat.DECISION: agent("decision"),
        }

    @staticmethod
    def _charger_config() -> ConfigAgents:
        try:
            return llm.charger_config()
        except ValueError as exc:  # ValidationError : .env malformé, jamais bloquant
            LOGGER.warning("config LLM invalide, agents déterministes : %s", exc)
            return ConfigAgents.model_construct()  # aucun agent configuré, sans relire l'env

    def traiter(self, demande: dict[str, Any]) -> dict[str, Any]:
        etat = EtatDemande(demande={})
        try:
            etat.demande = copy.deepcopy(demande)  # validée : une entrée malformée passe au filet
            self._executer(etat)
        except Exception as exc:  # noqa: BLE001 — EX-01 : seule capture large du paquet (filet)
            self._filet(etat, exc)
        fiche = construire_fiche(etat)
        if self._persister(etat, lambda s: s.terminer(etat, fiche)) is False:
            LOGGER.warning(
                "demande %s déjà escaladée par le reaper : la base garde l'escalade de secours",
                etat.demande.get("reference"),
            )
        return fiche

    @staticmethod
    def _filet(etat: EtatDemande, exc: Exception) -> None:
        """Filet niveau 1 (dossier 2.5) : lit l'état, ne relance rien, n'appelle aucun agent."""
        LOGGER.exception("filet de sécurité, demande %s", etat.demande.get("reference"))
        etat.escalade_forcee = f"filet de sécurité : {type(exc).__name__}"
        etat.trace.append(
            _etape_sans_action(
                agent="orchestrateur",
                action="filet_securite",
                statut="echec",
                de=etat.etat_courant,
                vers=Etat.ESCALADE.value,
                garde="filet",
            )
        )

    def executer(self, demande: dict[str, Any]) -> EtatDemande:
        etat = EtatDemande(demande=copy.deepcopy(demande))
        self._executer(etat)
        return etat

    def _executer(self, etat: EtatDemande) -> None:
        contrat = etat.demande.get("contrat")
        # niveau 0 : provenance absente ⇒ valide ; contrat malformé ⇒ l'éligibilité échouera, tracée
        etat.contrat = ContratDemande.model_validate(contrat if isinstance(contrat, dict) else {})
        self._persister(etat, lambda s: s.debuter(etat))
        courant = Etat.ELIGIBILITE
        while courant not in TERMINAUX:
            if courant is not Etat.DECISION and self._garde_globale(etat, courant):
                courant = Etat.DECISION  # TG : escalade forcée, l'issue reste à decision
                continue
            if (entree := garde_entree(courant, etat, self.bornes)) is not None:
                courant = self._sauter(etat, courant, *entree)  # T0 : action non exécutée
                continue
            courant = self._etape(etat, courant)

    # ------------------------------------------------------------------ un tour

    def _etape(self, etat: EtatDemande, courant: Etat) -> Etat:
        section = SECTION_DE[courant]
        agent = PROPRIETAIRES[section]
        debut, statut, ecrit = perf_counter(), "ok", []
        mesure: MesureAgent | None = None
        try:
            action, vue = self.actions[courant], vue_filtree(etat, courant, self.bornes, self.depot)
            if isinstance(action, AgentLLM):
                patch, mesure = action.executer(vue, self._budget(etat, courant))
            else:  # tool d'éligibilité, ou action remplacée dans un test
                patch = action(vue)
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
                **(mesure.model_dump() if mesure else {}),
            }
        )
        etat.etat_courant = suivant.value
        self._persister(etat, lambda s: s.enregistrer(etat))  # exécution durable (2.5)
        return suivant

    def _sauter(self, etat: EtatDemande, courant: Etat, suivant: Etat, garde: str) -> Etat:
        """Garde d'entrée vraie : l'action de l'état n'est pas exécutée, l'étape est tracée."""
        etat.compteurs.etapes += 1
        etat.trace.append(
            _etape_sans_action(
                agent=PROPRIETAIRES[SECTION_DE[courant]],
                action=courant.value,
                de=courant.value,
                vers=suivant.value,
                garde=garde,
            )
        )
        etat.etat_courant = suivant.value
        self._persister(etat, lambda s: s.enregistrer(etat))  # exécution durable (2.5)
        return suivant

    # ponytail: base en panne puis processus mort ⇒ hors du reaper ; file d'écritures si mesuré
    def _persister(self, etat: EtatDemande, ecrire: Callable[[Snapshots], Any]) -> Any:
        """Écrit un snapshot ; la base ne bloque jamais une décision (EX-01)."""
        if self.snapshots is None:
            return None
        try:
            return ecrire(self.snapshots)
        except ErreurPersistance as exc:
            LOGGER.warning(
                "persistance en échec, demande %s : %s", etat.demande.get("reference"), exc
            )
            if etat.trace:
                etat.trace[-1]["persistance"] = "echec"
            return None

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

    def _budget(self, etat: EtatDemande, courant: Etat) -> float:
        """Budget LLM dégressif (dossier 2.3 bis) : on rogne le LLM, jamais l'A2A ni decision."""
        restant = self.bornes.duree_max_s - (monotonic() - etat.debut)
        reserves = 0.0
        if courant in (Etat.PIECES, Etat.ESTIMATION):  # l'A2A n'a pas encore eu lieu
            reserves += self.bornes.delai_partenaire_s
        if courant is not Etat.DECISION:
            reserves += self.bornes.reserve_decision_s
        return max(0.0, restant - reserves)


def _etape_sans_action(**champs: Any) -> dict[str, Any]:
    """Étape de trace sans action d'agent (garde d'entrée, filet) : rien écrit, rien mesuré."""
    return {"ecrit": [], "statut": "ok", "duree_ms": 0.0, "appels_externes": 0, **champs}


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


def vue_filtree(
    etat: EtatDemande, courant: Etat, bornes: Bornes = BORNES, depot: DepotPieces = NIVEAU_0
) -> dict[str, Any]:
    """Ce que voit l'action de l'état courant — des copies : la demande reste immuable."""
    demande = copy.deepcopy(etat.demande)
    if courant is Etat.ELIGIBILITE:
        return {"demande": demande}
    if courant is Etat.PIECES:
        # claim check : l'agent ne voit que des descripteurs, chargés par le port
        demande.pop("pieces", None)
        demande.pop("espace_assure", None)
        return {
            "demande": demande,
            "relances": etat.compteurs.relances,
            "initiales": [p.model_dump(mode="json") for p in depot.initiales(etat.demande)],
            "depots": [p.model_dump(mode="json") for p in depot.depots(etat.demande)],
        }
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
        "contrat": {
            "statut_extraction": etat.contrat.statut_extraction,
            "violations": list(etat.contrat.violations),
        },
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
        dernier = etat.trace[-1]["de"] if etat.trace else etat.etat_courant
        raison = etat.escalade_forcee or "aucune issue produite"
        issue = {
            "issue": "escalade",
            "decision": None,
            "montant_rembourse": None,
            "motif": f"Escalade de secours : {raison} (dernier état : {dernier})",
            "file": file_prudente(etat),
            "mode_degrade": False,
        }
    return {
        "reference": etat.demande.get("reference"),
        **issue,
        "avis_fraude": etat.avis_fraude.avis if etat.avis_fraude else None,
        "trace": etat.trace,
        "arret": etat.arret.model_dump() if etat.arret else None,
    }


def file_prudente(etat: EtatDemande) -> str:
    """File la plus prudente d'une fiche de secours (dossier 2.5), lue dans l'état partagé."""
    if etat.contrat.statut_extraction != "valide":
        return "gestionnaire"
    avis = etat.avis_fraude
    if avis is None:  # antifraude non atteint : indicateurs inconnus
        return "gestionnaire"
    niveau = (avis.avis or {}).get("niveau") if avis.statut == "avis" else None
    if niveau == "eleve":
        return "cellule_fraude"
    sans_avis = niveau not in NIVEAUX_AVIS
    estime = etat.estimation.estime if etat.estimation else 0.0
    if avis.requis and sans_avis and estime > regles.SEUIL_MODE_DEGRADE:
        return "cellule_fraude"
    return "gestionnaire"
