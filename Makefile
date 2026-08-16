COMPOSE := docker compose -f infra/docker/docker-compose.yml
PY      := cd backend &&

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# -------------------------------------------------------------------- docker
.PHONY: up down logs ps reset
up: ## Start the development stack
	$(COMPOSE) up -d --build

down: ## Stop the stack
	$(COMPOSE) down

logs: ## Follow API logs
	$(COMPOSE) logs -f api

ps: ## Show service status
	$(COMPOSE) ps

reset: ## Destroy volumes and start clean (deletes all local data)
	$(COMPOSE) down -v && $(COMPOSE) up -d --build

# ------------------------------------------------------------------- backend
.PHONY: install migrate revision test smoke lint fmt types check
install: ## Install backend dependencies
	$(PY) pip install -e ".[dev]"

migrate: ## Apply migrations
	$(PY) alembic upgrade head

revision: ## Create a migration: make revision m="add x"
	$(PY) alembic revision --autogenerate -m "$(m)"

test: ## Run the test suite
	$(PY) pytest

smoke: ## Run the end-to-end smoke test only
	$(PY) pytest -m smoke

lint: ## Lint
	$(PY) ruff check app tests

fmt: ## Format
	$(PY) ruff check --fix app tests && ruff format app tests

types: ## Type check
	$(PY) mypy app

check: lint types test ## Everything CI runs

# ------------------------------------------------------------------ frontend
.PHONY: web web-build web-types
web: ## Run the frontend dev server
	cd frontend && npm run dev

web-build: ## Production build
	cd frontend && npm run build

web-types: ## Type check the frontend
	cd frontend && npm run typecheck
