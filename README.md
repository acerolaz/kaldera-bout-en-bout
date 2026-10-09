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
- **Espace sinistre de l'assuré** (`front/`, `docs/interface_web.md`) :
  - suivi du dossier en 5 étapes, avec le temps écoulé et le temps restant estimé ;
  - dépôt des pièces (glisser-déposer, photo mobile) ;
  - assistant pièces : un agent de relance, borné aux pièces, qui explique ce qui manque ;
  - verdict expliqué, sans aucune trace de l'anti-fraude.

## Stack

- Python 3.11 (uv)
- FastAPI / uvicorn (API d'ingestion, service partenaire simulé)
- pydantic 2, pydantic-settings
- azure-ai-inference (`ChatCompletionsClient`, Azure AI Foundry) : agents LLM et VLM ; les
  modèles sont configurés dans le `.env`
- httpx (client A2A, seed)
- PostgreSQL 16, psycopg 3 + psycopg_pool
- pypdf, pypdfium2, Pillow ; reportlab (générateur, en dépendance de développement)
- React, Vite, TypeScript, Tailwind, shadcn/ui (espace assuré, `front/`)
- argon2-cffi, itsdangerous (comptes et sessions de l'espace assuré)
- pytest, ruff, mypy ; Vitest, Playwright (front)
- Docker Compose (service partenaire ; PostgreSQL sous le profil `integration`)

## Setup

```bash
make install              # uv sync : installe les dépendances
cp .env.example .env      # puis renseigner les valeurs (voir ci-dessous)
make up                   # docker compose up -d : service partenaire sur :8100
cd front && npm install   # dépendances du front (espace assuré)
make test                 # tests unitaires et d'acceptance
make test-integration     # démarre PostgreSQL (port 5433) puis lance les tests d'intégration
```

Sans Docker, le service partenaire se lance aussi en local : `make partenaire`.

Configuration (`.env`) :

- `AZURE_AI_CHAT_ENDPOINT`, `AZURE_AI_CHAT_KEY` : endpoint d'inférence Azure AI Foundry
  (`https://<ressource>.services.ai.azure.com/models`) et sa clé, partagés par les agents
  et le VLM. Les `…__MODELE` sont des noms de déploiement Foundry.
- `KALDERA_<AGENT>__MODELE` (et `DELAI_AGENT_S`, `JETONS_MAX`, `TOURS_MAX`), pour
  `PIECES`, `ESTIMATION`, `ANTIFRAUDE` et `DECISION`. Sans ces lignes, chaque
  agent tourne en repli déterministe, tracé `llm_non_configure`.
- `KALDERA_DATABASE_URL` : sans cette variable, aucune persistance n'est active. En local,
  avec le PostgreSQL de Docker Compose : `postgresql://kaldera:kaldera@localhost:5433/kaldera_test`
  (base partagée avec les tests d'intégration et `make front-e2e`, qui la vident).
- `KALDERA_INGESTION__VLM__MODELE` et `KALDERA_INGESTION__VLM__VISION=true` :
  VLM d'ingestion. Sans eux, le worker refuse de démarrer.
- `PARTENAIRE_URL`, `PARTENAIRE_JETON` : service anti-fraude.
- `KALDERA_SESSION_SECRET` : secret de signature des sessions de l'espace assuré. Sans lui
  (ou s'il est vide), les routes `/assure/*` répondent 503. `KALDERA_FRONT_ORIGIN` (défaut
  `http://localhost:5173`) et `KALDERA_COOKIE_SECURE=false` (seulement en local, en http).
- `KALDERA_RELANCE__MODELE` (et `DELAI_AGENT_S`, `JETONS_MAX`, `TOURS_MAX`) : agent de relance.
  Sans profil, il répond par gabarits.

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

Enregistrer une demande et son contrat en base, à la main, par l'API (`make api` et
`make worker` lancés). Le corps de `POST /demandes` reprend le champ `json` d'une ligne
`"role": "demande"` du manifeste :

```bash
REF=KAL-26-0101; PIECES=fixtures/pieces/$REF
jq -c "select(.reference==\"$REF\" and .role==\"demande\") | .json" \
  fixtures/pieces/manifeste.jsonl > demande.json
curl -X POST localhost:8000/demandes -H 'Content-Type: application/json' -d @demande.json  # 201 ; 409 si déjà connue
curl -F role=contrat -F fichier=@$PIECES/contrat.pdf localhost:8000/demandes/$REF/pieces  # 202
curl -F role=initiale -F type=facture -F fichier=@$PIECES/initiale_01_facture.pdf \
  localhost:8000/demandes/$REF/pieces                                     # type : facture, photo, depot_plainte
curl -X POST localhost:8000/demandes/$REF/soumettre                       # 202 : part au worker
curl localhost:8000/demandes/$REF                                         # statut, puis fiche de décision
```

Le contrat est lu par le VLM, puis contrôlé par les 3 verrous (① schéma et numéro, ② barème, ③ couche texte du PDF).
Un contrat illisible ou incohérent part en escalade (règle 0). Codes de refus du dépôt :
404 (demande inconnue), 409 (déjà soumise), 413 (taille), 415 (format), 422 (champ manquant).

Épreuve de l'ingestion (sur une base vide) :

```bash
make generer          # régénère fixtures/pieces (déterministe, --seed 42)
make api &            # puis, dans un autre terminal :
make worker-epreuve   # worker avec le partenaire indisponible (invariance)
make seed             # dépose tout le manifeste par l'API et attend le traitement
make eval-ingestion   # rapport dans eval/rapports/
```

Espace sinistre de l'assuré (`KALDERA_DATABASE_URL`, `KALDERA_SESSION_SECRET` et
`KALDERA_COOKIE_SECURE=false` requis ; détails dans `docs/interface_web.md`) :

```bash
make up
docker compose --profile integration up -d --wait postgres
make demo-assure   # demande KAL-26-0101, son contrat et le compte « claire »
make api
make worker
make front         # http://localhost:5173
```

Connexion : `claire` / `kaldera-demo`. Ce mot de passe peut être changé par
`KALDERA_DEMO_MOT_DE_PASSE`, et ne sert jamais pour un vrai compte. `make demo-assure` et
`make seed` créent tous deux `KAL-26-0101` : on n'en lance qu'un par base (sinon « base déjà
préparée » ou « base déjà semée »).

Tests de fumée manuels, avec les vrais modèles (hors CI) :
`uv run python scripts/fumee_llm.py` et `make fumee-vlm`.

Les cibles `make` chargent `.env`. Hors `make` : `set -a; . ./.env; set +a`.

## Administration

Il n'y a pas encore de console d'administration (specs 2 et 3, maquette dans
`design-system/kaldera/pages/console-admin.md`), ni de commande pour créer un compte assuré
en dehors de la démo. L'exploitation se fait avec ces commandes :

```bash
# Partenaire anti-fraude simulé
make ctl ARGS=etat                                  # mode courant, nombre d'appels reçus
make ctl ARGS=normal                                # réponses conformes
make ctl ARGS=panne                                 # HTTP 503 (mode dégradé)
make ctl ARGS="lent --delai 6"                      # réponses tardives (délai en secondes)
make ctl ARGS="invalide --variante rotation"        # réponses non conformes au contrat
make ctl ARGS="journal --brut"                      # appels reçus, en JSON complet
make ctl ARGS=reset                                 # vide le journal, oublie les dossiers évalués

# Demandes et base
make reaper                                         # escalade les demandes bloquées
curl localhost:8000/demandes/KAL-26-0101            # statut et fiche d'une demande
docker compose --profile integration exec postgres psql -U kaldera kaldera_test  # inspecter la base
docker compose --profile integration down -v        # vider la base (et tout arrêter)
```

## Layout

- `src/kaldera/` : traitement des demandes
  - `machine.py`, `etat.py`, `orchestrateur.py` : machine à états, état partagé, moteur
  - `agents.py`, `agents_llm.py`, `gardes_fous.py`, `llm.py`, `prompts/` : agents
    déterministes (référence et repli), agents LLM, garde-fous, port LLM, consignes
  - `partenaire.py`, `espace_assure.py`, `regles.py` : client A2A, espace assuré, référentiel métier
  - `ports.py`, `memoire.py`, `postgres.py`, `reaper.py`, `migrations/` : persistance
  - `api.py`, `worker.py`, `ingestion.py`, `ingestion_postgres.py`, `vlm.py` : ingestion des pièces
  - `auth.py`, `vue_assure.py`, `relance.py`, `evenements.py`, `api_assure.py`,
    `assure_postgres.py` : espace assuré (sessions, projection, agent de relance, événements,
    routes `/assure/*`, dépôt PostgreSQL)
- `front/` : espace sinistre de l'assuré (React, Vite, Playwright dans `front/e2e/`)
- `design-system/` : design system de l'interface web
- `tools/` : `generer_pieces.py` (générateur), `seed.py`, `eval_ingestion.py` (épreuve)
- `fixtures/pieces/` : pièces factices générées et leur manifeste (versionnés)
- `eval/scenarios.jsonl`, `eval/scenarios_ingestion.jsonl` : scénarios de recette et d'ingestion
- `external_agent/` : service anti-fraude partenaire simulé et son contrat d'échange (`contrat.md`)
- `scripts/` : pilotage du partenaire simulé et tests de fumée LLM/VLM
- `tests/unit/`, `tests/acceptance/`, `tests/integration/` : tests (l'intégration exige PostgreSQL)
- `tests/e2e/` : serveur de bout en bout (API + worker sur FakeVLM) lancé par Playwright
- `docs/specs_metier.md`, `docs/interface.md` : spécifications fonctionnelles, contrat d'intégration
- `docs/interface_web.md` : espace sinistre de l'assuré (architecture, confidentialité, sécurité)
- `docs/journal_ajustements.md` : ajustements consignés et bornes en vigueur
- `docs/superpowers/` : specs et plans d'implémentation du chantier 1

## Useful commands

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make front-test # Vitest (front)
make front-e2e  # Playwright : parcours complet de l'assuré (démarre PostgreSQL de test)
make down       # arrête les services docker
```

## Known issues

- Le disjoncteur LLM et `make eval` (matrice agent × modèle) relèvent encore du
  chantier 2 (lot C2c) ; les métriques détaillées de l'agent `antifraude` et la
  remesure des bornes, du lot C2b.
- Les chemins réels Azure (agents LLM et VLM) n'ont pas été éprouvés dans
  l'environnement de développement. L'épreuve de l'ingestion avec le vrai VLM
  n'a pas encore été mesurée.
- Le VLM ne lit que la première page des PDF : un contrat de plusieurs pages
  serait mal lu.

## License

Usage interne — tous droits réservés.
