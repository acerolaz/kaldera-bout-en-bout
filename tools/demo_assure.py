"""Démonstration de l'espace assuré : une demande, son contrat, un compte assuré rattaché.

Usage : make demo-assure (KALDERA_DATABASE_URL requis ; lancer ensuite make api, make worker).
Demande KAL-26-0101 (NOM-01) tirée du manifeste ; compte « claire ». Le mot de passe de démo vient
de KALDERA_DEMO_MOT_DE_PASSE (défaut : kaldera-demo) — jamais pour un vrai compte.
"""

from __future__ import annotations

import os
from typing import Any

from psycopg_pool import ConnectionPool

from kaldera import auth
from kaldera.assure_postgres import DepotAssure
from kaldera.ingestion import controler_fichier
from kaldera.ingestion_postgres import IngestionPostgres
from kaldera.postgres import ConfigBase, pool
from tools.seed import MANIFESTE, lire_manifeste

MOT_DE_PASSE = os.environ.get("KALDERA_DEMO_MOT_DE_PASSE", "kaldera-demo")


def preparer(
    connexions: ConnectionPool,
    reference: str = "KAL-26-0101",
    identifiant: str = "claire",
    mot_de_passe: str = MOT_DE_PASSE,
    manifeste: list[dict[str, Any]] | None = None,
) -> bool:
    """Crée la demande et dépose son contrat ; faux si la demande existe déjà."""
    lignes = [x for x in (manifeste or lire_manifeste()) if x["reference"] == reference]
    demande = next(x["json"] for x in lignes if x["role"] == "demande")
    contrat = next(x for x in lignes if x["role"] == "contrat")
    # le contrat est lu et contrôlé avant toute écriture (pool en autocommit : pas de rollback)
    octets = (MANIFESTE.parent / contrat["fichier"]).read_bytes()
    mime, sha256 = controler_fichier(octets, 10, contrat=True)
    ingestion = IngestionPostgres(connexions)
    if not ingestion.creer_demande(demande):
        return False
    ingestion.deposer_contrat(reference, octets, mime, sha256)
    depot = DepotAssure(connexions)
    depot.rattacher(depot.creer_compte(identifiant, auth.hacher(mot_de_passe), "assure"), reference)
    return True


def main() -> None:
    url = ConfigBase().database_url
    if not url:
        raise SystemExit("KALDERA_DATABASE_URL absente")
    if not preparer(pool(url)):
        raise SystemExit("KAL-26-0101 existe déjà : base déjà préparée")
    print("Demande KAL-26-0101 prête ; connexion : claire / (KALDERA_DEMO_MOT_DE_PASSE)")


if __name__ == "__main__":
    main()
