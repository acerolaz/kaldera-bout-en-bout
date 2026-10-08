"""Mémoire partagée d'une demande : un objet typé, une section = un seul écrivain.

Les agents ne modifient jamais cet objet : ils proposent un patch de leur section,
l'orchestrateur le contrôle puis l'affecte (validation Pydantic à l'affectation).
"""

from __future__ import annotations

from collections.abc import Mapping
from time import monotonic
from types import MappingProxyType
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Bornes(BaseModel):
    """Bornes d'exécution provisoires (dossier 2.3), à éprouver au chantier 2."""

    model_config = ConfigDict(frozen=True)

    etapes_max: int = 12
    duree_max_s: float = Field(default=8, gt=0, le=10)  # engagement de service §12 : 10 s
    relances_pieces_max: int = 1
    delai_partenaire_s: float = 3


BORNES = Bornes()  # bornes en vigueur : seule source pour bornes() et l'orchestrateur


# ------------------------------------------------------------ sections métier


class Piece(BaseModel):
    type: str
    lisible: bool = False
    montant: float | None = None


class Eligibilite(BaseModel):
    eligible: bool
    conditions_ko: list[str] = []


class Pieces(BaseModel):
    statut: Literal["complet", "incomplet", "manquant"]
    manquantes: list[str] = []
    retenues: list[Piece] = []


class Estimation(BaseModel):
    justifie: float = Field(ge=0)
    retenu: float = Field(ge=0)
    franchise: float = Field(ge=0)
    plafond: float = Field(ge=0)
    estime: float = Field(ge=0)


class AvisFraude(BaseModel):
    requis: bool
    indicateurs: list[str] = []
    statut: Literal["non_requis", "avis", "indisponible"]
    avis: dict[str, Any] | None = None


class Issue(BaseModel):
    issue: Literal["decision", "escalade"]
    decision: Literal["acceptee", "refusee"] | None = None
    montant_rembourse: float | None = None
    motif: str = Field(min_length=3)
    file: str | None = None
    mode_degrade: bool = False

    @model_validator(mode="after")
    def _coherente(self) -> Issue:
        if self.issue == "decision":
            if self.decision is None or self.montant_rembourse is None:
                raise ValueError("une décision porte un verdict et un montant")
            if self.montant_rembourse < 0:
                raise ValueError("montant remboursé négatif")
        elif not self.file:
            raise ValueError("une escalade désigne une file")
        return self


# section métier → seul agent autorisé à l'écrire
PROPRIETAIRES: Mapping[str, str] = MappingProxyType(
    {
        "eligibilite": "orchestrateur",  # via le tool is_eligible()
        "pieces": "pieces",
        "estimation": "estimation",
        "avis_fraude": "antifraude",
        "issue": "decision",
    }
)
SECTIONS = tuple(PROPRIETAIRES)


# ------------------------------------------------------- pilotage (orchestrateur)


class Compteurs(BaseModel):
    etapes: int = 0
    relances: int = 0
    appels_externes: int = 0


class Arret(BaseModel):
    borne: str
    valeur: float
    etape: int  # étapes consommées au moment de l'arrêt
    etat: str | None = None  # état où la borne a interrompu le flux


class EtatDemande(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    demande: dict[str, Any]
    # sections métier
    eligibilite: Eligibilite | None = None
    pieces: Pieces | None = None
    estimation: Estimation | None = None
    avis_fraude: AvisFraude | None = None
    issue: Issue | None = None
    # pilotage — écrit par l'orchestrateur seul
    etat_courant: str = "eligibilite"
    trace: list[dict[str, Any]] = []
    compteurs: Compteurs = Field(default_factory=Compteurs)
    debut: float = Field(default_factory=monotonic)
    arret: Arret | None = None
    escalade_forcee: str | None = None  # raison d'une escalade forcée (borne, échec)
