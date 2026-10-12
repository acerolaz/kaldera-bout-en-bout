"""API de dépôt (dossier 2.4 ter) et de lecture du back-office (C3-2),
traitement et suivi de lot (C3-3) : routes minces, contrôles dans ``ingestion``,
SQL dans le dépôt.

Routes ``def`` synchrones : FastAPI les exécute dans son pool de threads (psycopg synchrone).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import traitements
from . import vue_gestionnaire as vue
from .flux import diffuser, ecouter
from .ingestion import FichierRefuse, controler_fichier
from .ingestion_postgres import IngestionPostgres
from .lots_postgres import DepotLots, DossiersNonLancables, ReferencesInconnues
from .ports import ErreurPersistance
from .postgres import ConfigBase, pool
from .vlm import ConfigIngestion
from .vue_gestionnaire import DossierVue, LigneDemande, LotVue

app = FastAPI(title="Kaldera — dépôt des demandes et des pièces")


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


def depot_lots(ingestion: Ingestion) -> DepotLots:
    return DepotLots(ingestion.connexions)


Lots = Annotated[DepotLots, Depends(depot_lots)]


@app.exception_handler(ErreurPersistance)
def _base_indisponible(request: Request, exc: ErreurPersistance) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "base indisponible"})


@app.exception_handler(ReferencesInconnues)
def _references_inconnues(request: Request, exc: ReferencesInconnues) -> JSONResponse:
    return JSONResponse(
        status_code=404, content={"detail": "demande inconnue", "references": exc.references}
    )


@app.exception_handler(DossiersNonLancables)
def _non_lancables(request: Request, exc: DossiersNonLancables) -> JSONResponse:
    return JSONResponse(
        status_code=409, content={"detail": "dossiers non lançables", "references": exc.references}
    )


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


class Traitement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    references: list[Annotated[str, Field(pattern=r"^KAL-\d{2}-\d{4}$")]] = Field(min_length=1)

    @field_validator("references")
    @classmethod
    def _sans_doublon(cls, references: list[str]) -> list[str]:
        if len(set(references)) != len(references):
            raise ValueError("référence en double")
        return references


class LotLance(BaseModel):
    lot_id: int
    references: list[str]


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


@app.get("/demandes", response_model=list[LigneDemande])
def lister_demandes(
    ingestion: Ingestion,
    statut: vue.StatutDemande | None = None,
    issue: vue.CodeIssue | None = None,
    file: str | None = None,
    mode_degrade: bool | None = None,
    q: str | None = None,
) -> list[LigneDemande]:
    lignes = vue.lignes((d.reference, d.statut, d.fiche, d.etat) for d in ingestion.lister())
    return vue.filtrer(
        lignes, statut=statut, issue=issue, file=file, mode_degrade=mode_degrade, q=q
    )


@app.get("/demandes/{reference}", response_model=DossierVue)
def lire_demande(reference: str, ingestion: Ingestion) -> DossierVue:
    demande = ingestion.lire_dossier(reference)
    if demande is None:
        raise HTTPException(404, "demande inconnue")
    return vue.dossier(demande.reference, demande.statut, demande.fiche, demande.etat)


@app.post("/traitements", status_code=202, response_model=LotLance)
def lancer_traitement(corps: Traitement, lots: Lots, taches: BackgroundTasks) -> LotLance:
    lot_id, demandes = lots.lancer(corps.references)  # 404 / 409 : gestionnaires ci-dessus
    taches.add_task(traitements.traiter, lots.connexions, demandes)
    return LotLance(lot_id=lot_id, references=corps.references)


@app.get("/lots/{lot_id}", response_model=LotVue)
def lire_lot(lot_id: int, lots: Lots) -> LotVue:
    lu = lots.lire(lot_id)
    if lu is None:
        raise HTTPException(404, "lot inconnu")
    demandes = ((d.reference, d.statut, d.fiche, d.etat) for d in lu.demandes)
    return vue.lot(lu.id, lu.debut, lu.derniere_maj, demandes)


def _flux(connexions: ConnectionPool, references: frozenset[str]) -> StreamingResponse:
    return StreamingResponse(
        diffuser(ecouter(str(connexions.conninfo)), references),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/flux/demandes/{reference}")
async def flux_demande(reference: str, ingestion: Ingestion) -> StreamingResponse:
    if await run_in_threadpool(ingestion.statut, reference) is None:
        raise HTTPException(404, "demande inconnue")
    return _flux(ingestion.connexions, frozenset({reference}))


@app.get("/flux/lots/{lot_id}")
async def flux_lot(lot_id: int, lots: Lots) -> StreamingResponse:
    references = await run_in_threadpool(lots.references, lot_id)
    if references is None:
        raise HTTPException(404, "lot inconnu")
    return _flux(lots.connexions, frozenset(references))
