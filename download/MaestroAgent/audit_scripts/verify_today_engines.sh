#!/usr/bin/env bash
# verify_today_engines.sh — behavioral test: do cognitive engines produce output?
# Authority: if this passes, the Today page is cognitively populated. Not just wiring.
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
    r = c.get('/api/personal/today')
    d = r.json()
    engines = ['org_state', 'meta_gap', 'org_pulse', 'curiosity', 'trajectories', 'identity', 'attention']
    populated = sum(1 for e in engines if d.get(e) and (not isinstance(d.get(e), dict) or len(d.get(e)) > 0))
    print(populated)
" 2>&1 | tail -1)

if [ "$RESULT" == "" ] || ! echo "$RESULT" | grep -qE '^[0-9]+$'; then
  echo "FAIL: C-03 — Today script error: $RESULT"
  exit 1
fi

if [ "$RESULT" -lt 5 ]; then
  echo "FAIL: C-03 — Today cognitive engines: $RESULT/7 populated (need ≥5)"
  exit 1
fi

echo "PASS: C-03 — Today cognitive engines: $RESULT/7 populated"
