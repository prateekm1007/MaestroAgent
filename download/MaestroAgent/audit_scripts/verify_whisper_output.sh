#!/usr/bin/env bash
# verify_whisper_output.sh — behavioral test: does Whisper actually produce output?
# Authority: if this passes, the product's primary moat works. Not just wiring.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

RESULT=$(python3 -c "
import os, tempfile
os.environ['MAESTRO_LOCAL_DEV']='true'
os.environ['MAESTRO_DEMO_SEED']='true'
os.environ['MAESTRO_OEM_STORE_DB']=tempfile.mktemp(suffix='.db')
os.environ['MAESTRO_APP_DIR']=os.path.dirname(os.getcwd())
from fastapi.testclient import TestClient
from maestro_api.main import create_app
app = create_app(db_path=':memory:')
c = TestClient(app)
r = c.get('/api/oem/whisper?entity=Globex&context=morning+brief')
d = r.json()
print(len(d.get('whispers', [])))
" 2>/dev/null || echo "ERROR")

if [ "$RESULT" == "ERROR" ] || [ "$RESULT" == "0" ]; then
  echo "FAIL: C-01 — Whisper produces 0 output for Globex (primary moat broken)"
  exit 1
fi

echo "PASS: C-01 — Whisper produces $RESULT whisper(s) for Globex"
