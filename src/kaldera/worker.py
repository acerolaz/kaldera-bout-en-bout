"""Worker d'ingestion (dossier 2.4 ter) : analyse les fichiers, puis admet et fait traiter.

Plusieurs workers peuvent tourner : ``SKIP LOCKED`` répartit les tâches, l'admission est un
compare-and-set ; le VLM est appelé hors transaction, ses sorties sont vérifiées par le code.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from . import evenements, relance
from .assure_postgres import DepotAssure
from .ingestion import (
    AnalysePiece,
    ExtractionContrat,
    demande_niveau_1,
    invariants_piece,
    texte_pdf,
    verrous_contrat,
)
from .ingestion_postgres import IngestionPostgres, Tache
from .orchestrateur import Orchestrateur
from .ports import ErreurPersistance
from .postgres import ConfigBase, DepotPostgres, SnapshotsPostgres, pool
from .vlm import ClientVLM, ConfigIngestion, ErreurVLM, consigne, fabrique_vlm

LOGGER = logging.getLogger(__name__)
PAUSE_S = 1.0
ESSAIS_MAX = 3  # prises d'une tâche avant échec (fichier qui fait planter le worker)
SCHEMAS: dict[str, type[BaseModel]] = {
    "analyser_piece": AnalysePiece,
    "extraire_contrat": ExtractionContrat,
}


def travailler(ingestion: IngestionPostgres, vlm: ClientVLM, config: ConfigIngestion) -> bool:
    """Un tour : reprise, une tâche, admissions. Vrai si une tâche a été traitée."""
    ingestion.reprendre_bloquees(2 * config.delai_analyse_s, ESSAIS_MAX)
    tache = ingestion.prendre_tache()
    if tache is not None:
        _analyser(ingestion, vlm, config, tache)
        _admettre(ingestion, tache.reference)
    for reference in ingestion.admissibles():  # tout en cache, ou soumise après la fin
        _admettre(ingestion, reference)
    return tache is not None


def _analyser(
    ingestion: IngestionPostgres, vlm: ClientVLM, config: ConfigIngestion, tache: Tache
) -> None:
    texte_consigne, version = consigne(tache.tache)
    brut = ingestion.analyse_en_cache(tache.sha256, vlm.modele, version)
    if brut is None:
        try:
            brut = vlm.analyser(
                tache.contenu,
                tache.mime,
                texte_consigne,
                SCHEMAS[tache.tache],
                config.delai_analyse_s,
            )
        except ErreurVLM as exc:
            LOGGER.warning("VLM en échec, fichier %s : %s", tache.sha256[:12], exc)
        else:
            try:
                SCHEMAS[tache.tache].model_validate(brut)
            except ValidationError:
                LOGGER.warning("sortie VLM non conforme, fichier %s", tache.sha256[:12])
                brut = None  # validée une fois : en aval, brut est conforme ou absent
            else:
                ingestion.mettre_en_cache(tache.sha256, vlm.modele, version, brut)
    texte = texte_pdf(tache.contenu) if tache.mime == "application/pdf" else ""
    if tache.tache == "analyser_piece":
        lu = _piece(ingestion, tache, brut, texte)
    else:
        lu = _contrat(ingestion, tache, brut, texte, vlm.modele, version)
    ingestion.finir_tache(tache.id, "faite" if lu else "echec")
    if tache.tache == "analyser_piece":
        _publier_analyse(ingestion, tache, config)


def _publier_analyse(ingestion: IngestionPostgres, tache: Tache, config: ConfigIngestion) -> None:
    """Vue projetée + message spontané (gabarit, jamais de LLM dans le worker)."""
    depot = DepotAssure(ingestion.connexions)
    vue = evenements.publier_vue(depot, tache.reference, "piece", config.delai_analyse_s)
    if vue is None:
        return
    type_piece = ingestion.type_declare(tache.reference, tache.sha256)
    texte = relance.message_spontane(type_piece, vue.pieces)
    if texte:
        a_refaire = any(p.statut == "a_refaire" for p in vue.pieces)
        evenements.publier_message(
            depot, tache.reference, "agent", texte, ["deposer"] if a_refaire else []
        )


def _piece(
    ingestion: IngestionPostgres, tache: Tache, brut: dict[str, Any] | None, texte: str
) -> bool:
    analyse = None if brut is None else AnalysePiece.model_validate(brut)
    if analyse is None:
        violations = ["analyse impossible"]
    else:
        violations = invariants_piece(
            analyse, ingestion.type_declare(tache.reference, tache.sha256), texte
        )
    if violations:
        LOGGER.warning("pièce %s en échec : %s", tache.sha256[:12], "; ".join(violations))
        ingestion.ecrire_piece(tache.reference, tache.sha256, "echec", False, None)
    else:
        assert analyse is not None
        ingestion.ecrire_piece(
            tache.reference, tache.sha256, "ok", analyse.lisible, analyse.montant
        )
    return analyse is not None


def _contrat(
    ingestion: IngestionPostgres,
    tache: Tache,
    brut: dict[str, Any] | None,
    texte: str,
    modele: str,
    version: str,
) -> bool:
    numero = ingestion.numero_contrat(tache.reference)
    if brut is None:
        extraction, violations = None, ["extraction impossible"]
    else:
        extraction, violations = verrous_contrat(brut, numero, texte)
    if violations:
        LOGGER.warning("contrat %s non exploitable : %s", numero, "; ".join(violations))
    ingestion.ecrire_contrat(numero, tache.sha256, extraction, violations, modele, version)
    return extraction is not None


def _admettre(ingestion: IngestionPostgres, reference: str) -> None:
    demande = ingestion.admettre(reference)
    if demande is None:
        return
    depot = DepotAssure(ingestion.connexions)
    evenements.publier_vue(depot, reference, "etape", 0.0)  # étape 2 : vérification
    demande = demande_niveau_1(demande, ingestion.contrat(demande["contrat"]["numero"]))
    fiche = Orchestrateur(
        depot=DepotPostgres(ingestion.connexions),
        snapshots=SnapshotsPostgres(ingestion.connexions),
    ).traiter(demande)
    atteints = {t.get("vers") for t in fiche.get("trace", [])}
    for etat, etape in (("estimation", 3), ("antifraude", 4)):
        if etat in atteints:
            evenements.publier_vue(depot, reference, "etape", 0.0, etape=etape)
    evenements.publier_vue(depot, reference, "verdict", 0.0)


def main() -> None:
    """``python -m kaldera.worker`` : boucle, pause quand la file est vide."""
    logging.basicConfig(level=logging.INFO)
    url = ConfigBase().database_url
    config = ConfigIngestion()
    vlm = fabrique_vlm(config)
    if not url:
        raise SystemExit("KALDERA_DATABASE_URL absente : rien à ingérer")
    if vlm is None:
        raise SystemExit(
            "aucun VLM : KALDERA_INGESTION__VLM__MODELE, KALDERA_INGESTION__VLM__VISION=true, "
            "AZURE_AI_CHAT_ENDPOINT et AZURE_AI_CHAT_KEY sont requis"
        )
    ingestion = IngestionPostgres(pool(url))
    while True:
        try:
            occupe = travailler(ingestion, vlm, config)
        except ErreurPersistance as exc:
            LOGGER.error("worker : %s ; nouvel essai dans %s s", exc, PAUSE_S)
            occupe = False
        if not occupe:
            time.sleep(PAUSE_S)


if __name__ == "__main__":
    main()
