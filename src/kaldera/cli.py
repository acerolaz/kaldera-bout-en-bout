"""Rejoue des demandes : ``python -m kaldera.cli eval/scenarios.jsonl [--scenario ID]``.

``--charger`` : insère les demandes en « prete » (base requise) ; le gestionnaire les lance
depuis l'IHM (E1 → E2 / E3), rien n'est traité ici.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import traiter_lot
from .ingestion_postgres import IngestionPostgres
from .postgres import ConfigBase, pool


def charger(scenarios: list[dict[str, Any]], ingestion: IngestionPostgres) -> tuple[int, list[str]]:
    """Insère chaque demande en « prete » ; renvoie (chargées, références déjà en base)."""
    chargees, ignorees = 0, []
    for scenario in scenarios:
        for demande in scenario["demandes"]:
            if ingestion.charger(demande):
                chargees += 1
            else:
                ignorees.append(demande["reference"])
    return chargees, ignorees


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fichier", type=Path, help="fichier JSONL de scénarios")
    parser.add_argument("--scenario", action="append", help="identifiant(s) de scénario à rejouer")
    parser.add_argument("--partenaire", default=None, help="URL du partenaire anti-fraude")
    parser.add_argument("--trace", action="store_true", help="affiche la trace de chaque fiche")
    parser.add_argument(
        "--charger", action="store_true", help="insère les demandes en « prete », sans traiter"
    )
    args = parser.parse_args()

    scenarios = [
        s
        for s in map(json.loads, filter(str.strip, args.fichier.read_text("utf-8").splitlines()))
        if not args.scenario or s["id"] in args.scenario
    ]
    if args.charger:
        url = ConfigBase().database_url
        if not url:
            raise SystemExit("KALDERA_DATABASE_URL absente : rien à charger")
        chargees, ignorees = charger(scenarios, IngestionPostgres(pool(url)))
        deja = ", ".join(ignorees) or "aucune"
        print(f"{chargees} demandes prêtes ; déjà en base, ignorées : {deja}")
        return
    for scenario in scenarios:
        print(f"== {scenario['id']} — {scenario['titre']}")
        resultat = traiter_lot(scenario["demandes"], partenaire_url=args.partenaire)
        for fiche in resultat["fiches"]:
            if not args.trace:
                fiche = {k: v for k, v in fiche.items() if k != "trace"}
            print(json.dumps(fiche, ensure_ascii=False))
        synthese = {"metriques": resultat["metriques"], "equipe": resultat["equipe"]}
        print(json.dumps(synthese, ensure_ascii=False))


if __name__ == "__main__":
    main()
