#!/usr/bin/env bash
# verify_whisper_output.sh — behavioral test: does Whisper actually produce output?
# Authority: if this passes, the product's primary moat works. Not just wiring.
#
# ISSUE: auditor caught that the old script used `2>/dev/null` (hid errors)
# and `TestClient(app)` without context manager (lifespan may not run).
# Fixed: now uses `with TestClient(app) as c:` and surfaces all errors.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

RESULT=$(python3 -c "
import os, tempfile, sys
os.environ['MAESTRO_LOCAL_DEV']='true'
os.environ['MAESTRO_DEMO_SEED']='true'
os.environ['MAESTRO_OEM_STORE_DB']=tempfile.mktemp(suffix='.db')
os.environ['MAESTRO_APP_DIR']=os.path.dirname(os.getcwd())
from fastapi.testclient import TestClient
from maestro_api.main import create_app
app = create_app(db_path=':memory:')
# Auditor fix: use context manager so lifespan runs (triggers init + demo seed)
with TestClient(app) as c:
    r = c.get('/api/oem/whisper?entity=Globex&context=morning+brief')
    d = r.json()
    print(len(d.get('whispers', [])))
" 2>&1 | tail -1)

if [ "$RESULT" == "0" ] || [ "$RESULT" == "" ]; then
  echo "FAIL: C-01 — Whisper produces 0 output for Globex (primary moat broken)"
  exit 1
fi

# Check if RESULT is a number
if ! echo "$RESULT" | grep -qE '^[0-9]+$'; then
  echo "FAIL: C-01 — Whisper script error: $RESULT"
  exit 1
fi

echo "PASS: C-01 — Whisper produces $RESULT whisper(s) for Globex"
