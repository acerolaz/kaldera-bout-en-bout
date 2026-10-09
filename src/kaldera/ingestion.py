"""Ingestion (dossier 2.4 ter, 2.4 quater) : le domaine, sans base ni VLM.

« Le VLM analyse, le code vérifie » : contrôles du fichier au dépôt, invariants des pièces,
trois verrous du contrat, puis la demande vue par l'équipe au niveau 1.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from . import regles

SIGNATURES = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


class FichierRefuse(Exception):
    """Fichier refusé au dépôt, sans stockage ni analyse : ``code`` HTTP (413 ou 415)."""

    def __init__(self, code: int, raison: str) -> None:
        super().__init__(raison)
        self.code, self.raison = code, raison


def type_mime(octets: bytes) -> str | None:
    """Type lu sur les octets, jamais sur le nom du fichier."""
    return next((mime for signature, mime in SIGNATURES if octets.startswith(signature)), None)


def controler_fichier(octets: bytes, taille_max_mo: int, *, contrat: bool) -> tuple[str, str]:
    """Contrôles synchrones du dépôt : taille, type réel ; renvoie (mime, sha256)."""
    if len(octets) > taille_max_mo * 1024 * 1024:
        raise FichierRefuse(413, f"fichier de plus de {taille_max_mo} Mo")
    mime = type_mime(octets)
    if mime is None or (contrat and mime != "application/pdf"):
        raise FichierRefuse(415, "type de fichier refusé (lu sur les octets)")
    return mime, hashlib.sha256(octets).hexdigest()


# PDF abîmé : pypdf lève des erreurs variées (dont AttributeError) ; pas de contrôle croisé
_PDF_ABIME = (
    PyPdfError,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    IndexError,
    RecursionError,
)


def texte_pdf(octets: bytes) -> str:
    """Couche texte d'un PDF natif ; vide pour un scan ou un PDF illisible."""
    try:
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(octets)).pages)
    except _PDF_ABIME:
        return ""


def nombre_pages(contenu: bytes) -> int:
    """Pages d'un PDF (0 s'il est illisible) : le VLM ne lit que la première (avertissement UI1)."""
    try:
        return len(PdfReader(io.BytesIO(contenu)).pages)
    except _PDF_ABIME:
        return 0


class AnalysePiece(BaseModel):
    """Sortie de ``analyser_piece`` : rien d'autre (une consigne glissée est refusée)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["facture", "photo", "depot_plainte"]
    lisible: bool
    # bornes de numeric(10,2) : une valeur que la base refuserait est refusée ici
    montant: Decimal | None = Field(default=None, max_digits=10, decimal_places=2)


class ExtractionContrat(BaseModel):
    """Sortie de ``extraire_contrat`` : les termes signés du contrat."""

    model_config = ConfigDict(extra="forbid")

    numero: str
    formule: Literal["essentiel", "confort", "premium"]
    date_souscription: date
    franchise: Decimal = Field(ge=0, max_digits=10, decimal_places=2)  # CHECK de contrats
    plafond: Decimal = Field(gt=0, max_digits=10, decimal_places=2)


def _normalise(texte: str) -> str:
    return re.sub(r"[\s  ]", "", texte).replace(",", ".")


def _formes(montant: Decimal) -> set[str]:
    formes = {f"{montant:.2f}", f"{montant.normalize():f}"}
    if montant == montant.to_integral_value():
        formes.add(f"{montant:.0f}")
    return formes


def _present(formes: set[str], texte_normalise: str) -> bool:
    return any(forme in texte_normalise for forme in formes)


def invariants_piece(a: AnalysePiece, type_declare: str, texte: str) -> list[str]:
    """Violations de la sortie du VLM pour une pièce (vide = descripteur accepté)."""
    violations = []
    if a.type != "facture" and a.montant is not None:
        violations.append("montant hors facture")
    if a.type == "facture" and a.montant is None:
        violations.append("facture sans montant")
    if a.montant is not None and a.montant <= 0:
        violations.append("montant négatif ou nul")
    if a.type != type_declare:
        violations.append(f"type lu {a.type} ≠ type déclaré {type_declare}")
    if texte and a.montant is not None and a.montant > 0:
        if not _present(_formes(a.montant), _normalise(texte)):
            violations.append("montant absent de la couche texte")  # contrôle croisé gratuit
    return violations


def verrous_contrat(
    brut: dict[str, Any], numero_attendu: str, texte: str
) -> tuple[ExtractionContrat | None, list[str]]:
    """Trois verrous : ① schéma et numéro, ② barème, ③ couche texte (si le PDF en a une)."""
    try:
        contrat = ExtractionContrat.model_validate(brut)
    except ValidationError:
        return None, ["① schéma"]
    violations = []
    if contrat.numero != numero_attendu:
        violations.append("① numéro ≠ demande")
    bareme = regles.FORMULES[contrat.formule]
    if contrat.franchise != Decimal(str(bareme["franchise"])) or contrat.plafond != Decimal(
        str(bareme["plafond"])
    ):
        violations.append("② barème")
    if texte:
        normalise = _normalise(texte)
        valeurs = {
            "numero": {_normalise(contrat.numero)},
            "franchise": _formes(contrat.franchise),
            "plafond": _formes(contrat.plafond),
            "date_souscription": {
                contrat.date_souscription.isoformat(),
                contrat.date_souscription.strftime("%d/%m/%Y"),
            },
        }
        absents = [nom for nom, formes in valeurs.items() if not _present(formes, normalise)]
        if absents:
            violations.append("③ absent de la couche texte : " + ", ".join(absents))
    return contrat, violations


def demande_niveau_1(demande: dict[str, Any], contrat: dict[str, Any] | None) -> dict[str, Any]:
    """La demande vue par l'équipe : état du contrat (gestion) + termes extraits (PDF)."""
    gestion = demande["contrat"]  # numero, statut, cotisations_a_jour : système de gestion
    if contrat is None:
        termes: dict[str, Any] = {
            "statut_extraction": "non_exploitable",
            "violations": ["contrat absent"],
        }
    else:
        termes = dict(contrat)  # formule, date, statut_extraction, violations, provenance
    return {**demande, "contrat": {**gestion, **termes, "source": "extraction_vlm"}}
