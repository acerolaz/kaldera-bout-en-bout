"""Client du service anti-fraude partenaire (A2A, JSON-RPC 2.0, contrat v2.0).

Seul client A2A, détenu par l'agent ``antifraude`` (dossier 3.1 → 3.4) : Agent Card, projection
stricte sur 7 champs, un appel par dossier (registre), validation de chaque réponse en 4 couches.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import regles

URL_PAR_DEFAUT = "http://localhost:8100"
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
    except ValueError:
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

    model_config = ConfigDict(extra="forbid", strict=True)

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


def evaluer_risque(
    demande: dict[str, Any], url: str | None = None, *, timeout: float | None = None
) -> dict[str, Any] | None:
    """Demande l'avis anti-fraude du partenaire pour une demande.

    Retourne l'évaluation du partenaire, ou ``None`` si elle n'a pas pu être obtenue
    (y compris au-delà de ``timeout`` secondes).
    """
    requete = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "data", "data": demande}],
            }
        },
    }
    entetes = {"Authorization": f"Bearer {os.environ.get('PARTENAIRE_JETON', '')}"}

    def appeler() -> dict[str, Any] | None:
        try:
            reponse = httpx.post(
                f"{url_partenaire(url)}/a2a", json=requete, headers=entetes, timeout=timeout
            )
            reponse.raise_for_status()
            resultat = reponse.json()["result"]
            return resultat["artifacts"][0]["parts"][0]["data"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError):
            return None

    if timeout is None:
        return appeler()
    # httpx borne chaque phase (connexion, lecture…), pas la durée totale : échéance globale.
    # ponytail: le fil abandonné finit seul (timeout httpx par phase) ; client async si le
    # nombre d'appels simultanés devient important
    avis: list[dict[str, Any] | None] = []
    fil = threading.Thread(target=lambda: avis.append(appeler()), daemon=True)
    fil.start()
    fil.join(timeout)
    return avis[0] if avis else None
