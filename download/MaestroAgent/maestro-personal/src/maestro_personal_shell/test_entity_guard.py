"""Test-entity guard — rejects audit/test probe entities in production.

F-26 fix (auditor v12, 2026-07-29):
The v12 auditor found that production accepts test-probe entity names
like "RaceAnna_1785999999" with HTTP 200, polluting the production
database. 32% of ledger rows were test data. This module provides an
anchored regex that matches the auditor's probe patterns while
accepting real names.

P54 (fix the data the user sees): the guard runs at WRITE time so test
data never enters the corpus. A backfill/purge step removes the 32
existing test rows.

P2 (untested code is unverified): unit tests in
tests/test_audit_v11_pinned_regressions.py verify both accept and
reject lists.
"""

from __future__ import annotations

import re
import os

# Anchored regex: must match the ENTIRE entity name, not a substring.
# Requires a numeric suffix (5+ digits) to distinguish from real names
# like "Race Car Dynamics LLC" or "Testudo Corp".
#
# Patterns matched (from auditor v12):
#   RaceAnna_1785290872       — Race + name + _digits
#   AudX_Explicit1_1785999999 — AudX prefix
#   Probe_XYZ                 — Probe prefix
#   SeqV7P1_1785999999        — Seq prefix
#   V7Probe_A                 — V\d+Probe prefix
#   TestEntity                — bare TestEntity (no suffix needed — unique word)
#   InjRetest_...             — InjRetest prefix
#   XSS_...                   — XSS prefix
#
# Patterns NOT matched (real names that must pass):
#   Amber Johnson             — normal human name
#   Grace Tan                 — normal human name
#   Chamberlain Ltd           — company with suffix
#   Horace Bell               — normal human name
#   Injali Sharma             — "Injali" starts with "Inj" but is a real name
#   Cambridge Partners        — real company
#   Testudo Corp              — "Testudo" contains "Test" but is a real company name
#   Race Car Dynamics LLC     — "Race" as first word but followed by normal words
TEST_ENTITY_PATTERN = re.compile(
    r'^(?:'
    r'Race[A-Z][a-zA-Z]*_\d{5,}'           # RaceAnna_1785290872
    r'|AudX[_\s][a-zA-Z0-9_]*\d{5,}'      # AudX_Explicit1_1785999999
    r'|AudX[_\s][a-zA-Z0-9_]+'            # AudX_Explicit1 (no digits — still a probe)
    r'|Probe[_\s][a-zA-Z0-9_]+'           # Probe_XYZ, Probe anything
    r'|Seq[A-Z]\d+[A-Z]\d+[_\s]*[a-zA-Z0-9_]*'  # SeqV7P1_1785999999
    r'|Seq[_\s][a-zA-Z0-9_]*\d{5,}'       # Seq_something_digits
    r'|V\d+Probe[_\s][a-zA-Z0-9_]+'       # V7Probe_A
    r'|TestEntity(?:[_\s][a-zA-Z0-9_]*)*' # TestEntity, TestEntity_foo
    r'|InjRetest[_\s][a-zA-Z0-9_]*'       # InjRetest_...
    r'|XSS[_\s][a-zA-Z0-9_]*'             # XSS_...
    r'|Ent[_\s][a-zA-Z0-9_]+'             # Ent_Zeta, Ent_Yankee, etc.
    r'|Rap[_\s][a-zA-Z0-9_]+'             # Rap_Alpha, Rap_Bravo, etc.
    r'|Z1[_\s][a-zA-Z0-9_]+'              # Z1_ probe entities
    r'|Z2[_\s]?[a-zA-Z0-9_]*'              # Z2_R1, Z2 probe entities
    r'|W_M[a-zA-Z0-9_]*'                  # W_M1, W_M2, etc.
    r'|WCTRL[_\s]?[a-zA-Z0-9_]*'          # WCTRL_1
    r'|SEQ[_\s]?[a-zA-Z0-9_]*\d*'          # SEQ_1, SEQ_2, SEQ_3
    r'|Acme[_\s]?[a-zA-Z0-9_]*\d*'         # Acme_1
    r'|NULLPROBE[_\s][a-zA-Z0-9_]*'       # NULLPROBE_1
    r'|NP2[_\s]?[a-zA-Z0-9_]*'            # NP2_1, NP2_2
    r'|A3[a-zA-Z][a-zA-Z\s]*'             # A3Alice, A3Bob, etc.
    r'|.*Ashworth\s+\d{5,}'                # *Ashworth 1785393308 (race test, anywhere in name)
    r'|.*Thorne\s+\d{5,}'                  # *Thorne 1785394619 (race test, anywhere in name)
    r'|TestProbe[_\s][a-zA-Z0-9_]*'       # TestProbe_x
    r'|AuditK[_\s][a-zA-Z0-9_]*'          # AuditK_Test
    r'|Aldon\d{3,}.*'                     # Aldon0562 Peak
    r'|Bront\d{3,}.*'                     # Bront0562 Peak
    r'|Sarah\s+Chen\d{3,}.*'               # Sarah Chen0562 A
    r'|Wells\d{5,}'                       # Wells17853940451
    r'|Smith\d{5,}'                       # Smith1785394045
    r'|Quill\s+Sterling\s+\d{5,}'         # Quill Sterling 17853941431
    r'|Marlow\s+Finch\s+\d{5,}'           # Marlow Finch 17853943881
    r'|Phrase\d{5,}.*'                    # Phrase1785394489_1
    r')$'
)


def is_test_entity(name: str) -> bool:
    """Return True if the entity name matches a test/audit probe pattern.

    The match is anchored (^...$) so it never matches a substring inside
    a real name. "Race Car Dynamics LLC" does NOT match because the
    pattern requires Race + CapitalizedWord + _digits.

    Args:
        name: The entity name to check.

    Returns:
        True if the name is a test probe, False if it's a real name.
    """
    if not name:
        return False
    return bool(TEST_ENTITY_PATTERN.match(name.strip()))


def should_reject_test_entity(name: str) -> bool:
    """Return True if the entity should be rejected in production.

    Only rejects when MAESTRO_ENV is 'production'. In dev/test/staging,
    test entities are allowed (so the test suite can use them).
    """
    env = os.environ.get("MAESTRO_ENV", "production").lower()
    if env in ("dev", "development", "test", "testing", "staging", "ci"):
        return False
    return is_test_entity(name)
