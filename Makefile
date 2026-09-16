.DEFAULT_GOAL := help
SHELL := /bin/bash
API := apps/api
WEB := apps/web
PY := $(API)/.venv/bin/python

.PHONY: help setup api web worker seed reset test check lint build up down logs migrate

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies, migrate and seed
	./scripts/dev.sh setup

api: ## Run the API on :8000
	./scripts/dev.sh api

web: ## Run the UI on :5173
	./scripts/dev.sh web

worker: ## Run the background worker
	./scripts/dev.sh worker

migrate: ## Apply database migrations
	cd $(API) && .venv/bin/alembic upgrade head

seed: ## Load demo data
	./scripts/dev.sh seed

reset: ## Drop the database and reseed
	./scripts/dev.sh reset

test: ## Run backend and frontend tests
	./scripts/dev.sh test

check: ## Run the full CI gate locally
	./scripts/dev.sh check

up: ## Start the whole stack in Docker
	docker compose up -d --build
	docker compose run --rm seed

down: ## Stop the stack and remove volumes
	docker compose down -v

logs: ## Tail API logs
	docker compose logs -f api
