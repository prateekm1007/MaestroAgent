#!/bin/bash
# TICKET-11b: CI check — no hardcoded DB paths outside db_util.py
#
# P70 principle: a principle written down does not retroactively protect code.
# This grep check ENFORCES the "always use default_sqlite_path()" rule.
#
# Usage: bash scripts/check_no_hardcoded_db_paths.sh
# Exit code: 0 = pass (no violations), 1 = fail (violations found)

set -e

# Search for hardcoded Path(__file__) / "personal.db" patterns
# in all .py files EXCEPT db_util.py (which defines default_sqlite_path)
VIOLATIONS=$(grep -rn 'Path(__file__).*personal\.db' \
  --include="*.py" \
  download/MaestroAgent/maestro-personal/src/maestro_personal_shell/ \
  | grep -v 'db_util.py' \
  | grep -v '# code used Path' \
  | grep -v '# comment' \
  2>/dev/null || true)

if [ -n "$VIOLATIONS" ]; then
  echo "❌ TICKET-11b VIOLATION: hardcoded DB path found outside db_util.py"
  echo ""
  echo "Found violations:"
  echo "$VIOLATIONS"
  echo ""
  echo "Fix: replace all hardcoded Path(__file__)...personal.db with"
  echo "  from maestro_personal_shell.db_util import default_sqlite_path"
  echo "  db_path = default_sqlite_path()"
  echo ""
  echo "This is P70 enforcement: a principle in a governance file does not"
  echo "protect code — a grep-able CI check does."
  exit 1
fi

echo "✅ TICKET-11b: no hardcoded DB paths outside db_util.py"
exit 0
