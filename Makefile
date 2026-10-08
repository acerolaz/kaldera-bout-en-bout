-include .env
export

.PHONY: install up down partenaire scenarios ctl test test-integration reaper api worker fmt lint typecheck

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
	uv run mypy src

reaper:
	uv run python -m kaldera.reaper

api:
	uv run uvicorn kaldera.api:app --port 8000

worker:
	uv run python -m kaldera.worker
