-include .env
export

.PHONY: install up down partenaire scenarios ctl test test-integration reaper api worker fmt lint typecheck generer seed worker-epreuve eval-ingestion epreuve eval fumee-vlm demo-assure front front-test front-e2e recette recette-reset dossier

install:
	uv sync

up:
	docker compose up -d --build

down:
	docker compose down

partenaire:
	uv run python -m external_agent --port 8100

scenarios:
	uv run python -m kaldera.cli eval/scenarios.jsonl $(ARGS)

ctl:
	uv run python scripts/partner_ctl.py $(ARGS)

test:
	uv run pytest -v

TEST_DATABASE_URL ?= postgresql://kaldera:kaldera@localhost:5433/kaldera_test

test-integration:
	docker compose --profile integration up -d --wait postgres
	TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -m integration -v

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src tools/eval_llm.py

reaper:
	uv run python -m kaldera.reaper

api:
	uv run uvicorn kaldera.api:app --port 8000

worker:
	uv run python -m kaldera.worker

generer:
	uv run python tools/generer_pieces.py --seed 42

worker-epreuve:
	PARTENAIRE_URL=http://127.0.0.1:9 uv run python -m kaldera.worker

seed:
	uv run python -m tools.seed

eval-ingestion:
	uv run python -m tools.eval_ingestion

epreuve:
	uv run python -m tools.epreuve

eval:
	uv run python -m tools.eval_llm

fumee-vlm:
	uv run python scripts/fumee_vlm.py

demo-assure:
	uv run python -m tools.demo_assure

front:
	cd front && npm run dev

front-test:
	cd front && npm test

front-e2e:
	docker compose --profile integration up -d --wait postgres
	cd front && npx playwright install chromium && TEST_DATABASE_URL=$(TEST_DATABASE_URL) npx playwright test

# Recette (docs/recette/cahier-recette.pdf) : repart d'une base vide, puis make api, make worker, make front
recette: recette-reset
	docker compose --profile integration up -d --build --wait
	uv run python -m tools.demo_assure

recette-reset:
	docker compose --profile integration down -v

# Dossier de conception (docs/conception/) : pages HTML → PDF A4 paysage (Chromium du front)
dossier:
	node docs/conception/rendre.cjs
