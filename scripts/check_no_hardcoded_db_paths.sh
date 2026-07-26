#!/bin/bash
# TICKET-11b: CI check — no hardcoded DB paths outside db_util.py
#
# P70 principle: a principle written down does not retroactively protect code.
# This grep check ENFORCES the "always use default_sqlite_path()" rule.
#
# P66/P70 fix (2026-07-26): the check now also catches:
# - Aliased imports (from pathlib import Path as _P_xxx)
# - Path constructions via __import__("pathlib")
# - Works from any directory (uses find from repo root)
#
# Usage: bash scripts/check_no_hardcoded_db_paths.sh
# Exit code: 0 = pass, 1 = fail

set -e

# Find the repo root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Search for ALL patterns that construct a personal.db path:
# 1. Path(__file__)...personal.db (direct)
# 2. _P_xxx(__file__)...personal.db (aliased)
# 3. __import__("pathlib").Path(__file__)...personal.db (dynamic import)
VIOLATIONS=$(cd "$REPO_ROOT" && grep -rn 'personal\.db' \
  --include="*.py" \
  download/MaestroAgent/maestro-personal/src/maestro_personal_shell/ \
  | grep -v 'db_util.py' \
  | grep -v '# ' \
  | grep -v '"""' \
  | grep -v "MAESTRO_PERSONAL_DB" \
  | grep -iE 'Path\(|__import__.*pathlib|resolve\(\)' \
  2>/dev/null || true)

if [ -n "$VIOLATIONS" ]; then
  echo "❌ TICKET-11b VIOLATION: hardcoded DB path found outside db_util.py"
  echo ""
  echo "Found violations:"
  echo "$VIOLATIONS"
  echo ""
  echo "Fix: replace all hardcoded Path constructions with:"
  echo "  from maestro_personal_shell.db_util import default_sqlite_path"
  echo "  db_path = default_sqlite_path()"
  echo ""
  echo "P70 enforcement: import at MODULE LEVEL, never locally inside functions"
  echo "(local imports cause P66 shadowing — the name becomes local to the"
  echo "entire function, breaking earlier usages)."
  exit 1
fi

echo "✅ TICKET-11b: no hardcoded DB paths outside db_util.py"
exit 0
