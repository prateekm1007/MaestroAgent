# Maestro Personal — Makefile
# Phase 12: test-personal-audit target for clean-clone verification

.PHONY: test-personal-audit test-personal-quick test-mutation test-core hooks

# F2 fix: one-command hook activation for new developers and CI.
# Without this, the pre-commit hook only protects developers who
# manually run `git config core.hooksPath .githooks`. New contributors
# and CI don't get the check. Per P22 (regression = production path),
# the production path for the hook is a new developer's first commit.
hooks:
	git config core.hooksPath .githooks
	@echo "Pre-commit hooks activated (core.hooksPath = .githooks)"
	@echo "Benchmark integrity check will run on scoreboard JSON commits."

# Install exact dependencies and run the full personal test suite
test-personal-audit:
	cd maestro-personal && pip install -q fastapi uvicorn httpx pydantic pytest pytest-asyncio && \
	python -m pytest tests/ -q --tb=short

# Quick test run (skip slow eval tests)
test-personal-quick:
	cd maestro-personal && python -m pytest tests/ -q --tb=short \
	--ignore=tests/test_commitment_eval.py

# Mutation test suite (Phase 12)
test-mutation:
	cd maestro-personal && python -m pytest tests/test_phase12_mutation.py -v -s

# Core regression (Enterprise path unaffected)
test-core:
	cd backend && python -m pytest maestro_cognitive_council/tests/ -q --tb=short

# All tests
test-all: test-personal-audit test-core
