"""Vue gestionnaire (C3-2) : projection pure de l'état en base vers l'IHM du back-office.

L'IHM n'interprète rien (EX-D44) : statut d'affichage des étapes, avancement et résumés sont
calculés ici, sans entrée / sortie. Liste blanche : seuls les champs déclarés dans les schémas
ci-dessous sortent de l'API (jamais email, téléphone, IBAN, adresse ni identifiant client).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, ValidationError

from .etat import BORNES, EtatDemande
from .machine import Etat
from .regles import FORMULES

ETAPES = tuple(
    e.value
    for e in (Etat.ELIGIBILITE, Etat.PIECES, Etat.ESTIMATION, Etat.ANTIFRAUDE, Etat.DECISION)
)
TERMINAUX = frozenset({"terminee", "secours"})  # statuts de demande : dossier clos
FAITES = frozenset({"termine", "sautee", "repli", "degrade"})  # étapes comptées dans l'avancement

log = logging.getLogger(__name__)

CodeIssue = Literal["acceptee", "refusee", "escalade"]
StatutDemande = Literal["admission", "en_cours", "terminee", "secours"]
StatutEtape = Literal["en_attente", "termine", "sautee", "echec", "repli", "degrade"]
StatutAvis = Literal["ok", "indisponible", "non_requis"]
STATUT_AVIS: dict[str, StatutAvis] = {
    "avis": "ok",
    "indisponible": "indisponible",
    "non_requis": "non_requis",
}


class LigneDemande(BaseModel):
    reference: str
    nom: str | None
    prenom: str | None
    police: str | None
    type_sinistre: str | None
    montant_declare: float | None
    statut: str
    issue: CodeIssue | None
    file: str | None
    mode_degrade: bool


class Garanties(BaseModel):
    formule: str | None
    franchise: float | None
    plafond: float | None
    date_souscription: str | None
    statut_contrat: str | None
    cotisations_a_jour: bool | None
    statut_extraction: str
    source: str
    modele: str | None
    sha256: str | None


class Etape(BaseModel):
    etat: str
    statut: StatutEtape
    avancement: int
    passages: int
    duree_ms: float | None = None
    latence_llm_ms: float | None = None
    modele: str | None = None
    mode: Literal["llm", "repli"] | None = None
    cause: str | None = None
    tours_llm: int | None = None
    jetons: int | None = None
    sortie_rejetee: bool = False
    de: str | None = None
    vers: str | None = None
    garde: str | None = None
    resume: str = ""


class CarteAntifraude(BaseModel):
    requis: bool
    indicateurs: list[str]
    statut: StatutAvis
    niveau: str | None
    score: float | None
    evaluation_id: str | None
    version_modele: str | None
    note: str | None
    cause: str | None


class ArretVue(BaseModel):
    borne: str
    valeur: float
    etat: str | None


class DossierVue(BaseModel):
    reference: str
    statut: str
    fiche: dict[str, Any] | None
    nom: str | None
    prenom: str | None
    police: str | None
    formule: str | None
    avancement: int
    duree_ms: float
    budget_ms: float
    issue: CodeIssue | None
    file: str | None
    motif: str | None
    mode_degrade: bool
    montant_rembourse: float | None
    garanties: Garanties
    etapes: list[Etape]
    antifraude: CarteAntifraude | None
    arret: ArretVue | None


# ------------------------------------------------------------------ outils


def euros(montant: float) -> str:
    """1 230 € / 12,50 € : milliers en espace fine insécable, décimales si non nulles."""
    entier, _, decimales = f"{montant:,.2f}".partition(".")
    texte = entier.replace(",", "\u202f")
    return f"{texte} €" if decimales == "00" else f"{texte},{decimales} €"


def _sous(source: dict[str, Any], cle: str) -> dict[str, Any]:
    valeur = source.get(cle)
    return valeur if isinstance(valeur, dict) else {}


class _Sortie(NamedTuple):
    code: CodeIssue | None
    file: str | None
    motif: str | None
    mode_degrade: bool
    montant_rembourse: float | None


def _sortie(fiche: dict[str, Any] | None, etat: EtatDemande) -> _Sortie:
    """Issue du dossier : ``etat.issue`` fait foi ; sinon la fiche de secours (filet, reaper)."""
    if etat.issue is not None:
        i = etat.issue
        code = "escalade" if i.issue == "escalade" else i.decision
        return _Sortie(code, i.file, i.motif, i.mode_degrade, i.montant_rembourse)
    if fiche and fiche.get("issue"):
        code = "escalade" if fiche["issue"] == "escalade" else fiche.get("decision")
        return _Sortie(
            code,
            fiche.get("file"),
            fiche.get("motif"),
            bool(fiche.get("mode_degrade")),
            fiche.get("montant_rembourse"),
        )
    return _Sortie(None, None, None, False, None)


# ------------------------------------------------------------------ E1


def ligne(
    reference: str, statut: str, fiche: dict[str, Any] | None, etat: EtatDemande
) -> LigneDemande:
    assure = _sous(etat.demande, "assure")
    contrat = _sous(etat.demande, "contrat")
    sinistre = _sous(etat.demande, "sinistre")
    sortie = _sortie(fiche, etat)
    return LigneDemande(
        reference=reference,
        nom=assure.get("nom"),
        prenom=assure.get("prenom"),
        police=contrat.get("numero"),
        type_sinistre=sinistre.get("type"),
        montant_declare=sinistre.get("montant_declare"),
        statut=statut,
        issue=sortie.code,
        file=sortie.file,
        mode_degrade=sortie.mode_degrade,
    )


def lignes(
    demandes: Iterable[tuple[str, str, dict[str, Any] | None, EtatDemande]],
) -> list[LigneDemande]:
    """Projette la liste ; une ligne illisible devient une ligne minimale (spec §5), sans PII."""
    resultat: list[LigneDemande] = []
    for reference, statut, fiche, etat in demandes:
        try:
            resultat.append(ligne(reference, statut, fiche, etat))
        except ValidationError:
            log.warning("état illisible, ligne minimale pour %s", reference)
            resultat.append(
                LigneDemande(
                    reference=reference,
                    nom=None,
                    prenom=None,
                    police=None,
                    type_sinistre=None,
                    montant_declare=None,
                    statut=statut,
                    issue=None,
                    file=None,
                    mode_degrade=False,
                )
            )
    return resultat


def filtrer(
    lignes: list[LigneDemande],
    *,
    statut: str | None = None,
    issue: str | None = None,
    file: str | None = None,
    mode_degrade: bool | None = None,
    q: str | None = None,
) -> list[LigneDemande]:
    """Filtres combinés en ET ; un filtre vide est ignoré ; ``q`` sans casse (référence, nom, police)."""
    texte = (q or "").strip().casefold()
    return [
        lg
        for lg in lignes
        if (not statut or lg.statut == statut)
        and (not issue or lg.issue == issue)
        and (not file or lg.file == file)
        and (mode_degrade is None or lg.mode_degrade == mode_degrade)
        and (
            not texte
            or any(texte in (v or "").casefold() for v in (lg.reference, lg.nom, lg.police))
        )
    ]


# ------------------------------------------------------------------ E2


def _entrees(etat: EtatDemande) -> dict[str, list[dict[str, Any]]]:
    """Entrées de trace par étape ; le filet (niveau 1) est rattaché à son état ``de``."""
    par_etape: dict[str, list[dict[str, Any]]] = {}
    for entree in etat.trace:
        cle = entree.get("de") if entree.get("action") == "filet_securite" else entree.get("action")
        par_etape.setdefault(str(cle), []).append(entree)
    return par_etape


def _statut(nom: str, entree: dict[str, Any], etat: EtatDemande) -> StatutEtape:
    """Spec C3-2 §2.4 : la première règle vraie gagne."""
    if entree.get("action") == "filet_securite":
        return "echec"
    if entree.get("statut") == "echec":
        avis = etat.avis_fraude
        indisponible = avis is not None and avis.statut == "indisponible"
        return "degrade" if nom == Etat.ANTIFRAUDE.value and indisponible else "echec"
    if not entree.get("ecrit") and "mode" not in entree:  # garde d'entrée : action non exécutée
        return "sautee"
    if entree.get("mode") == "repli":
        return "repli"
    return "termine"


def _resume(nom: str, statut: StatutEtape, entree: dict[str, Any], etat: EtatDemande) -> str:
    """Spec C3-2 §2.5 : gabarits déterministes, langage gestionnaire."""
    if entree.get("action") == "filet_securite":
        return f"Filet de sécurité : {entree.get('erreur', 'erreur')}"
    if statut == "sautee":
        return f"Sautée (garde {entree.get('garde')})"
    if nom == Etat.ELIGIBILITE.value and etat.eligibilite is not None:
        e = etat.eligibilite
        return "Éligible" if e.eligible else "Non éligible : " + ", ".join(e.conditions_ko)
    if nom == Etat.PIECES.value and etat.pieces is not None:
        p = etat.pieces
        if p.statut == "complet":
            return f"Pièces complètes ({len(p.retenues)} retenues)"
        prefixe = "Incomplet : manque" if p.statut == "incomplet" else "Pièces manquantes :"
        return f"{prefixe} {', '.join(p.manquantes)}"
    if nom == Etat.ESTIMATION.value and etat.estimation is not None:
        s = etat.estimation
        declare = _sous(etat.demande, "sinistre").get("montant_declare")
        base = (
            f"min(déclaré {euros(declare)}, justifié {euros(s.justifie)})"
            if isinstance(declare, (int, float))
            else f"justifié {euros(s.justifie)}"
        )
        atteint = "atteint" if s.estime >= s.plafond else "non atteint"
        return (
            f"Estimé {euros(s.estime)} = {base} − franchise {euros(s.franchise)}, "
            f"plafond {euros(s.plafond)} {atteint}"
        )
    if nom == Etat.ANTIFRAUDE.value and etat.avis_fraude is not None:
        a = etat.avis_fraude
        if not a.requis:
            return "Avis non requis"
        if a.statut == "indisponible":
            return f"Avis indisponible : {a.cause or 'cause inconnue'}"
        avis = a.avis or {}
        return f"Avis obtenu : niveau {avis.get('niveau', '?')}, score {avis.get('score', '?')}"
    if nom == Etat.DECISION.value and etat.issue is not None:
        i = etat.issue
        if i.issue == "escalade":
            return f"Escaladée vers {i.file or 'gestionnaire'} : {i.motif}"
        if i.decision == "acceptee":
            return f"Acceptée : {euros(i.montant_rembourse or 0)}"
        return f"Refusée : {i.motif}"
    return ""


def _etapes(etat: EtatDemande) -> list[Etape]:
    par_etape = _entrees(etat)
    tracees = [rang for rang, nom in enumerate(ETAPES) if nom in par_etape]
    derniere = tracees[-1] if tracees else -1
    cartes: list[Etape] = []
    for rang, nom in enumerate(ETAPES):
        passages = par_etape.get(nom, [])
        if not passages:
            # absente mais une étape aval a eu lieu : la machine l'a court-circuitée sans la tracer
            if rang < derniere:
                cartes.append(
                    Etape(
                        etat=nom,
                        statut="sautee",
                        avancement=100,
                        passages=0,
                        resume="Sautée (court-circuit)",
                    )
                )
            else:
                cartes.append(Etape(etat=nom, statut="en_attente", avancement=0, passages=0))
            continue
        e = passages[-1]  # relance de pièces : la carte reflète le dernier passage
        statut = _statut(nom, e, etat)
        cartes.append(
            Etape(
                etat=nom,
                statut=statut,
                avancement=100,
                passages=len(passages),
                duree_ms=e.get("duree_ms"),
                latence_llm_ms=e.get("latence_llm_ms"),
                modele=e.get("modele"),
                mode=e.get("mode"),
                cause=e.get("cause"),
                tours_llm=e.get("tours_llm"),
                jetons=e.get("jetons"),
                sortie_rejetee=bool(e.get("sortie_rejetee")),
                de=e.get("de"),
                vers=e.get("vers"),
                garde=e.get("garde"),
                resume=_resume(nom, statut, e, etat),
            )
        )
    return cartes


def _garanties(etat: EtatDemande) -> Garanties:
    contrat = _sous(etat.demande, "contrat")
    formule = contrat.get("formule")
    bareme = FORMULES.get(formule, {}) if isinstance(formule, str) else {}
    provenance = etat.contrat
    return Garanties(
        formule=formule,
        franchise=bareme.get("franchise"),
        plafond=bareme.get("plafond"),
        date_souscription=contrat.get("date_souscription"),
        statut_contrat=contrat.get("statut"),
        cotisations_a_jour=contrat.get("cotisations_a_jour"),
        statut_extraction=provenance.statut_extraction,
        source=provenance.source,
        modele=provenance.modele,
        sha256=provenance.sha256,
    )


def _antifraude(etat: EtatDemande) -> CarteAntifraude | None:
    a = etat.avis_fraude
    if a is None:
        return None
    avis = a.avis or {}
    return CarteAntifraude(
        requis=a.requis,
        indicateurs=list(a.indicateurs),
        statut=STATUT_AVIS[a.statut],
        niveau=avis.get("niveau"),
        score=avis.get("score"),
        evaluation_id=avis.get("evaluation_id"),
        version_modele=avis.get("version_modele"),
        note=a.note,
        cause=a.cause,
    )


def dossier(
    reference: str, statut: str, fiche: dict[str, Any] | None, etat: EtatDemande
) -> DossierVue:
    base = ligne(reference, statut, fiche, etat)
    sortie = _sortie(fiche, etat)
    etapes = _etapes(etat)
    arret = etat.arret
    faites = sum(e.statut in FAITES for e in etapes)
    return DossierVue(
        reference=reference,
        statut=statut,
        fiche=fiche,
        nom=base.nom,
        prenom=base.prenom,
        police=base.police,
        formule=_sous(etat.demande, "contrat").get("formule"),
        avancement=100 if statut in TERMINAUX else round(100 * faites / len(ETAPES)),
        duree_ms=round(sum(float(e.get("duree_ms") or 0) for e in etat.trace), 2),
        budget_ms=BORNES.duree_max_s * 1000,
        issue=base.issue,
        file=base.file,
        motif=sortie.motif,
        mode_degrade=base.mode_degrade,
        montant_rembourse=sortie.montant_rembourse,
        garanties=_garanties(etat),
        etapes=etapes,
        antifraude=_antifraude(etat),
        arret=ArretVue(borne=arret.borne, valeur=arret.valeur, etat=arret.etat) if arret else None,
    )
