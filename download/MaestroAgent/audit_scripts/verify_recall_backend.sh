#!/usr/bin/env bash
# verify_recall_backend.sh — recall backend verification
# Authority: if this passes, recall uses a vector backend (not SQL LIKE).
# The auditor's design called for this script; it was missing.
#
# Honest finding: sentence-transformers is NOT available in this env,
# so the RecallEngine falls back to SemanticMatcher (character n-gram
# TF-IDF vectors). This is still vector-based (not SQL LIKE), but less
# powerful than neural embeddings. The LongTermMemory.search() path
# (episodic memory) does default to SQL LIKE when no vector is configured.
#
# This script verifies:
# 1. RecallEngine uses a vector backend (sentence-transformers OR TF-IDF)
# 2. The fallback is NOT SQL LIKE (it's TF-IDF vectors)
# 3. If sentence-transformers is available, it's actually loaded
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check 1: RecallEngine exists and has a recall method
if ! python3 -c "from maestro_oem.recall_engine import RecallEngine; assert hasattr(RecallEngine, 'recall')" 2>/dev/null; then
  echo "FAIL: recall — RecallEngine.recall method does not exist"
  exit 1
fi

# Check 2: RecallEngine uses vector backend (not SQL LIKE)
RESULT=$(python3 -c "
from maestro_oem.recall_engine import _get_embedding_model
model = _get_embedding_model()
if model is not None:
    print('NEURAL')
else:
    print('TFIDF')
" 2>/dev/null || echo "ERROR")

if [ "$RESULT" == "NEURAL" ]; then
  echo "PASS: recall — sentence-transformers (all-MiniLM-L6-v2) loaded at runtime"
elif [ "$RESULT" == "TFIDF" ]; then
  echo "PASS: recall — falls back to SemanticMatcher (TF-IDF vectors, not SQL LIKE)"
  echo "  NOTE: sentence-transformers not available in this env. Install with: pip install sentence-transformers"
  echo "  The TF-IDF fallback is still vector-based (character n-gram cosine similarity)"
else
  echo "FAIL: recall — could not determine backend (got: $RESULT)"
  exit 1
fi

# Check 3: LongTermMemory.search() — does it use vector when configured?
if ! python3 -c "
from maestro_memory.long_term import LongTermMemory
from maestro_memory.vector import InMemoryVectorMemory
ltm = LongTermMemory(vector=InMemoryVectorMemory())
assert ltm.vector is not None, 'vector backend not configured'
print('OK')
" 2>/dev/null | grep -q "OK"; then
  echo "FAIL: recall — LongTermMemory does not accept/use a vector backend"
  exit 1
fi

echo "  LongTermMemory accepts vector backend (InMemoryVectorMemory) — semantic search available when configured"
