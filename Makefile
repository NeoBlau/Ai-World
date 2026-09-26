# AI WORLD — developer commands
COMPOSE ?= docker compose

.PHONY: dev up build down test test-backend test-frontend test-e2e migrate seed reset logs lint ps

dev: ## Start the whole stack (build if needed) and follow logs
	$(COMPOSE) up --build

up: ## Start in the background
	$(COMPOSE) up --build -d

build: ## Build all images
	$(COMPOSE) build

down: ## Stop everything
	$(COMPOSE) down

test: test-backend test-frontend ## Run backend + frontend tests

test-backend: ## pytest inside the backend image (uses a separate test database)
	$(COMPOSE) up -d postgres redis
	$(COMPOSE) run --rm --no-deps -e TEST_DATABASE_URL=postgresql+asyncpg://aiworld:aiworld@postgres:5432/aiworld_test migrate \
		sh -c "python scripts/create_test_db.py && pytest -q"

test-frontend: ## Type-check + Vitest
	cd frontend && npm ci --no-audit --no-fund && npm run lint && npm test

test-e2e: ## Playwright against a running stack (make up first)
	cd frontend && npx playwright test

migrate: ## Apply database migrations
	$(COMPOSE) run --rm migrate alembic upgrade head

seed: ## Seed demo world (idempotent)
	$(COMPOSE) run --rm migrate python -m app.world.seed

reset: ## Wipe world data and reseed
	$(COMPOSE) run --rm migrate python -m app.world.seed --reset

logs: ## Follow logs of backend and worker
	$(COMPOSE) logs -f backend worker

lint:
	cd backend && ruff check app tests
	cd frontend && npm run lint

ps:
	$(COMPOSE) ps
