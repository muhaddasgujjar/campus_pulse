# Campus Pulse AI: common commands. Run `make help` for the list.
# Needs: uv (Python), npm (comes with Node), Docker (for up/down/logs). Windows: run from Git Bash.

SHELL := bash
.DEFAULT_GOAL := help

UV       ?= uv
NPM      ?= npm
PYTHON   ?= python
API      := apps/api
WEB      := apps/web
COMPOSE  := docker compose -f infra/docker-compose.yml
PROFILES ?=
PROFILE_FLAGS := $(foreach p,$(PROFILES),--profile $(p))

.PHONY: help install up down logs test test-api test-web lint lint-api lint-web fmt \
        typecheck typecheck-api typecheck-web build-web docker-api migrate seed eval web-dev api-dev

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install API (uv) and web (npm) dependencies
	cd $(API) && $(UV) sync --frozen
	cd $(WEB) && $(NPM) ci

up: ## Start api + web with Docker Compose (add PROFILES=local-redis for a local Redis)
	$(COMPOSE) $(PROFILE_FLAGS) up --build -d

down: ## Stop all compose services
	$(COMPOSE) --profile local-redis down

logs: ## Follow compose logs
	$(COMPOSE) logs -f --tail=200

test: test-api test-web ## Run all tests (no cloud needed)

test-api: ## API tests (pytest; DB tests skip unless DATABASE_URL is set)
	cd $(API) && $(UV) run pytest

test-web: ## Web smoke tests (vitest)
	cd $(WEB) && $(NPM) run test

lint: lint-api lint-web ## Lint everything

lint-api:
	cd $(API) && $(UV) run ruff check . && $(UV) run ruff format --check .

lint-web:
	cd $(WEB) && $(NPM) run lint

fmt: ## Auto-format and auto-fix (ruff, eslint --fix)
	cd $(API) && $(UV) run ruff format . && $(UV) run ruff check --fix .
	cd $(WEB) && $(NPM) run lint -- --fix

typecheck: typecheck-api typecheck-web ## Type checks (mypy, tsc)

typecheck-api:
	cd $(API) && $(UV) run mypy

typecheck-web:
	cd $(WEB) && $(NPM) run typecheck

build-web: ## Production build of the web app
	cd $(WEB) && $(NPM) run build

docker-api: ## Build the API image and print its size
	docker build -f infra/Dockerfile -t campus-pulse-api:local $(API)
	docker image ls campus-pulse-api:local

migrate: ## Run Alembic migrations against DATABASE_URL_MIGRATIONS (Supabase session pooler)
	cd $(API) && $(UV) run alembic upgrade head

seed: ## Load seed/lgu (idempotent). Uses DATABASE_URL, else a local pgserver database
	cd $(API) && $(UV) run python -m app.cli seed ../../seed/lgu

eval: ## Golden-set evaluation, offline (no LLM, fake embedder). EVAL_ARGS="--live" uses real providers
	cd $(API) && $(UV) run python -m app.evaluation ../../eval/golden.jsonl $(EVAL_ARGS)

web-dev: ## Next.js dev server on http://localhost:3000
	cd $(WEB) && $(NPM) run dev

api-dev: ## FastAPI dev server with reload on http://localhost:8000
	cd $(API) && $(UV) run uvicorn app.main:app --reload --port 8000
