"""Test de fumée manuel (hors CI) : le VLM du .env lit le contrat et la facture de NOM-01.

Usage : uv run python scripts/fumee_vlm.py   (après tools/generer_pieces.py)
"""

from __future__ import annotations

import time
from pathlib import Path

from kaldera.ingestion import (
    AnalysePiece,
    ExtractionContrat,
    invariants_piece,
    texte_pdf,
    verrous_contrat,
)
from kaldera.vlm import ConfigIngestion, ErreurVLM, consigne, fabrique_vlm

DOSSIER = Path(__file__).resolve().parents[1] / "fixtures/pieces/KAL-26-0101"


def main() -> None:
    config = ConfigIngestion()
    vlm = fabrique_vlm(config)
    if vlm is None:
        print("Aucun VLM : renseigner AZURE_AI_* et KALDERA_INGESTION__VLM__* (VISION=true)")
        return
    for fichier, tache, schema in (
        ("contrat.pdf", "extraire_contrat", ExtractionContrat),
        ("initiale_01_facture.pdf", "analyser_piece", AnalysePiece),
    ):
        octets = (DOSSIER / fichier).read_bytes()
        texte, version = consigne(tache)
        debut = time.perf_counter()
        try:
            sortie = vlm.analyser(octets, "application/pdf", texte, schema, config.delai_analyse_s)
        except ErreurVLM as exc:
            print(f"{fichier}: ErreurVLM {exc}")
            continue
        duree = time.perf_counter() - debut
        if tache == "extraire_contrat":
            _, violations = verrous_contrat(sortie, "CTR-778801", texte_pdf(octets))
        else:
            violations = invariants_piece(
                AnalysePiece.model_validate(sortie), "facture", texte_pdf(octets)
            )
        print(f"{fichier} ({vlm.modele}, prompt {version}) {duree:.1f} s → {sortie} {violations}")


if __name__ == "__main__":
    main()
