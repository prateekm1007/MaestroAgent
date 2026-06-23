# MaestroAgent — Makefile for common commands.
# Usage: make <target>

.PHONY: help dev dev-backend dev-frontend build install update test docker-up docker-down docker-logs clean

help: ## Show this help
	@echo "MaestroAgent — common commands:"
	@echo ""
	@echo "  make dev          Start backend + frontend in dev mode (fastest for browser review)"
	@echo "  make dev-backend  Start backend only"
	@echo "  make dev-frontend Start frontend only"
	@echo "  make build        Build the frontend PWA bundle"
	@echo "  make install      Docker self-host install (production)"
	@echo "  make update       Docker update (zero downtime)"
	@echo "  make test         Run e2e smoke tests"
	@echo "  make docker-up    Start Docker stack"
	@echo "  make docker-down  Stop Docker stack"
	@echo "  make docker-logs  Follow Docker logs"
	@echo "  make clean        Clean build artifacts"
	@echo ""
	@echo "For browser review: make dev → open http://localhost:1420"

dev: ## Start backend + frontend in dev mode
	./dev.sh both

dev-backend: ## Start backend only
	./dev.sh backend

dev-frontend: ## Start frontend only
	./dev.sh frontend

build: ## Build the frontend PWA bundle
	cd frontend && pnpm install && pnpm build

install: ## Docker self-host install
	./install.sh

update: ## Docker update
	./update.sh

test: ## Run e2e smoke tests
	./test_e2e.sh

docker-up: ## Start Docker stack
	docker compose up -d --build

docker-down: ## Stop Docker stack
	docker compose down

docker-logs: ## Follow Docker logs
	docker compose logs -f

clean: ## Clean build artifacts
	rm -rf frontend/dist frontend/node_modules backend/.venv backend/build backend/dist
	rm -rf .maestro maestro.db
	@echo "Cleaned. Run 'make dev' or 'make install' to start fresh."
