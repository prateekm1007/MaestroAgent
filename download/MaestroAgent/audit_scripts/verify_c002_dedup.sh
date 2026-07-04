#!/usr/bin/env bash
# verify_c002_dedup.sh — C-002 content-hash dedup wiring verification
# Authority: if this script passes, C-002 is FIXED. If it fails, C-002 is open.
# P20: every add_evidence/add_validation caller must pass content_hash=
# P22: regression test must execute the production path (4 identical signals → 1 LO)
set -euo pipefail
cd "$(git rev-parse --show-toplevel)/download/MaestroAgent/backend"

# Check 1: P20 grep — all callers pass content_hash
TOTAL=$(grep -rn '\.add_evidence(\|\.add_validation(' maestro_oem/ --include='*.py' | grep -v 'def add_' | grep -v 'test_' | grep -v 'intent\.add_evidence\|intent_id' | grep -v '^.*:#' | grep -v 'dedup logic in' | wc -l)
WITH_HASH=$(grep -rn '\.add_evidence(\|\.add_validation(' maestro_oem/ --include='*.py' | grep -v 'def add_' | grep -v 'test_' | grep -v 'intent\.add_evidence\|intent_id' | grep 'content_hash=' | wc -l)
MULTILINE=$(grep -A 2 '\.add_evidence($' maestro_oem/model.py | grep 'content_hash=' | wc -l)
PASSING=$((WITH_HASH + MULTILINE))

if [ "$PASSING" -lt "$TOTAL" ]; then
  echo "FAIL: C-002 P20 — $PASSING/$TOTAL callers pass content_hash (need $TOTAL/$TOTAL)"
  exit 1
fi

# Check 2: P22 — 4 identical signals → 1 LO (production path)
RESULT=$(python3 -c "
import os, uuid
from datetime import datetime, timezone
os.environ['MAESTRO_LOCAL_DEV']='true'; os.environ['MAESTRO_DEMO_SEED']='false'
os.environ['MAESTRO_OEM_STORE_DB']='/tmp/verify_c002.db'
from maestro_oem.engine import OEMEngine
from maestro_oem.signal import SignalType, SignalProvider
class S:
    def __init__(self):
        self.type=SignalType.CUSTOMER_COMMITMENT_MADE; self.actor='jane@acme.com'
        self.artifact='crm:dup'; self.metadata={'customer':'Globex','commitment':'SSO'}
        self.timestamp=datetime.now(timezone.utc); self.signal_id=uuid.uuid4()
        self.provider=SignalProvider.CUSTOMER
e=OEMEngine(); e.ingest([S() for _ in range(4)])
m=e.model
los=[lo for lo in m.learning_objects.values() if lo.evidence_count>0]
print(f'{len(los)}:{los[0].evidence_count}:{len(los[0].content_hashes) if los else 0}')
" 2>/dev/null || echo "ERROR")

LO_COUNT=$(echo "$RESULT" | cut -d: -f1)
EV_COUNT=$(echo "$RESULT" | cut -d: -f2)
CH_COUNT=$(echo "$RESULT" | cut -d: -f3)

if [ "$LO_COUNT" != "1" ] || [ "$EV_COUNT" != "1" ]; then
  echo "FAIL: C-002 P22 — 4 identical signals → $LO_COUNT LO(s) with evidence_count=$EV_COUNT (need 1 LO with evidence_count=1)"
  exit 1
fi

echo "PASS: C-002 — $PASSING/$TOTAL callers pass content_hash; 4 identical signals → 1 LO (evidence_count=$EV_COUNT, content_hashes=$CH_COUNT)"
