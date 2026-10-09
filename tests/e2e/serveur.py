"""Serveur de bout en bout (Playwright) : API réelle + worker sur FakeVLM, partenaire coupé.

Base : TEST_DATABASE_URL, vidée puis préparée (tools.demo_assure). Aucun appel Azure : les
profils LLM sont retirés de l'environnement et le .env n'est pas lu (agents en gabarit/repli).
Usage : uv run python -m tests.e2e.serveur (lancé par front/playwright.config.ts).
"""

from __future__ import annotations

import os
import re
import threading
import time

import uvicorn

ENV_LLM = re.compile(
    r"^(AZURE_AI_|KALDERA_(PIECES|ESTIMATION|ANTIFRAUDE|DECISION|RELANCE|INGESTION)__)"
)


def main() -> None:
    for variable in [v for v in os.environ if ENV_LLM.match(v)]:
        del os.environ[variable]
    url = os.environ["TEST_DATABASE_URL"]
    os.environ.update(
        KALDERA_DATABASE_URL=url,
        KALDERA_SESSION_SECRET=os.environ.get("KALDERA_SESSION_SECRET", "secret-e2e"),
        KALDERA_COOKIE_SECURE="false",
        KALDERA_FRONT_ORIGIN="http://localhost:5173",
        PARTENAIRE_URL="http://127.0.0.1:9",
    )
    from kaldera import llm
    from kaldera.ingestion_postgres import IngestionPostgres
    from kaldera.ports import ErreurPersistance
    from kaldera.postgres import pool
    from kaldera.vlm import ConfigIngestion, FakeVLM
    from kaldera.worker import travailler
    from tools.demo_assure import preparer
    from tools.seed import lire_manifeste, verites_fake

    llm.charger_config = lambda: llm.ConfigAgents(_env_file=None)  # le .env n'est jamais lu
    connexions = pool(url)
    with connexions.connection() as conn:
        conn.execute(
            "TRUNCATE evenements_assure, demandes_assure, utilisateurs, appels_partenaire, "
            "pieces, file_ingestion, analyses, demandes, contrats, blobs"
        )
    preparer(connexions)
    ingestion = IngestionPostgres(connexions)
    vlm = FakeVLM(verites_fake(lire_manifeste()))
    config = ConfigIngestion(_env_file=None, delai_analyse_s=5)

    def boucle() -> None:
        while True:
            try:
                occupe = travailler(ingestion, vlm, config)
            except ErreurPersistance:
                occupe = False
            if not occupe:
                time.sleep(0.2)

    threading.Thread(target=boucle, daemon=True).start()
    uvicorn.run("kaldera.api:app", host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
