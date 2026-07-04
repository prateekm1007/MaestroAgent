#!/usr/bin/env bash
# verify_c7_admin_cli.sh — C7 admin bootstrap CLI verification
# Authority: if this passes, C7 is FIXED. `maestro create-admin` must exist.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check: create-admin command exists in the CLI
if ! grep -q 'create-admin' maestro_cli/main.py; then
  echo "FAIL: C7 — create-admin command not in maestro_cli/main.py"
  exit 1
fi

# Check: the test passes
if ! python3 -m pytest maestro_cli/tests/test_c7_create_admin.py -q --tb=line 2>/dev/null | grep -q "3 passed"; then
  echo "FAIL: C7 — test_c7_create_admin.py does not pass (3/3 expected)"
  exit 1
fi

echo "PASS: C7 — maestro create-admin command exists; 3/3 tests pass"
