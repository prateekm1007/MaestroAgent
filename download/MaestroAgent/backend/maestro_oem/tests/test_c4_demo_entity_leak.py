"""C4 fix: Remove demo entity names from production code.

Adversarial audit finding (ADVERSARIAL-AUDIT-24PHASE):
> C4: Demo entity names leak into production code. @acme.com appears in
> 14 production files (not just demo_provider.py). Globex/Initech/Hooli
> appear in 10 production modules including evidence.py, situation.py,
> cross_meeting_patterns.py, decision_v2.py.
> Impact: Demo data is not architecturally isolated from production code.
> A real customer's deployment would have Maestro referencing "Globex"
> in its learning logic.

Two categories of fix:
  1. CRITICAL: delivery_intelligence.py hardcodes "acme.com" as the
     internal domain. A real customer's employees would ALL be classified
     as "external" because they don't have @acme.com emails. Fix: make
     the org domain configurable via environment variable.
  2. HIGH: Demo entity names (Globex, Initech, Hooli, @acme.com) in
     docstrings, API examples, and provider sample data. Fix: replace
     with generic placeholders (@example.com per RFC 2606, <customer>,
     <entity>, <email>).

demo_provider.py is EXEMPT — it's the demo seed and is supposed to have
demo data. The audit's concern is production code, not demo fixtures.
"""
from __future__ import annotations

import sys
import os
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class MockSignal:
    def __init__(self, sig_type, actor="", artifact="", metadata=None, timestamp=None, provider="customer"):
        self.type = sig_type
        self.actor = actor
        self.artifact = artifact
        self.metadata = metadata or {}
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.signal_id = f"sig-{artifact or id(self)}"
        self.provider = type("P", (), {"value": provider})()


# ─── 1. delivery_intelligence.py must use configurable org domain ────────

def test_delivery_intelligence_uses_configurable_org_domain():
    """The internal attendee heuristic must NOT hardcode 'acme.com'.

    A real customer with domain 'mycompany.com' must have their employees
    correctly classified as internal — not classified as external because
    they don't have @acme.com emails.
    """
    from maestro_oem.delivery_intelligence import DeliveryIntelligence
    from maestro_oem.calendar_source import CalendarEvent, StaticCalendarSource

    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)

    # Simulate a real customer with domain 'mycompany.com'
    signals = [MockSignal(
        sig_type=type("S", (), {"value": "customer.commitment_made"}),
        actor="jane@mycompany.com",
        metadata={"customer": "TestCorp", "commitment": "Deliver X"},
    )]

    di = DeliveryIntelligence(signals=signals, now=now)

    # The meeting has an internal attendee from mycompany.com
    meeting = CalendarEvent(
        title="TestCorp Review",
        start=tomorrow.replace(hour=10),
        end=tomorrow.replace(hour=11),
        entity="TestCorp",
        attendees=["ceo@testcorp.com", "jane@mycompany.com"],
    )

    delivery = di.compute(entity="TestCorp", meeting=meeting)

    # The recipient must be jane@mycompany.com (the internal attendee),
    # NOT "unknown" (which would happen if acme.com was hardcoded and
    # jane@mycompany.com was classified as external)
    assert delivery["recipient"] == "jane@mycompany.com", \
        f"Recipient must be the internal attendee (jane@mycompany.com), " \
        f"not 'unknown'. Got: {delivery['recipient']!r}. " \
        f"This means the org domain is still hardcoded to acme.com."


def test_delivery_intelligence_org_domain_from_env(monkeypatch):
    """The org domain must be configurable via MAESTRO_ORG_DOMAIN env var."""
    from maestro_oem.delivery_intelligence import DeliveryIntelligence
    from maestro_oem.calendar_source import CalendarEvent

    now = datetime.now(timezone.utc)
    tomorrow = now + timedelta(days=1)

    monkeypatch.setenv("MAESTRO_ORG_DOMAIN", "realcustomer.io")

    signals = [MockSignal(
        sig_type=type("S", (), {"value": "customer.commitment_made"}),
        actor="jane@realcustomer.io",
        metadata={"customer": "TestCorp", "commitment": "Deliver X"},
    )]

    di = DeliveryIntelligence(signals=signals, now=now)

    meeting = CalendarEvent(
        title="TestCorp Review",
        start=tomorrow.replace(hour=10),
        end=tomorrow.replace(hour=11),
        entity="TestCorp",
        attendees=["ceo@testcorp.com", "jane@realcustomer.io"],
    )

    delivery = di.compute(entity="TestCorp", meeting=meeting)
    assert delivery["recipient"] == "jane@realcustomer.io", \
        f"With MAESTRO_ORG_DOMAIN=realcustomer.io, jane@realcustomer.io " \
        f"must be recognized as internal. Got: {delivery['recipient']!r}"


def test_delivery_intelligence_no_hardcoded_acme_in_logic():
    """The delivery_intelligence.py module must NOT contain 'acme.com' as
    a hardcoded domain check in its logic code.

    It may appear in docstrings/comments (as an example), but NOT in
    actual conditional logic (if/split/==/lower checks).
    """
    import maestro_oem.delivery_intelligence as di_module
    import inspect

    source = inspect.getsource(di_module)

    # Find all lines that contain 'acme.com' in non-comment, non-docstring context
    # We look for patterns like: == "acme.com" or .lower() == "acme.com"
    import re
    # Match acme.com in string literals used in comparisons
    hardcoded_patterns = re.findall(r'==\s*["\']acme\.com["\']', source)
    assert len(hardcoded_patterns) == 0, \
        f"delivery_intelligence.py must NOT hardcode 'acme.com' in comparisons. " \
        f"Found: {hardcoded_patterns}"


# ─── 2. No demo entity names in production code logic ─────────────────────

def test_no_acme_com_in_production_logic_files():
    """Production code files (not tests, not demo_provider) must NOT
    contain 'acme.com' in string literals used as logic (comparisons,
    defaults, hardcoded values).

    Docstrings and comments are acceptable (they're documentation).
    String literals in if/==/split contexts are NOT acceptable.
    """
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]

    # Files to check — production code, excluding tests and demo_provider
    excluded = {"test_", "demo_provider", "__pycache__", ".pyc", "conftest"}
    violations = []

    for py_file in backend.rglob("*.py"):
        rel = str(py_file.relative_to(backend))
        if any(excl in rel for excl in excluded):
            continue

        try:
            content = py_file.read_text()
        except Exception:
            continue

        # Check for acme.com in string literals (not comments/docstrings)
        # Simple heuristic: look for "acme.com" or 'acme.com' in code lines
        # that aren't comments (don't start with #)
        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if 'acme.com' in line and ('"' in line or "'" in line):
                # Check if it's in a string literal (not a comment)
                if not stripped.startswith('#'):
                    violations.append(f"{rel}:{i}: {stripped[:100]}")

    # Filter out docstring lines (lines inside """ blocks)
    # This is a heuristic — for a perfect check we'd need AST parsing
    # For now, we accept lines that are clearly in docstrings (indented
    # inside a class/function with """ context)
    real_violations = [v for v in violations if 'acme.com' in v]
    # Filter: provider sample data is acceptable IF it uses @example.com
    # But for now, flag all and let the coder decide

    # The test passes if there are NO acme.com references in production
    # code files (excluding demo_provider.py)
    # We allow it in: demo_provider.py, __init__.py files that are just
    # package markers, and .md files
    real_violations = [
        v for v in real_violations
        if not any(excl in v for excl in ["demo_provider", "__init__"])
    ]

    assert len(real_violations) == 0, \
        f"Production code must not contain 'acme.com' references. " \
        f"Found {len(real_violations)} violations:\n" + "\n".join(real_violations[:10])


def test_no_globex_in_production_logic_files():
    """Production code files (not tests, not demo) must NOT contain
    'Globex' in string literals used as logic."""
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    excluded = {"test_", "demo_provider", "__pycache__", ".pyc", "conftest"}
    violations = []

    for py_file in backend.rglob("*.py"):
        rel = str(py_file.relative_to(backend))
        if any(excl in rel for excl in excluded):
            continue

        try:
            content = py_file.read_text()
        except Exception:
            continue

        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if 'Globex' in line and ('"' in line or "'" in line):
                if not stripped.startswith('#'):
                    violations.append(f"{rel}:{i}: {stripped[:100]}")

    # Filter out docstrings and demo_provider
    real_violations = [
        v for v in violations
        if not any(excl in v for excl in ["demo_provider", "__init__"])
    ]

    # Allow Globex in docstrings (documentation) but not in hardcoded
    # string values used as logic
    # For now, we check for Globex in API examples and hardcoded defaults
    api_example_violations = [v for v in real_violations if 'example' in v.lower() or 'Globex' in v]

    assert len(api_example_violations) == 0, \
        f"Production code must not use 'Globex' in API examples or hardcoded values. " \
        f"Found {len(api_example_violations)} violations:\n" + "\n".join(api_example_violations[:10])
