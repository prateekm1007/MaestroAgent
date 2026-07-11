# Maestro Personal — Makefile
# Phase 12: test-personal-audit target for clean-clone verification

.PHONY: test-personal-audit test-personal-quick test-mutation test-core

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
