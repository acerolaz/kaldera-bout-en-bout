"""Le tool d'éligibilité et les 4 agents spécialistes (dossier 1.1 à 1.3).

Chaque agent reçoit une vue (dict, déjà filtrée par l'orchestrateur) et renvoie un
patch de sa seule section : ``{section: données}``. Aucun agent n'en appelle un
autre, ne connaît les états de la machine, ni n'écrit dans l'état partagé.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import espace_assure, regles

# client A2A injecté : (demande filtrée, timeout en s) → avis ou None si indisponible
Evaluateur = Callable[..., dict[str, Any] | None]


# ------------------------------------------------------------- tool éligibilité


def is_eligible(demande: dict[str, Any]) -> dict[str, Any]:
    """Règles E1–E5 : fonction pure, aucun montant en sortie (le plafond relève de l'estimation)."""
    contrat, sinistre = demande["contrat"], demande["sinistre"]
    formule = regles.FORMULES[contrat["formule"]]
    conditions_ko = []
    if contrat["statut"] != "actif":
        conditions_ko.append("contrat non actif")
    if not contrat["cotisations_a_jour"]:
        conditions_ko.append("cotisations impayées")
    if (
        regles.jours_entre(contrat["date_souscription"], sinistre["date_survenance"])
        < regles.CARENCE_JOURS
    ):
        conditions_ko.append("sinistre survenu pendant la période de carence")
    delai = regles.jours_entre(sinistre["date_survenance"], sinistre["date_declaration"])
    delai_max = (
        regles.DELAI_DECLARATION_VOL_JOURS
        if sinistre["type"] == "vol"
        else regles.DELAI_DECLARATION_JOURS
    )
    if delai > delai_max:
        conditions_ko.append("déclaration hors délai")
    if sinistre["type"] not in formule["garanties"]:
        conditions_ko.append("sinistre non couvert par la formule")
    return {"eligible": not conditions_ko, "conditions_ko": conditions_ko}


# ------------------------------------------------------------------ pieces


class AgentPieces:
    """Présence, lisibilité et types des pièces ; lit le dépôt n°k à la relance n°k."""

    nom = "pieces"

    def __call__(self, vue: dict[str, Any]) -> dict[str, Any]:
        demande, relances = vue["demande"], vue["relances"]
        recues = list(demande.get("pieces", []))
        for tentative in range(relances):
            for type_piece in _manquantes(demande, recues):
                depot = espace_assure.demander_piece(demande, type_piece, tentative)
                if depot is not None:
                    recues.append(depot)
        manquantes = _manquantes(demande, recues)
        if not manquantes:
            statut = "complet"
        elif any(espace_assure.demander_piece(demande, t, relances) for t in manquantes):
            # l'assuré a déjà déposé ce type : une relance peut aboutir (ou re-soumettre
            # le même dépôt illisible — c'est la borne de relances qui tranche)
            statut = "incomplet"
        else:
            statut = "manquant"  # rien à relancer
        return {
            "pieces": {
                "statut": statut,
                "manquantes": manquantes,
                "retenues": [p for p in recues if p.get("lisible", False)],
            }
        }


def _manquantes(demande: dict[str, Any], recues: list[dict[str, Any]]) -> list[str]:
    manquantes = []
    for type_piece in regles.PIECES_EXIGEES[demande["sinistre"]["type"]]:
        du_type = [p for p in recues if p["type"] == type_piece]
        if not du_type or not du_type[-1].get("lisible", False):
            manquantes.append(type_piece)
    return manquantes


# ------------------------------------------------------------------ estimation


class AgentEstimation:
    """Seul agent qui chiffre : franchise, puis plafond (point ambigu tranché, dossier 1.2)."""

    nom = "estimation"

    def __call__(self, vue: dict[str, Any]) -> dict[str, Any]:
        demande = vue["demande"]
        formule = regles.FORMULES[demande["contrat"]["formule"]]
        justifie = round(
            sum(
                p.get("montant") or 0.0 for p in vue["pieces"]["retenues"] if p["type"] == "facture"
            ),
            2,
        )
        retenu = min(demande["sinistre"]["montant_declare"], justifie)
        estime = min(max(retenu - formule["franchise"], 0.0), formule["plafond"])
        return {
            "estimation": {
                "justifie": justifie,
                "retenu": retenu,
                "franchise": formule["franchise"],
                "plafond": formule["plafond"],
                "estime": round(estime, 2),
            }
        }


# ------------------------------------------------------------------ antifraude


class AgentAntifraude:
    """Indicateurs F1–F4 ; seul détenteur du client A2A, un appel au plus par demande."""

    nom = "antifraude"

    def __init__(self, evaluer: Evaluateur, delai_s: float) -> None:
        self.evaluer = evaluer
        self.delai_s = delai_s

    def __call__(self, vue: dict[str, Any]) -> dict[str, Any]:
        demande = vue["demande"]
        indicateurs = indicateurs_fraude(demande, vue["estimation"]["justifie"])
        if not indicateurs:
            return {"avis_fraude": {"requis": False, "statut": "non_requis"}}
        # le moteur peut réduire le délai au temps restant de la demande
        avis = self.evaluer(demande, timeout=min(self.delai_s, vue.get("delai_s", self.delai_s)))
        return {
            "avis_fraude": {
                "requis": True,
                "indicateurs": indicateurs,
                "statut": "indisponible" if avis is None else "avis",
                "avis": avis,
            }
        }


def indicateurs_fraude(demande: dict[str, Any], justifie: float) -> list[str]:
    sinistre = demande["sinistre"]
    anciennete = regles.jours_entre(
        demande["contrat"]["date_souscription"], sinistre["date_survenance"]
    )
    regles_f = {
        "F1": sinistre["montant_declare"] >= regles.SEUIL_MONTANT_FRAUDE,
        "F2": anciennete < regles.ANCIENNETE_SENSIBLE_JOURS,
        "F3": demande.get("historique", {}).get("sinistres_12_mois", 0)
        >= regles.FREQUENCE_SENSIBLE,
        "F4": sinistre["montant_declare"] > justifie * (1 + regles.ECART_DECLARATION_MAX),
    }
    return [nom for nom, leve in regles_f.items() if leve]


# ------------------------------------------------------------------ decision


class AgentDecision:
    """Seul écrivain de l'issue : règle 0, règles §10 dans l'ordre, mode dégradé §9, escalade forcée."""

    nom = "decision"

    def __call__(self, vue: dict[str, Any]) -> dict[str, Any]:
        return {"issue": _issue(vue)}


NIVEAUX_AVIS = {"faible", "modere", "eleve"}


def _issue(vue: dict[str, Any]) -> dict[str, Any]:
    contrat = vue.get("contrat") or {}
    if contrat.get("statut_extraction", "valide") != "valide":  # règle 0 (hors §10, PQ8)
        return _escalade("gestionnaire", "Contrat illisible ou incohérent")
    eligibilite, pieces = vue.get("eligibilite"), vue.get("pieces")
    estimation, avis = vue.get("estimation"), vue.get("avis_fraude")
    arret = vue.get("arret")

    if eligibilite is not None and not eligibilite["eligible"]:  # règle 1
        return _decision(
            "refusee", 0.0, "Demande non éligible : " + ", ".join(eligibilite["conditions_ko"])
        )
    if pieces is not None and pieces["statut"] != "complet":  # règle 2
        motif = "Pièces manquantes : " + ", ".join(pieces["manquantes"])
        if arret:
            motif += f" (borne {arret['borne']} atteinte)"
        return _escalade("gestionnaire", motif)
    # une borne violée (hors relance des pièces, traitée par la règle 2) n'aboutit jamais
    # à une acceptation : escalade forcée
    borne_violee = arret is not None and arret["borne"] != "relances_pieces_max"
    if vue.get("escalade_forcee") or borne_violee or None in (eligibilite, pieces, estimation):
        raison = vue.get("escalade_forcee") or (
            f"borne {arret['borne']} atteinte" if borne_violee and arret else "traitement incomplet"
        )
        return _escalade("gestionnaire", f"Escalade forcée : {raison}")

    assert estimation is not None  # garanti par le test ci-dessus
    montant = estimation["estime"]
    if montant <= 0:  # règle 3
        return _decision("refusee", 0.0, "Dommage inférieur ou égal à la franchise")
    if avis is None:
        return _escalade("gestionnaire", "Escalade forcée : contrôle anti-fraude non effectué")

    niveau = (avis.get("avis") or {}).get("niveau") if avis["statut"] == "avis" else None
    # avis indisponible, ou niveau inexploitable : par prudence, mode dégradé §9
    degrade = avis["statut"] == "indisponible" or (
        avis["statut"] == "avis" and niveau not in NIVEAUX_AVIS
    )
    if niveau == "modere":  # règle 4
        return _escalade("gestionnaire", "Contrôle renforcé : risque de fraude modéré")
    if niveau == "eleve":
        return _escalade("cellule_fraude", "Suspicion de fraude")
    if degrade and montant > regles.SEUIL_MODE_DEGRADE:  # règle 4, mode dégradé §9
        return _escalade(
            "cellule_fraude",
            "Avis anti-fraude indisponible : contrôle anti-fraude manuel (§9)",
            mode_degrade=True,
        )
    if montant > regles.SEUIL_DELEGATION:  # règle 5
        return _escalade("gestionnaire", "Seuil de délégation dépassé")
    motif = f"Remboursement accordé : {montant:.2f} €"  # règle 6
    if degrade:
        motif += " — avis anti-fraude indisponible, décision en mode dégradé (§9)"
    return _decision("acceptee", montant, motif, mode_degrade=degrade)


def _decision(
    decision: str, montant: float, motif: str, *, mode_degrade: bool = False
) -> dict[str, Any]:
    return {
        "issue": "decision",
        "decision": decision,
        "montant_rembourse": montant,
        "motif": motif,
        "file": None,
        "mode_degrade": mode_degrade,
    }


def _escalade(file: str, motif: str, *, mode_degrade: bool = False) -> dict[str, Any]:
    return {
        "issue": "escalade",
        "decision": None,
        "montant_rembourse": None,
        "motif": motif,
        "file": file,
        "mode_degrade": mode_degrade,
    }
