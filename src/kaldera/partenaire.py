"""Client du service anti-fraude partenaire (A2A, JSON-RPC 2.0, contrat v2.0).

Seul client A2A, détenu par l'agent ``antifraude`` (dossier 3.1 → 3.4) : Agent Card, projection
stricte sur 7 champs, un appel par dossier (registre), validation de chaque réponse en 4 couches.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import regles
from .ports import ErreurPersistance, RegistreA2A

LOGGER = logging.getLogger(__name__)

URL_PAR_DEFAUT = "http://localhost:8100"
DELAI_CARTE_S = 1.0
_CARTES: dict[str, str] = {}  # URL de base → URL d'appel de l'Agent Card (succès seulement)
CODES_RPC = {
    -32700: "corps illisible",
    -32600: "enveloppe invalide",
    -32601: "méthode inconnue",
    -32602: "projection refusée",
    -32029: "doublon refusé : manquement au contrat",
}
Indicateur = Literal["MONTANT_ELEVE", "SINISTRE_PRECOCE", "FREQUENCE_ELEVEE", "TYPE_SENSIBLE"]


@dataclass(frozen=True)
class Indisponible:
    """Avis non obtenu. ``cause`` ne reprend jamais le contenu de la réponse (EX-D22)."""

    cause: str


class ReponseAntifraude(BaseModel):
    """Évaluation du contrat §3 : 6 champs exacts (couche ③)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    reference_dossier: str
    score: float
    niveau: Literal["faible", "modere", "eleve"]
    indicateurs: list[Indicateur]
    evaluation_id: str
    version_modele: str


def niveau_attendu(score: float) -> str:
    return "faible" if score < 0.40 else "modere" if score < 0.75 else "eleve"


def valider_reponse(
    statut_http: int, corps_brut: str, id_rpc: str, reference: str
) -> dict[str, Any] | Indisponible:
    """Couches ① transport, ② enveloppe JSON-RPC, ③ schéma, ④ cohérence (dossier 3.4)."""
    if statut_http in (401, 503):
        return Indisponible(f"HTTP {statut_http}{' (jeton)' if statut_http == 401 else ''}")
    try:
        corps = json.loads(corps_brut)
    except (ValueError, RecursionError):  # RecursionError : corps hostile très imbriqué
        return Indisponible(f"couche ① : corps illisible (HTTP {statut_http})")
    if not isinstance(corps, dict) or corps.get("jsonrpc") != "2.0":
        return Indisponible("couche ② : enveloppe JSON-RPC invalide")
    erreur = corps.get("error")
    if erreur is not None:  # piège : une erreur JSON-RPC arrive souvent sous HTTP 200
        code = erreur.get("code") if isinstance(erreur, dict) else None
        if type(code) is not int:  # jamais une valeur libre du partenaire dans la cause
            code = None
        libelle = CODES_RPC.get(code, "erreur inconnue") if code is not None else "erreur inconnue"
        return Indisponible(f"JSON-RPC {'?' if code is None else code} : {libelle}")
    if statut_http != 200:
        return Indisponible(f"couche ① : HTTP {statut_http}")
    if corps.get("id") != id_rpc:
        return Indisponible("couche ② : id JSON-RPC différent de la requête")
    resultat: Any = corps.get("result")
    try:
        (artefact,) = resultat["artifacts"]
        (partie,) = artefact["parts"]
        termine = (
            resultat["kind"] == "task"
            and resultat["status"]["state"] == "completed"
            and partie["kind"] == "data"
        )
        donnees = partie["data"]
    except (TypeError, KeyError, ValueError):
        termine = False
    if not termine:
        return Indisponible("couche ② : tâche non terminée ou artefact invalide")
    try:
        avis = ReponseAntifraude.model_validate(donnees)
    except ValidationError as exc:
        return Indisponible(f"couche ③ : {_cause_schema(exc)}")
    if not 0 <= avis.score <= 1:
        return Indisponible("couche ④ : score hors bornes")
    if avis.niveau != niveau_attendu(avis.score):
        return Indisponible("couche ④ : niveau incohérent avec le score")
    if avis.reference_dossier != reference:
        return Indisponible("couche ④ : référence différente de la requête")
    return avis.model_dump()


def _cause_schema(exc: ValidationError) -> str:
    """Champs du contrat et types d'erreur seulement : ni ``input``, ni ``msg``, ni clé inconnue."""
    causes = sorted(
        {
            "champ hors contrat"
            if e["type"] == "extra_forbidden"
            else f"{e['loc'][0] if e['loc'] else 'data'} {e['type']}"
            for e in exc.errors()
        }
    )
    return ", ".join(causes)


class RequeteAntifraude(BaseModel):
    """Les 7 champs du contrat §2, aucun autre (EX-D20)."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    reference_dossier: str = Field(pattern=r"^KAL-\d{2}-\d{4}$")
    type_sinistre: Literal["degat_des_eaux", "incendie", "bris_de_glace", "vol"]
    montant_declare: float = Field(gt=0)
    date_survenance: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    anciennete_contrat_jours: int = Field(ge=0)
    sinistres_12_mois: int = Field(ge=0)
    departement: str = Field(pattern=r"^(\d{2}|2A|2B|97\d)$")


def departement(code_postal: str) -> str:
    """2 premiers chiffres ; Corse 2A / 2B ; outre-mer (97x) sur 3 chiffres (contrat §2)."""
    if not re.fullmatch(r"\d{5}", code_postal):
        raise ValueError("code postal mal formé")
    if code_postal.startswith("20"):
        return "2A" if int(code_postal) < 20200 else "2B"
    return code_postal[:3] if code_postal.startswith("97") else code_postal[:2]


def projeter(demande: dict[str, Any]) -> RequeteAntifraude:
    """Liste blanche : seule porte de sortie des données vers le partenaire (C2-Q3)."""
    sinistre, contrat = demande["sinistre"], demande["contrat"]
    return RequeteAntifraude(
        reference_dossier=demande["reference"],
        type_sinistre=sinistre["type"],
        montant_declare=sinistre["montant_declare"],
        date_survenance=sinistre["date_survenance"],
        anciennete_contrat_jours=regles.jours_entre(
            contrat["date_souscription"], sinistre["date_survenance"]
        ),
        sinistres_12_mois=(demande.get("historique") or {}).get("sinistres_12_mois", 0),
        departement=departement(demande["assure"]["code_postal"]),
    )


def cause_projection(exc: Exception) -> str:
    """Noms de champs seulement, jamais les valeurs de la demande."""
    if isinstance(exc, KeyError):
        return f"projection : donnée absente ({exc.args[0]})"
    if isinstance(exc, ValidationError):
        champs = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
        return f"projection : {', '.join(champs) or 'donnée'} invalide"
    return "projection : donnée invalide"


def url_partenaire(url: str | None = None) -> str:
    return (url or os.environ.get("PARTENAIRE_URL") or URL_PAR_DEFAUT).rstrip("/")


def url_appel(base: str) -> str:
    """URL d'appel lue dans l'Agent Card, une fois par processus ; ``/a2a`` en secours."""
    if base in _CARTES:
        return _CARTES[base]
    try:
        reponse = httpx.get(f"{base}/.well-known/agent.json", timeout=DELAI_CARTE_S)
        url = reponse.json().get("url") if reponse.status_code == 200 else None
    # réseau, URL malformée (hors HTTPError), JSON, carte non objet
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, AttributeError):
        url = None
    # même origine que la base : le jeton ne part jamais vers un hôte annoncé par la carte
    if isinstance(url, str) and _origine(url) == _origine(base):
        _CARTES[base] = url
        return url
    return f"{base}/a2a"


def _origine(url: str) -> tuple[str, str]:
    parties = urlsplit(url)
    return parties.scheme, parties.netloc


def evaluer_risque(
    demande: dict[str, Any],
    url: str,
    *,
    registre: RegistreA2A,
    timeout: float | None = None,
) -> dict[str, Any] | Indisponible:
    """Avis anti-fraude validé, ou ``Indisponible`` ; aucune relance, quel que soit le cas (§6).

    ``url`` est l'URL d'appel (``url_appel``). Projection, jeton, URL, puis réservation, puis
    envoi : si l'une échoue, rien ne part et l'appel unique du dossier n'est pas gaspillé.
    """
    try:
        requete = projeter(demande)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:  # historique non objet
        return Indisponible(cause_projection(exc))
    jeton = os.environ.get("PARTENAIRE_JETON")
    if not jeton:  # 401 assuré : ne pas consommer l'appel unique du dossier
        return Indisponible("jeton absent")
    if not jeton.isascii():  # en-tête HTTP impossible : ne pas consommer l'appel unique
        return Indisponible("jeton invalide")
    try:
        cible: httpx.URL | None = httpx.URL(url)
    except httpx.InvalidURL:
        cible = None
    if cible is None or cible.scheme not in ("http", "https") or not cible.host:
        return Indisponible("URL partenaire invalide")
    reference = requete.reference_dossier
    try:
        if not registre.reserver(reference):
            return Indisponible("registre : dossier déjà soumis")
    except ErreurPersistance:
        return Indisponible("registre indisponible")

    id_rpc = str(uuid.uuid4())
    enveloppe = {
        "jsonrpc": "2.0",
        "id": id_rpc,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "data", "data": requete.model_dump()}],
            }
        },
    }
    entetes = {"Authorization": f"Bearer {jeton}"}

    def appeler() -> dict[str, Any] | Indisponible:
        try:
            reponse = httpx.post(url, json=enveloppe, headers=entetes, timeout=timeout)
        # InvalidURL hors HTTPError ; ValueError : jeton non ASCII (UnicodeEncodeError)…
        except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
            return Indisponible(f"couche ① : {type(exc).__name__}")
        return valider_reponse(reponse.status_code, reponse.text, id_rpc, reference)

    if timeout is None:
        avis = appeler()
    else:
        # httpx borne chaque phase (connexion, lecture…), pas la durée totale : échéance globale.
        # ponytail: le fil abandonné finit seul (timeout httpx par phase) et ne meurt plus d'une
        # erreur locale (attrapée dans appeler) ; client async si les appels simultanés abondent
        recus: list[dict[str, Any] | Indisponible] = []
        fil = threading.Thread(target=lambda: recus.append(appeler()), daemon=True)
        fil.start()
        fil.join(timeout)
        avis = recus[0] if recus else Indisponible(f"délai > {timeout:g} s")
    if isinstance(avis, dict):
        try:
            registre.noter(reference, avis["evaluation_id"])
        except ErreurPersistance as exc:  # avis gardé : la réservation empêche déjà un second appel
            LOGGER.warning("evaluation_id non noté pour %s : %s", reference, exc)
    return avis
