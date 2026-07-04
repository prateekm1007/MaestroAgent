#!/usr/bin/env bash
# verify_c6_persistence.sh — C6 OEM persistence verification
# Authority: if this passes, C6 is FIXED. _save_model_state must be called
# from demo seed + shutdown, and laws must survive a restart cycle.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check 1: _save_model_state called from _seed_from_demo_provider
if ! grep -q "_save_model_state" maestro_api/oem_state.py; then
  echo "FAIL: C6 — _save_model_state not in oem_state.py"
  exit 1
fi

# Check 2: _save_model_state called from lifespan shutdown
if ! grep -q "_save_model_state" maestro_api/main.py; then
  echo "FAIL: C6 — _save_model_state not in main.py (shutdown)"
  exit 1
fi

# Check 3: restart cycle — laws survive
RESULT=$(python3 -c "
import os, tempfile
from pathlib import Path
tmpdir = tempfile.mkdtemp()
store_db = str(Path(tmpdir) / 'oem_store.db')
os.environ['MAESTRO_LOCAL_DEV']='true'; os.environ['MAESTRO_DEMO_SEED']='true'
os.environ['MAESTRO_ENV']='development'; os.environ['MAESTRO_OEM_STORE_DB']=store_db
from maestro_api.oem_state import OEMState
s1 = OEMState(); s1.initialize()
laws1 = len(s1.engine.get_model().laws)
os.environ['MAESTRO_DEMO_SEED'] = 'false'
s2 = OEMState(); s2.initialize()
laws2 = len(s2.engine.get_model().laws)
print(f'{laws1}:{laws2}')
" 2>/dev/null || echo "0:0")

LAWS_BEFORE=$(echo "$RESULT" | cut -d: -f1)
LAWS_AFTER=$(echo "$RESULT" | cut -d: -f2)

if [ "$LAWS_BEFORE" -eq 0 ]; then
  echo "FAIL: C6 — demo seed produced 0 laws (test setup failed)"
  exit 1
fi

if [ "$LAWS_AFTER" -eq 0 ]; then
  echo "FAIL: C6 — after restart, laws=0 (was $LAWS_BEFORE before). _save_model_state not called from demo seed."
  exit 1
fi

echo "PASS: C6 — laws survive restart ($LAWS_BEFORE → $LAWS_AFTER); _save_model_state in demo seed + shutdown"
