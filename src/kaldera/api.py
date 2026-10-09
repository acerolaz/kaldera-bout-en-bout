"""API de dépôt (dossier 2.4 ter) : routes minces, contrôles dans ``ingestion``, SQL dans le dépôt.

Routes ``def`` synchrones : FastAPI les exécute dans son pool de threads (psycopg synchrone).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .api_assure import router as routeur_assure
from .auth import ConfigAssure
from .ingestion import FichierRefuse, controler_fichier
from .ingestion_postgres import IngestionPostgres
from .ports import ErreurPersistance
from .postgres import ConfigBase, pool
from .vlm import ConfigIngestion

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def _cycle(application: FastAPI) -> AsyncIterator[None]:
    if ConfigAssure().session_secret is None:
        LOGGER.warning("KALDERA_SESSION_SECRET absente : l'espace assuré (/assure) répond 503")
    yield


app = FastAPI(title="Kaldera — dépôt des demandes et des pièces", lifespan=_cycle)
app.include_router(routeur_assure)


def depot_ingestion() -> IngestionPostgres:
    url = ConfigBase().database_url
    if not url:
        raise HTTPException(503, "base non configurée (KALDERA_DATABASE_URL)")
    try:
        return IngestionPostgres(pool(url))
    except psycopg.Error as exc:
        raise HTTPException(503, "base injoignable") from exc


def config_ingestion() -> ConfigIngestion:
    return ConfigIngestion()


Ingestion = Annotated[IngestionPostgres, Depends(depot_ingestion)]
Config = Annotated[ConfigIngestion, Depends(config_ingestion)]


@app.exception_handler(ErreurPersistance)
def _base_indisponible(request: Request, exc: ErreurPersistance) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "base indisponible"})


class ContratGestion(BaseModel):
    """État courant du contrat (système de gestion) ; les termes viennent du PDF seul."""

    model_config = ConfigDict(extra="forbid")

    numero: str = Field(min_length=1)
    statut: str
    cotisations_a_jour: bool


class DemandeCreation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(pattern=r"^KAL-\d{2}-\d{4}$")
    assure: dict[str, Any]
    contrat: ContratGestion
    sinistre: dict[str, Any]
    historique: dict[str, Any] = {}


class StatutDemande(BaseModel):
    reference: str
    statut: str
    fiche: dict[str, Any] | None = None


class Depot(BaseModel):
    sha256: str
    piece_id: UUID | None = None


@app.post("/demandes", status_code=201, response_model=StatutDemande)
def creer_demande(demande: DemandeCreation, ingestion: Ingestion) -> StatutDemande:
    if not ingestion.creer_demande(demande.model_dump()):
        raise HTTPException(409, "référence déjà connue")
    return StatutDemande(reference=demande.reference, statut="admission")


@app.post("/demandes/{reference}/pieces", status_code=202, response_model=Depot)
def deposer(
    reference: str,
    fichier: UploadFile,
    role: Annotated[Literal["contrat", "initiale", "depot"], Form()],
    ingestion: Ingestion,
    config: Config,
    response: Response,
    type_piece: Annotated[
        Literal["facture", "photo", "depot_plainte"] | None, Form(alias="type")
    ] = None,
    relance: Annotated[int | None, Form(ge=1)] = None,
) -> Depot:
    if role != "contrat" and type_piece is None:
        raise HTTPException(422, "type de pièce requis")
    if (role == "depot") != (relance is not None):
        raise HTTPException(422, "relance requise pour un dépôt, interdite sinon")
    statut = ingestion.statut(reference)
    if statut is None:
        raise HTTPException(404, "demande inconnue")
    if statut != "admission":
        raise HTTPException(409, "demande déjà soumise au traitement")
    octets = fichier.file.read(config.taille_max_mo * 1024 * 1024 + 1)
    try:
        mime, sha256 = controler_fichier(octets, config.taille_max_mo, contrat=role == "contrat")
    except FichierRefuse as exc:
        raise HTTPException(exc.code, exc.raison) from exc
    if role == "contrat":
        ingestion.deposer_contrat(reference, octets, mime, sha256)
        return Depot(sha256=sha256)
    assert type_piece is not None  # garanti par le contrôle ci-dessus
    piece_id, nouvelle = ingestion.deposer_piece(
        reference, octets, mime, sha256, type_piece, relance
    )
    if not nouvelle:
        response.status_code = 200  # ING-04 : déjà déposée, rien de nouveau
    return Depot(sha256=sha256, piece_id=piece_id)


@app.post("/demandes/{reference}/soumettre", status_code=202, response_model=StatutDemande)
def soumettre(reference: str, ingestion: Ingestion) -> StatutDemande:
    if ingestion.soumettre(reference):
        return StatutDemande(reference=reference, statut="admission")
    if ingestion.statut(reference) is None:
        raise HTTPException(404, "demande inconnue")
    raise HTTPException(409, "demande déjà soumise au traitement")


@app.get("/demandes/{reference}", response_model=StatutDemande)
def lire_demande(reference: str, ingestion: Ingestion) -> StatutDemande:
    ligne = ingestion.lire(reference)
    if ligne is None:
        raise HTTPException(404, "demande inconnue")
    return StatutDemande(**ligne)
