# MaestroAgent — Makefile for common commands.
# Usage: make <target>

.PHONY: help dev dev-backend dev-frontend build install update test audit docker-up docker-down docker-logs clean hooks

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
	@echo "  make audit        Run curated critical test suite (W1.6 audit CI command)"
	@echo "  make hooks        Install pre-commit hook (P20 + P6 enforcement)"
	@echo "  make docker-up    Start Docker stack"
	@echo "  make docker-down  Stop Docker stack"
	@echo "  make docker-logs  Follow Docker logs"
	@echo "  make clean        Clean build artifacts"
	@echo ""
	@echo "For browser review: make dev → open http://localhost:8765"

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

audit: ## Run curated critical test suite (W1.6 audit CI command)
	cd backend && MAESTRO_LOCAL_DEV=true MAESTRO_DEMO_SEED=true python -m pytest \
		maestro_oem/tests/test_critical01_delivery_gate_wired.py \
		maestro_oem/tests/test_c1_sqlite_persistence.py \
		maestro_oem/tests/test_c2_epistemic_types.py \
		maestro_oem/tests/test_c3_prompt_injection.py \
		maestro_oem/tests/test_c4_demo_entity_leak.py \
		maestro_oem/tests/test_c5_hardcoded_confidence.py \
		maestro_oem/tests/test_h01_epistemic_classifier_widened.py \
		maestro_oem/tests/test_h05_source_authority.py \
		maestro_oem/tests/test_h06_commitment_extraction.py \
		maestro_oem/tests/test_h1_decorative_precision.py \
		maestro_oem/tests/test_h2_hardcoded_templates.py \
		maestro_oem/tests/test_c2_fallback_path.py \
		maestro_oem/tests/test_c3_learning_loop.py \
		maestro_oem/tests/test_governed_adaptation.py \
		maestro_oem/tests/test_interaction_memory.py \
		maestro_oem/tests/test_content_epistemic_classifier.py \
		maestro_oem/tests/test_llm_narrator.py \
		maestro_oem/tests/test_whisper_prioritization_routing.py \
		maestro_oem/tests/test_phase1_commitment_lifecycle.py \
		maestro_oem/tests/test_phase2_entity_scoping.py \
		maestro_oem/tests/test_phase4_delivery_matrix.py \
		maestro_oem/tests/test_phase5_persistence.py \
		--tb=short -v

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

hooks: ## Install pre-commit hook (P20 call-site + P6 except-pass enforcement)
	@echo "Installing pre-commit hook..."
	@git config core.hooksPath .githooks
	@chmod +x .githooks/pre-commit
	@echo "✓ Pre-commit hook installed (core.hooksPath = .githooks)"
	@echo ""
	@echo "The hook enforces:"
	@echo "  P20: every add_evidence()/add_validation() caller must pass content_hash="
	@echo "  P6:  no bare 'except.*pass' (must have a # comment explaining why)"
	@echo ""
	@echo "Config: .githooks/p20_checks.json (add new function/param pairs here)"
	@echo "Bypass: git commit --no-verify (emergencies only — document WHY in commit message)"
	@echo ""
	@echo "To test: stage a .py file and run: .githooks/pre-commit"
