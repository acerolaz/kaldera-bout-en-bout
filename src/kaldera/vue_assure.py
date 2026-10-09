"""Projection vers l'assuré (UI1, spec §3 et §6) : seul passage des données internes vers lui.

Fonctions pures, liste blanche : les DTO sont ``extra="forbid"`` et ne lisent que les champs
nommés ici. Jamais exposés : avis anti-fraude, score, indicateurs, file ``cellule_fraude``, mode
dégradé, replis, trace, noms d'agents, état interne. Le motif de la fiche n'est jamais recopié.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from . import regles

StatutPiece = Literal["a_fournir", "en_analyse", "validee", "a_refaire"]
Branche = Literal["attente_pieces", "gestionnaire"]
TypePiece = Literal["facture", "photo", "depot_plainte"]

LIBELLES_PIECES: dict[str, str] = {
    "facture": "Facture",
    "photo": "Photos des dommages",
    "depot_plainte": "Récépissé de dépôt de plainte",
}
RAISON_A_REFAIRE = "Le document n'a pas pu être lu ou ne correspond pas au type indiqué."
TEXTE_TRANSMISE = "Votre dossier a été transmis à un gestionnaire, qui reprendra contact avec vous."
DELAI_TRAITEMENT_S = 10.0  # engagement de service après l'admission (specs_metier §12)
# phase interne → étape visible (spec §3) ; un état inconnu en cours de traitement ⇒ étape 5
ETAPES_EN_COURS = {"eligibilite": 2, "pieces": 2, "estimation": 3, "antifraude": 4, "decision": 5}
CONDITIONS_EN_CLAIR = {
    "contrat non actif": "votre contrat n'était pas actif",
    "cotisations impayées": "des cotisations restent impayées",
    "sinistre survenu pendant la période de carence": (
        "le sinistre est survenu pendant la période de carence"
    ),
    "déclaration hors délai": "le sinistre a été déclaré hors délai",
    "sinistre non couvert par la formule": "ce type de sinistre n'est pas couvert par votre formule",
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PieceAttendue(_Strict):
    type: TypePiece
    libelle: str
    statut: StatutPiece
    raison: str | None = None


class Verdict(_Strict):
    issue: Literal["acceptee", "partielle", "refusee", "transmise"]
    montant: float | None = None
    franchise: float | None = None
    explication: str
    pieces_retenues: list[str] = []


class VueDemande(_Strict):
    reference: str
    cree_le: datetime
    etape: int = Field(ge=1, le=5)
    branche: Branche | None = None
    horodatages: dict[int, datetime] = {}
    restant_estime_s: float = Field(ge=0)
    pieces: list[PieceAttendue]
    soumise: bool
    verdict: Verdict | None = None


class ResumeDemande(_Strict):
    reference: str
    cree_le: datetime
    etape: int
    branche: Branche | None = None


class MessageChat(_Strict):
    auteur: Literal["assure", "agent"]
    texte: str
    actions: list[Literal["deposer"]] = []


def _euros(montant: float) -> str:
    return f"{montant:,.2f}".replace(",", " ").replace(".", ",") + " €"


def pieces_attendues(type_sinistre: str, pieces: list[dict[str, Any]]) -> list[PieceAttendue]:
    """Une ligne par pièce exigée ; la dernière déposée de chaque type fait foi (comme le moteur)."""
    attendues = []
    for type_piece in regles.PIECES_EXIGEES[type_sinistre]:
        du_type = [p for p in pieces if p["type"] == type_piece]
        statut: StatutPiece
        raison = None
        if not du_type:
            statut = "a_fournir"
        elif du_type[-1]["statut_analyse"] == "en_attente":
            statut = "en_analyse"
        elif du_type[-1]["statut_analyse"] == "ok" and du_type[-1]["lisible"]:
            statut = "validee"
        else:
            statut, raison = "a_refaire", RAISON_A_REFAIRE
        attendues.append(
            PieceAttendue(
                type=type_piece,  # type: ignore[arg-type]  # clés de PIECES_EXIGEES
                libelle=LIBELLES_PIECES[type_piece],
                statut=statut,
                raison=raison,
            )
        )
    return attendues


def etape_et_branche(
    statut: str,
    etat_courant: str,
    soumise: bool,
    fiche: dict[str, Any] | None,
    pieces: list[PieceAttendue],
) -> tuple[int, Branche | None]:
    if statut == "admission":
        attente = (
            not soumise
            and any(p.statut in ("a_fournir", "a_refaire") for p in pieces)
            and not any(p.statut == "en_analyse" for p in pieces)
        )
        return 1, ("attente_pieces" if attente else None)
    if statut == "en_cours":
        return ETAPES_EN_COURS.get(etat_courant, 5), None
    if statut == "terminee" and fiche is not None and fiche.get("issue") == "decision":
        return 5, None
    return 5, "gestionnaire"  # escalade (toute file), ou secours du reaper


def verdict(statut: str, fiche: dict[str, Any] | None, etat: dict[str, Any]) -> Verdict | None:
    if statut not in ("terminee", "secours"):
        return None
    if statut == "secours" or fiche is None or fiche.get("issue") != "decision":
        return Verdict(issue="transmise", explication=TEXTE_TRANSMISE)
    estimation = etat.get("estimation") or {}
    franchise = estimation.get("franchise")
    retenues = [
        LIBELLES_PIECES[p["type"]]
        for p in (etat.get("pieces") or {}).get("retenues", [])
        if p.get("type") in LIBELLES_PIECES
    ]
    if fiche.get("decision") == "refusee":
        conditions = (etat.get("eligibilite") or {}).get("conditions_ko", [])
        textes = [CONDITIONS_EN_CLAIR[c] for c in conditions if c in CONDITIONS_EN_CLAIR]
        if textes:
            explication = (
                "Votre demande ne peut pas être prise en charge : " + " ; ".join(textes) + "."
            )
        elif estimation and estimation.get("estime") == 0 and franchise is not None:
            explication = (
                "Le montant du dommage retenu ne dépasse pas la franchise de votre contrat "
                f"({_euros(franchise)})."
            )
        else:
            explication = "Votre demande ne peut pas être prise en charge."
        return Verdict(
            issue="refusee",
            montant=0.0,
            franchise=franchise,
            explication=explication,
            pieces_retenues=retenues,
        )
    montant = float(fiche["montant_rembourse"])
    declare = float(etat["demande"]["sinistre"]["montant_declare"])
    retenu = float(estimation.get("retenu", montant))
    plafond = estimation.get("plafond")
    plafonne = plafond is not None and estimation.get("estime", 0) >= plafond
    explication = f"Montant retenu {_euros(retenu)}"
    if franchise is not None:
        explication += f", moins la franchise de {_euros(franchise)}"
    if plafonne and plafond is not None:
        explication += f", dans la limite du plafond de {_euros(plafond)}"
    explication += f" : {_euros(montant)} vous seront remboursés."
    if retenu < declare:
        explication += (
            f" Le montant retenu correspond aux justificatifs fournis ({_euros(retenu)} sur "
            f"{_euros(declare)} déclarés)."
        )
    return Verdict(
        issue="partielle" if retenu < declare or plafonne else "acceptee",
        montant=montant,
        franchise=franchise,
        explication=explication,
        pieces_retenues=retenues,
    )


def construire(donnees: dict[str, Any], delai_analyse_s: float) -> VueDemande:
    etat = donnees["etat"] or {}
    pieces = pieces_attendues(etat["demande"]["sinistre"]["type"], donnees["pieces"])
    soumise = donnees["soumise_le"] is not None
    statut = donnees["statut"]
    etape, branche = etape_et_branche(
        statut, donnees["etat_courant"], soumise, donnees["fiche"], pieces
    )
    if statut == "admission":
        restant = delai_analyse_s * sum(p.statut == "en_analyse" for p in pieces)
    else:
        restant = DELAI_TRAITEMENT_S if statut == "en_cours" else 0.0
    return VueDemande(
        reference=donnees["reference"],
        cree_le=donnees["cree_le"],
        etape=etape,
        branche=branche,
        horodatages={**donnees["horodatages"], 1: donnees["cree_le"]},  # décision 7
        restant_estime_s=restant,
        pieces=pieces,
        soumise=soumise,
        verdict=verdict(statut, donnees["fiche"], etat),
    )


def resume(vue: VueDemande) -> ResumeDemande:
    return ResumeDemande(
        reference=vue.reference, cree_le=vue.cree_le, etape=vue.etape, branche=vue.branche
    )
