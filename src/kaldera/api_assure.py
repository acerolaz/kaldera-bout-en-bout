"""Routes de l'espace assuré (UI1, spec §4) : minces ; session, projection et agent ailleurs.

Toutes exigent une session ``assure`` et l'appartenance de la demande (404 sinon, jamais 403) ;
toute modification exige l'en-tête ``Origin`` du front (403 sinon). Sans ``KALDERA_SESSION_SECRET``
chaque route répond 503. Le flux SSE relit ``evenements_assure`` (contenu déjà projeté).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from time import monotonic
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import auth, evenements, llm, relance
from .agents_llm import AgentLLM
from .assure_postgres import Compte, DepotAssure
from .ingestion import FichierRefuse, controler_fichier, nombre_pages
from .ingestion_postgres import IngestionPostgres
from .postgres import ConfigBase, pool
from .vlm import ConfigIngestion
from .vue_assure import MessageChat, ResumeDemande, VueDemande, construire, resume

router = APIRouter(prefix="/assure", tags=["espace assuré"])
MESSAGES_MAX = 30
FORMAT_REFUSE = "Format non accepté : PDF, PNG ou JPEG uniquement."
DEJA_SOUMIS = "Votre dossier a déjà été soumis : il n'est plus possible d'ajouter une pièce."
DUREE_FLUX_S = 900.0  # au-delà, le navigateur se reconnecte (Last-Event-ID)


def depot_assure() -> DepotAssure:
    url = ConfigBase().database_url
    if not url:
        raise HTTPException(503, "base non configurée (KALDERA_DATABASE_URL)")
    try:
        return DepotAssure(pool(url))
    except psycopg.Error as exc:
        raise HTTPException(503, "base injoignable") from exc


def config_assure() -> auth.ConfigAssure:
    return auth.ConfigAssure()


def config_depot() -> ConfigIngestion:
    return ConfigIngestion()


def agent_de_relance() -> AgentLLM:
    cfg = llm.charger_config()
    return relance.agent_relance(llm.fabrique_llm(cfg, "relance"), cfg.relance)


def pause_flux() -> float:
    return 1.0


def _config_active(
    config: Annotated[auth.ConfigAssure, Depends(config_assure)],
) -> auth.ConfigAssure:
    if config.session_secret is None:
        raise HTTPException(503, "espace assuré non configuré (KALDERA_SESSION_SECRET)")
    return config


Config = Annotated[auth.ConfigAssure, Depends(_config_active)]
Depot = Annotated[DepotAssure, Depends(depot_assure)]


def _origine(request: Request, config: Config) -> None:
    if request.headers.get("origin") != config.front_origin:
        raise HTTPException(403, "origine refusée")


Origine = Depends(_origine)


def utilisateur_courant(request: Request, config: Config, depot: Depot) -> Compte:
    compte_id = auth.lire_session(config, request.cookies.get(auth.COOKIE))
    compte = None if compte_id is None else depot.compte_par_id(compte_id)
    if compte is None or compte.role != "assure":
        raise HTTPException(401, "session requise")
    return compte


Utilisateur = Annotated[Compte, Depends(utilisateur_courant)]


def _sienne(reference: str, compte: Compte, depot: DepotAssure) -> None:
    if not depot.appartient(compte.id, reference):
        raise HTTPException(404, "demande inconnue")


def _vue(depot: DepotAssure, reference: str, config: ConfigIngestion) -> VueDemande:
    donnees = depot.donnees(reference)
    if donnees is None:
        raise HTTPException(404, "demande inconnue")
    return construire(donnees, config.delai_analyse_s)


class _Corps(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Connexion(_Corps):
    identifiant: str = Field(min_length=1, max_length=64)
    mot_de_passe: str = Field(min_length=1, max_length=256)


class Soumission(_Corps):
    confirmer: bool = False


class MessageAssure(_Corps):
    texte: str = Field(max_length=1000)

    @field_validator("texte")
    @classmethod
    def _non_vide(cls, texte: str) -> str:
        if not texte.strip():
            raise ValueError("message vide")
        return texte.strip()


class Recu(_Corps):
    statut: Literal["recu", "deja_recu"]
    avertissement_multipage: bool


# ------------------------------------------------------------------ session


@router.post("/session", status_code=204, dependencies=[Origine])
def ouvrir_session(corps: Connexion, config: Config, depot: Depot, response: Response) -> None:
    compte = auth.authentifier(depot, corps.identifiant, corps.mot_de_passe)
    if compte is None or compte.role != "assure":
        raise HTTPException(401, "identifiant ou mot de passe incorrect, ou compte bloqué")
    response.set_cookie(
        auth.COOKIE,
        auth.jeton_session(config, compte.id),
        max_age=int(config.duree_session_h * 3600),
        httponly=True,
        secure=config.cookie_secure,
        samesite="strict",
        path="/",
    )


@router.delete("/session", status_code=204, dependencies=[Origine])
def fermer_session(response: Response) -> None:
    response.delete_cookie(auth.COOKIE, path="/")


# ------------------------------------------------------------------ demandes


@router.get("/demandes", response_model=list[ResumeDemande])
def mes_demandes(
    compte: Utilisateur, depot: Depot, config: Annotated[ConfigIngestion, Depends(config_depot)]
) -> list[ResumeDemande]:
    return [resume(_vue(depot, ref, config)) for ref in depot.demandes_de(compte.id)]


@router.get("/demandes/{reference}", response_model=VueDemande)
def ma_demande(
    reference: str,
    compte: Utilisateur,
    depot: Depot,
    config: Annotated[ConfigIngestion, Depends(config_depot)],
) -> VueDemande:
    _sienne(reference, compte, depot)
    return _vue(depot, reference, config)


@router.post(
    "/demandes/{reference}/pieces", status_code=202, response_model=Recu, dependencies=[Origine]
)
def deposer_piece(
    reference: str,
    fichier: UploadFile,
    type_piece: Annotated[Literal["facture", "photo", "depot_plainte"], Form(alias="type")],
    compte: Utilisateur,
    depot: Depot,
    config: Annotated[ConfigIngestion, Depends(config_depot)],
    response: Response,
) -> Recu:
    _sienne(reference, compte, depot)
    if _vue(depot, reference, config).soumise or depot.statut(reference) != "admission":
        raise HTTPException(409, DEJA_SOUMIS)
    octets = fichier.file.read(config.taille_max_mo * 1024 * 1024 + 1)
    try:
        mime, sha256 = controler_fichier(octets, config.taille_max_mo, contrat=False)
    except FichierRefuse as exc:
        raison = FORMAT_REFUSE if exc.code == 415 else exc.raison
        raise HTTPException(exc.code, raison) from exc
    _, nouvelle = IngestionPostgres(depot.connexions).deposer_piece(
        reference, octets, mime, sha256, type_piece, None
    )
    if not nouvelle:
        response.status_code = 200
    else:
        evenements.publier_vue(depot, reference, "piece", config.delai_analyse_s)
    multipage = mime == "application/pdf" and nombre_pages(octets) > 1
    return Recu(statut="recu" if nouvelle else "deja_recu", avertissement_multipage=multipage)


@router.post("/demandes/{reference}/soumettre", response_model=VueDemande, dependencies=[Origine])
def soumettre(
    reference: str,
    corps: Soumission,
    compte: Utilisateur,
    depot: Depot,
    config: Annotated[ConfigIngestion, Depends(config_depot)],
) -> VueDemande:
    _sienne(reference, compte, depot)
    vue = _vue(depot, reference, config)
    if vue.soumise or depot.statut(reference) != "admission":
        raise HTTPException(409, "deja_soumise")
    if any(p.statut == "en_analyse" for p in vue.pieces):
        raise HTTPException(409, "analyse_en_cours")
    if not corps.confirmer and any(p.statut != "validee" for p in vue.pieces):
        raise HTTPException(409, "confirmation_requise")
    if not IngestionPostgres(depot.connexions).soumettre(reference):
        raise HTTPException(409, "deja_soumise")
    evenements.publier_vue(depot, reference, "etape", config.delai_analyse_s)
    return _vue(depot, reference, config)


@router.post(
    "/demandes/{reference}/messages",
    status_code=202,
    response_model=MessageChat,
    dependencies=[Origine],
)
def envoyer_message(
    reference: str,
    corps: MessageAssure,
    compte: Utilisateur,
    depot: Depot,
    config: Annotated[ConfigIngestion, Depends(config_depot)],
    agent: Annotated[AgentLLM, Depends(agent_de_relance)],
) -> MessageChat:
    _sienne(reference, compte, depot)
    if depot.statut(reference) in ("terminee", "secours"):
        raise HTTPException(409, "dossier_clos")  # le chat s'arrête au verdict
    if depot.messages_assure(reference) >= MESSAGES_MAX:
        raise HTTPException(429, "trop de messages pour ce dossier")
    donnees = depot.donnees(reference)
    if donnees is None:
        raise HTTPException(404, "demande inconnue")
    vue = construire(donnees, config.delai_analyse_s)
    evenements.publier_message(depot, reference, "assure", corps.texte)
    assure = (donnees["etat"] or {}).get("demande", {}).get("assure", {})
    texte = relance.repondre(corps.texte, vue.pieces, assure, agent)
    a_refaire = any(p.statut in ("a_fournir", "a_refaire") for p in vue.pieces)
    actions: list[Literal["deposer"]] = ["deposer"] if a_refaire and not vue.soumise else []
    evenements.publier_message(depot, reference, "agent", texte, actions)
    return MessageChat(auteur="agent", texte=texte, actions=actions)


# ------------------------------------------------------------------ flux SSE


async def _flux(
    request: Request, depot: DepotAssure, reference: str, apres: int, pause_s: float
) -> AsyncIterator[str]:
    fin = monotonic() + DUREE_FLUX_S
    while not await request.is_disconnected():
        lignes = await run_in_threadpool(depot.evenements_depuis, reference, apres)
        for ligne in lignes:
            apres = ligne["id"]
            donnees = json.dumps(ligne["contenu"], ensure_ascii=False)
            yield f"id: {ligne['id']}\nevent: {ligne['type']}\ndata: {donnees}\n\n"
            if ligne["type"] == "verdict":
                return
        if not lignes:
            statut = await run_in_threadpool(depot.statut, reference)
            if statut in ("terminee", "secours") or monotonic() > fin:
                return
        await asyncio.sleep(pause_s)


@router.get("/demandes/{reference}/flux")
def flux(
    request: Request,
    reference: str,
    compte: Utilisateur,
    depot: Depot,
    pause_s: Annotated[float, Depends(pause_flux)],
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    _sienne(reference, compte, depot)
    valide = last_event_id is not None and last_event_id.isascii() and last_event_id.isdigit()
    apres = (
        int(last_event_id[:18]) if valide and last_event_id else 0
    )  # bigint : pas de débordement
    return StreamingResponse(
        _flux(request, depot, reference, apres, pause_s),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
