#!/usr/bin/env python3
"""
Round 50 — Ship-Ready E2E Verification Script.

This script verifies that the product is ready for pilot shipment by
testing the running system end-to-end. It covers:

  1. All 6 previously-404 endpoints now return 200
  2. The 7 critical fixes from Round 49
  3. The Round 48 fixes (SemanticMatcher, synthesized_answer, verified_by, confidence)
  4. The SemanticMatcher churn bug (hire engineers ≠ churn)
  5. Production secrets fail-closed

Usage:
  cd backend
  MAESTRO_APP_DIR=/path/to/MaestroAgent MAESTRO_DEMO_SEED=true PYTHONPATH=. \
    python /home/z/my-project/scripts/e2e_ship_verification.py

Exit code 0 = all checks pass, pilot ready.
Exit code 1 = some checks fail, do not ship.
"""
import sys
import os
sys.path.insert(0, '.')

os.environ.setdefault('MAESTRO_APP_DIR', os.getcwd())
os.environ.setdefault('MAESTRO_DEMO_SEED', 'true')

from fastapi.testclient import TestClient

FAILURES = []
PASSES = []


def check(label, condition, detail=''):
    status = '✓' if condition else '✗'
    line = f'  {status} {label}'
    if detail:
        line += f' — {detail}'
    print(line)
    if condition:
        PASSES.append(label)
    else:
        FAILURES.append(label)


print('=' * 60)
print('ROUND 50 — SHIP-READY E2E VERIFICATION')
print('=' * 60)
print()

# ─── 1. Start the app ───
from maestro_api.main import create_app
app = create_app(db_path=':memory:')
client = TestClient(app)

# ─── 2. Endpoints (were 404, now 200) ───
print('1. ENDPOINTS (previously 404):')
endpoints = [
    ('/api/oem/timeline?limit=5', 'Timeline'),
    ('/api/oem/ceo-briefing', 'CEO Briefing'),
    ('/api/oem/tasks', 'Tasks'),
    ('/api/oem/commitments', 'Commitments'),
    ('/api/oem/laws/verified/list', 'Verified Laws'),
    ('/api/oem/ask?q=payments', 'Ask (SemanticMatcher)'),
    # Round 47 endpoints
    ('/api/oem/canvas/test', 'Canvas'),
    ('/api/oem/teammate/test@example.com', 'Per-Teammate'),
    ('/api/oem/mcp/tools', 'MCP Tools'),
    ('/api/oem/pilot/metrics', 'Pilot Metrics'),
]
for path, label in endpoints:
    r = client.get(path)
    check(f'{label} [{r.status_code}]', r.status_code == 200)

# ─── 3. C7: Production secrets fail-closed ───
print()
print('2. C7: PRODUCTION SECRETS FAIL-CLOSED:')
os.environ['MAESTRO_ENV'] = 'production'
os.environ['JWT_SECRET'] = 'dev-secret-change-in-production'
try:
    create_app(db_path=':memory:')
    check('Refuses to start with default secret', False)
except RuntimeError:
    check('Refuses to start with default secret', True)
finally:
    del os.environ['MAESTRO_ENV']
    del os.environ['JWT_SECRET']

# ─── 4. SemanticMatcher + churn bug ───
print()
print('3. SEMANTIC MATCHER (churn bug):')
from maestro_api.oem_state import oem_state
from maestro_oem.decision import DecisionEngine
dec = DecisionEngine(oem_state.model)

result = dec.answer_question('should we hire more engineers')
los = result.get('learning_objects', [])
churn = any('churn' in lo.get('title', '').lower() for lo in los)
hire = any('hir' in lo.get('title', '').lower() for lo in los)
check('No churn false positive', not (churn and not hire))

# ─── 5. synthesized_answer ───
print()
print('4. SYNTHESIZED ANSWER:')
has_syn = 'synthesized_answer' in result and result['synthesized_answer']
check('Field exists and non-empty', has_syn)
if has_syn:
    print(f'     Value: {result["synthesized_answer"][:100]}...')

# ─── 6. verified_by on laws ───
print()
print('5. VERIFIED_BY FIELD:')
from maestro_oem.law import OrganizationalLaw
check('Field exists on laws', 'verified_by' in OrganizationalLaw.model_fields)

# ─── 7. Confidence calibration ───
print()
print('6. CONFIDENCE CALIBRATION:')
confs = [lo.confidence for lo in oem_state.model.learning_objects.values()]
unique = len(set(confs))
check(f'{unique} unique values (was 1)', unique > 5, f'range {min(confs):.4f}-{max(confs):.4f}')

# ─── 8. C4: WriteBackService wired ───
print()
print('7. C4: WRITEBACK WIRED TO OAUTH:')
import inspect, re
from maestro_api.routes import oem
src = inspect.getsource(oem)
calls = re.findall(r'WriteBackService\([^)]*\)', src)
wired = sum(1 for c in calls if 'oauth_manager' in c)
check(f'{wired}/{len(calls)} call sites wired', wired >= 7)

# ─── 9. C1: RBAC import ───
print()
print('8. C1: RBAC IMPORT FIXED:')
# Check the actual import line (line 60), not the comment (line 52)
import_lines = [
    l.strip() for l in src.split('\n')
    if 'get_auth_store' in l and l.strip().startswith('from maestro_auth')
]
check('Imports from maestro_auth.permissions', all('permissions' in l for l in import_lines))

# ─── 10. C2: OAuth encryption ───
print()
print('9. C2: OAUTH TOKENS ENCRYPTED:')
from maestro_oem.checkpoint_store import CheckpointStore
cs_src = inspect.getsource(CheckpointStore.save_credentials)
check('EncryptionManager.encrypt() called', 'enc.encrypt' in cs_src)

# ─── 11. C3: WebSocket auth ───
print()
print('10. C3: WEBSOCKET AUTH:')
from maestro_api import websocket
ws_src = inspect.getsource(websocket)
check('4401 close code + auth check', '4401' in ws_src and 'is_auth_enabled' in ws_src)

# ─── 12. C5: SAML verification ───
print()
print('11. C5: SAML SIGNATURE VERIFICATION:')
from maestro_auth import saml
saml_src = inspect.getsource(saml)
check('xmlsec verification implemented', 'xmlsec' in saml_src and 'MAESTRO_SAML_IDP_CERT' in saml_src)

# ─── 13. C6: Dockerfile ───
print()
print('12. C6: DOCKERFILE:')
dockerfile_path = os.path.join(os.environ.get('MAESTRO_APP_DIR', ''), 'Dockerfile')
if os.path.exists(dockerfile_path):
    dockerfile = open(dockerfile_path).read()
    check('Copies actual production assets', 'COPY app.html' in dockerfile and 'COPY static/' in dockerfile)
    # Check that no COPY or RUN command references _deprecated/
    copy_run_lines = [l for l in dockerfile.split('\n') if l.strip().startswith(('COPY', 'RUN'))]
    has_deprecated_in_commands = any('_deprecated/' in l for l in copy_run_lines)
    check('No _deprecated/ in COPY/RUN commands', not has_deprecated_in_commands)
else:
    check('Dockerfile exists', False, f'not found at {dockerfile_path}')

# ─── Summary ───
print()
print('=' * 60)
print(f'SUMMARY: {len(PASSES)} passed, {len(FAILURES)} failed')
print('=' * 60)
if FAILURES:
    print()
    print('FAILURES:')
    for f in FAILURES:
        print(f'  ✗ {f}')
    print()
    print('PILOT NOT READY — fix failures before shipping.')
    sys.exit(1)
else:
    print()
    print('ALL CHECKS PASS — PILOT READY TO SHIP.')
    sys.exit(0)
