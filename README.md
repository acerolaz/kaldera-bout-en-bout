# Kaldera

Plateforme de traitement des demandes de remboursement d'assurance habitation.
Une équipe de quatre agents (pièces, estimation, anti-fraude, décision) est
orchestrée par une machine à états déterministe. Chaque agent appelle son propre
LLM et dispose d'un repli déterministe. Le service anti-fraude partenaire est
consulté selon le protocole agent-à-agent (A2A). Les pièces déposées par l'assuré
sont lues par un VLM, utilisé comme outil, puis vérifiées par le code.

> Principe : le LLM raisonne, l'outil calcule, le code vérifie.

## Features

- **Orchestration** : machine à états T0–T11 (`machine.py`), gardes d'entrée,
  bornes d'exécution (étapes, durée, relances) et filet de secours. Une demande
  finit toujours par une décision ou une escalade motivée.
- **Agents LLM** : un modèle par rôle, configuré dans le `.env`. Chaque agent
  dispose d'une liste d'outils autorisés et d'une boucle bornée. Sa sortie passe
  par un garde-fou, qui la compare à la référence déterministe et vérifie
  qu'elle ne contient pas de données sensibles. En cas d'échec, l'agent se
  replie sur la référence, et ce repli est tracé.
- **Règle 0** : un contrat illisible ou incohérent part en escalade vers un
  gestionnaire, au lieu d'être deviné.
- **Partenaire anti-fraude** (JSON-RPC 2.0, Agent Card) :
  - projection stricte des données envoyées ;
  - un seul appel par dossier ;
  - mode dégradé quand le partenaire est indisponible.
- **Persistance** (PostgreSQL, facultative) : un snapshot par transition, une
  fin de traitement en compare-and-set, et un reaper qui reprend les demandes
  bloquées.
- **Ingestion des pièces** :
  - **API de dépôt** : type de fichier lu sur les octets, taille bornée,
    doublon refusé ;
  - **worker** : file `SKIP LOCKED` et cache des analyses ;
  - **VLM** (Azure, vision) : il ne reçoit que l'image du document, puis ses
    sorties sont contrôlées par les invariants des pièces et les 3 verrous du
    contrat.
- **Épreuve** :
  - un générateur de pièces factices déterministe ;
  - un seed qui rejoue un manifeste par l'API ;
  - une mesure de la précision par champ, des cas ING-01 → 05 et de
    l'invariance niveau 1 / niveau 0 ;
  - des scénarios de recette, des métriques par agent et un journal des
    ajustements.

## Stack

- Python 3.11 (uv)
- FastAPI / uvicorn (API d'ingestion, service partenaire simulé)
- pydantic 2, pydantic-settings
- langchain-azure-ai (agents LLM et VLM ; les modèles sont configurés dans le `.env`)
- httpx (client A2A, seed)
- PostgreSQL 16, psycopg 3 + psycopg_pool
- pypdf, pypdfium2, Pillow ; reportlab (générateur, en dépendance de développement)
- pytest, ruff, mypy
- Docker Compose (service partenaire ; PostgreSQL sous le profil `integration`)

## Setup

```bash
make install              # uv sync : installe les dépendances
cp .env.example .env      # puis renseigner les valeurs (voir ci-dessous)
make up                   # docker compose up -d : service partenaire sur :8100
make test                 # tests unitaires et d'acceptance
make test-integration     # démarre PostgreSQL (port 5433) puis lance les tests d'intégration
```

Sans Docker, le service partenaire se lance aussi en local : `make partenaire`.

Configuration (`.env`) :

- `AZURE_AI_ENDPOINT`, `AZURE_AI_API_KEY` : identifiants Azure AI, partagés par
  les agents et le VLM.
- `KALDERA_<AGENT>__MODELE` (et `DELAI_AGENT_S`, `JETONS_MAX`, `TOURS_MAX`), pour
  `PIECES`, `ESTIMATION`, `ANTIFRAUDE` et `DECISION`. Sans ces lignes, chaque
  agent tourne en repli déterministe, tracé `llm_non_configure`.
- `KALDERA_DATABASE_URL` : sans cette variable, aucune persistance n'est active.
- `KALDERA_INGESTION__VLM__MODELE` et `KALDERA_INGESTION__VLM__VISION=true` :
  VLM d'ingestion. Sans eux, le worker refuse de démarrer.
- `PARTENAIRE_URL`, `PARTENAIRE_JETON` : service anti-fraude.

## Utilisation

Traitement direct des demandes JSON (niveau 0) :

```bash
make scenarios                                    # rejoue eval/scenarios.jsonl
make scenarios ARGS="--scenario NOM-01 --trace"   # un scénario, avec sa trace
make ctl ARGS=panne                               # met le service partenaire en panne
make ctl ARGS=journal                             # appels reçus par le partenaire
```

Ingestion des fichiers (niveau 1, `KALDERA_DATABASE_URL` requis) :

```bash
make api        # API de dépôt sur :8000 (POST /demandes, /pieces, /soumettre)
make worker     # analyse les fichiers, admet et fait traiter les demandes
make reaper     # escalade de secours des demandes bloquées
```

Épreuve de l'ingestion (sur une base vide) :

```bash
make generer          # régénère fixtures/pieces (déterministe, --seed 42)
make api &            # puis, dans un autre terminal :
make worker-epreuve   # worker avec le partenaire indisponible (invariance)
make seed             # dépose tout le manifeste par l'API et attend le traitement
make eval-ingestion   # rapport dans eval/rapports/
```

Tests de fumée manuels, avec les vrais modèles (hors CI) :
`uv run python scripts/fumee_llm.py` et `make fumee-vlm`.

Les cibles `make` chargent `.env`. Hors `make` : `set -a; . ./.env; set +a`.

## Layout

- `src/kaldera/` : traitement des demandes
  - `machine.py`, `etat.py`, `orchestrateur.py` : machine à états, état partagé, moteur
  - `agents.py`, `agents_llm.py`, `gardes_fous.py`, `llm.py`, `prompts/` : agents
    déterministes (référence et repli), agents LLM, garde-fous, port LLM, consignes
  - `partenaire.py`, `espace_assure.py`, `regles.py` : client A2A, espace assuré, référentiel métier
  - `ports.py`, `memoire.py`, `postgres.py`, `reaper.py`, `migrations/` : persistance
  - `api.py`, `worker.py`, `ingestion.py`, `ingestion_postgres.py`, `vlm.py` : ingestion des pièces
- `tools/` : `generer_pieces.py` (générateur), `seed.py`, `eval_ingestion.py` (épreuve)
- `fixtures/pieces/` : pièces factices générées et leur manifeste (versionnés)
- `eval/scenarios.jsonl`, `eval/scenarios_ingestion.jsonl` : scénarios de recette et d'ingestion
- `external_agent/` : service anti-fraude partenaire simulé et son contrat d'échange (`contrat.md`)
- `scripts/` : pilotage du partenaire simulé et tests de fumée LLM/VLM
- `tests/unit/`, `tests/acceptance/`, `tests/integration/` : tests (l'intégration exige PostgreSQL)
- `docs/specs_metier.md`, `docs/interface.md` : spécifications fonctionnelles, contrat d'intégration
- `docs/journal_ajustements.md` : ajustements consignés et bornes en vigueur
- `docs/superpowers/` : specs et plans d'implémentation du chantier 1

## Useful commands

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make down       # arrête les services docker
```

## Known issues

- Les 14 tests de `tests/acceptance/test_collaboration_a2a.py` échouent : la
  conformité stricte au contrat A2A relève du chantier 2, tout comme le
  disjoncteur LLM et `make eval`.
- Les chemins réels Azure (agents LLM et VLM) n'ont pas été éprouvés dans
  l'environnement de développement. L'épreuve de l'ingestion avec le vrai VLM
  n'a pas encore été mesurée.
- Le VLM ne lit que la première page des PDF : un contrat de plusieurs pages
  serait mal lu.

## License

Usage interne — tous droits réservés.
