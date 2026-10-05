# Campus Pulse AI: common commands. Run `make help` for the list.
# Needs: uv (Python), pnpm (Node), Docker (for up/down/logs). Windows: run from Git Bash.

SHELL := bash
.DEFAULT_GOAL := help

UV       ?= uv
PNPM     ?= pnpm
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

install: ## Install API (uv) and web (pnpm) dependencies
	cd $(API) && $(UV) sync --frozen
	cd $(WEB) && $(PNPM) install --frozen-lockfile

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
	cd $(WEB) && $(PNPM) test

lint: lint-api lint-web ## Lint everything

lint-api:
	cd $(API) && $(UV) run ruff check . && $(UV) run ruff format --check .

lint-web:
	cd $(WEB) && $(PNPM) lint

fmt: ## Auto-format and auto-fix (ruff, eslint --fix)
	cd $(API) && $(UV) run ruff format . && $(UV) run ruff check --fix .
	cd $(WEB) && $(PNPM) lint --fix

typecheck: typecheck-api typecheck-web ## Type checks (mypy, tsc)

typecheck-api:
	cd $(API) && $(UV) run mypy

typecheck-web:
	cd $(WEB) && $(PNPM) typecheck

build-web: ## Production build of the web app
	cd $(WEB) && $(PNPM) build

docker-api: ## Build the API image and print its size
	docker build -f infra/Dockerfile -t campus-pulse-api:local $(API)
	docker image ls campus-pulse-api:local

migrate: ## (stub until M2) Run Alembic migrations against DATABASE_URL_MIGRATIONS
	@echo "migrate: no migrations yet. M2 adds them; this target will run:"
	@echo "  cd $(API) && $(UV) run alembic upgrade head"

seed: ## (stub until M2) Load seed/lgu into the dev database
	@echo "seed: seed import scripts arrive in M2 (seed/lgu holds header-only templates)."

eval: ## Run the golden-set evaluation (stub metrics until M2)
	$(PYTHON) eval/run.py

web-dev: ## Next.js dev server on http://localhost:3000
	cd $(WEB) && $(PNPM) dev

api-dev: ## FastAPI dev server with reload on http://localhost:8000
	cd $(API) && $(UV) run uvicorn app.main:app --reload --port 8000
