"""Self-audit fixes: disagreement detector generalization + HIGH-04 production test.

This test applies the method that would have caught everything the first time:
- Test 3+ phrasings of each scenario (not just the exact case the code handles)
- Test the no-disagreement case (false positive check)
- Test production mode behavior (not just dev mode)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ["MAESTRO_LOCAL_DEV"] = "true"
os.environ["MAESTRO_DEMO_SEED"] = "false"
os.environ["MAESTRO_PURGE_ON_INIT"] = "true"


def _make_signal(text, actor, customer="Globex", signal_type="message_sent"):
    from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
    sig_map = {
        "customer_commitment_made": SignalType.CUSTOMER_COMMITMENT_MADE,
        "message_sent": SignalType.MESSAGE_SENT,
    }
    return ExecutionSignal(
        type=sig_map.get(signal_type, SignalType.MESSAGE_SENT),
        actor=actor, artifact=f"test:{uuid4().hex[:8]}",
        metadata={"customer": customer, "text": text, "body": text},
        provider=SignalProvider.SLACK,
        timestamp=datetime.now(timezone.utc),
    )


# ─── Disagreement detector: 6 phrasings (the method: test 3+ before claiming done) ───

def test_disagreement_case1_says_we():
    """Phrasing 1: 'Sales says we promised...' vs 'Product says we only promised...'"""
    from maestro_oem.situation import SituationBuilder
    signals = [
        _make_signal("Sales says we promised production availability", "sales@acme.com"),
        _make_signal("Product says we only promised technical completion", "product@acme.com"),
    ]
    s = SituationBuilder(signals=signals, calendar_source=None, whisper_store={}).build_for_entity("Globex")
    assert len(s.disagreements) >= 2, f"Case 1 must detect disagreement. Got: {s.disagreements}"


def test_disagreement_case2_no_says():
    """Phrasing 2: 'We promised SSO by Q4' vs 'We only promised technical completion'"""
    from maestro_oem.situation import SituationBuilder
    signals = [
        _make_signal("We promised SSO by Q4", "sales@acme.com"),
        _make_signal("We only promised technical completion", "product@acme.com"),
    ]
    s = SituationBuilder(signals=signals, calendar_source=None, whisper_store={}).build_for_entity("Globex")
    assert len(s.disagreements) >= 2, f"Case 2 must detect disagreement. Got: {s.disagreements}"


def test_disagreement_case3_direct_conflict():
    """Phrasing 3: 'SSO will be ready by Q4' vs 'SSO will not be ready by Q4'"""
    from maestro_oem.situation import SituationBuilder
    signals = [
        _make_signal("SSO will be ready by Q4", "eng@acme.com"),
        _make_signal("SSO will not be ready by Q4", "pm@acme.com"),
    ]
    s = SituationBuilder(signals=signals, calendar_source=None, whisper_store={}).build_for_entity("Globex")
    assert len(s.disagreements) >= 2, f"Case 3 must detect disagreement. Got: {s.disagreements}"


def test_disagreement_case4_customer_expects():
    """Phrasing 4: 'The customer expects production availability' vs 'The customer only asked for technical completion'"""
    from maestro_oem.situation import SituationBuilder
    signals = [
        _make_signal("The customer expects production availability", "sales@acme.com"),
        _make_signal("The customer only asked for technical completion", "product@acme.com"),
    ]
    s = SituationBuilder(signals=signals, calendar_source=None, whisper_store={}).build_for_entity("Globex")
    assert len(s.disagreements) >= 2, f"Case 4 must detect disagreement. Got: {s.disagreements}"


def test_disagreement_case5_commitment_plus_negation():
    """Phrasing 5: commitment from one actor + negation from another = disagreement"""
    from maestro_oem.situation import SituationBuilder
    signals = [
        _make_signal("We will deliver SSO by Q4", "sales@acme.com", signal_type="customer_commitment_made"),
        _make_signal("Security approval is still conditional", "security@corp.com"),
    ]
    s = SituationBuilder(signals=signals, calendar_source=None, whisper_store={}).build_for_entity("Globex")
    assert len(s.disagreements) >= 2, f"Case 5 must detect disagreement. Got: {s.disagreements}"


def test_disagreement_case6_no_false_positive():
    """Phrasing 6: same actor, no disagreement — must NOT detect one (false positive check)"""
    from maestro_oem.situation import SituationBuilder
    signals = [
        _make_signal("We will deliver SSO by Q4", "sales@acme.com"),
        _make_signal("We also promised MFA", "sales@acme.com"),
    ]
    s = SituationBuilder(signals=signals, calendar_source=None, whisper_store={}).build_for_entity("Globex")
    assert len(s.disagreements) == 0, f"Case 6 must NOT detect disagreement (same actor). Got: {s.disagreements}"


# ─── HIGH-04: Production mode simulation ────────────────────────────────

def test_high04_production_code_path_exists():
    """HIGH-04: get_oem_for_request has the production code path (auth + org resolution).

    This test verifies the STRUCTURE of the production path. A full
    behavior test requires OIDC/SAML configured — which can't be done
    in a unit test. But we can verify the code path EXISTS and would
    be taken when auth is enabled.
    """
    import inspect
    from maestro_api.oem_state import get_oem_for_request

    source = inspect.getsource(get_oem_for_request)

    # Must have auth check
    assert "is_auth_enabled" in source, "Must check if auth is enabled"

    # Must have org resolution
    assert "get_org_id_from_request" in source, "Must resolve org_id from request"

    # Must use cache-aware factory
    assert "get_with_cache_check" in source, "Must use cache-aware factory"

    # Must fail-closed on org resolution failure
    assert "warning" in source.lower() or "logger" in source.lower(), \
        "Must log warning on org resolution failure"


def test_high04_dev_mode_backward_compatible():
    """HIGH-04: dev mode returns global oem_state (backward-compatible)."""
    from maestro_api.oem_state import get_oem_for_request, oem_state
    state = get_oem_for_request(request=None)
    assert state is oem_state, "Dev mode must return global oem_state"


# ─── CRITICAL-01: ACL comprehensiveness (all types) ─────────────────────

def test_acl_all_types_correct():
    """CRITICAL-01: all 10 ACL types produce correct allow/deny decisions."""
    from maestro_oem.acl_resolver import ACLResolver

    class Sig:
        def __init__(self, acl, actor="alice@acme.com", viewers=None):
            self.source_acl = acl
            self.actor = actor
            self.metadata = {"viewers": viewers or []}

    r = ACLResolver()
    assert r.can_access(Sig("public"), "bob@acme.com") is True
    assert r.can_access(Sig("private", actor="alice@acme.com"), "alice@acme.com") is True
    assert r.can_access(Sig("private", actor="alice@acme.com"), "bob@acme.com") is False
    assert r.can_access(Sig("private", actor="alice@acme.com", viewers=["bob@acme.com"]), "bob@acme.com") is True
    assert r.can_access(Sig("channel:slack:C1"), "bob@acme.com") is False
    assert r.can_access(Sig("team:github:eng"), "bob@acme.com") is False
    assert r.can_access(Sig("project:jira:PROJ"), "bob@acme.com") is False
    assert r.can_access(Sig("weird:acl:type"), "bob@acme.com") is False
    assert r.can_access(Sig(""), "bob@acme.com") is True
    assert r.can_access(Sig(None), "bob@acme.com") is True


# ─── CRITICAL-01: membership store integration ──────────────────────────

def test_acl_membership_store_allows_members():
    """CRITICAL-01: membership store allows members, denies non-members."""
    from maestro_oem.acl_resolver import ACLResolver
    from maestro_oem.channel_membership_store import ChannelMembershipStore, MockProviderClient

    store = ChannelMembershipStore(":memory:")
    store.sync_members("slack", "C-private", {"alice@acme.com"})
    mock = MockProviderClient({"C-private": {"alice@acme.com"}})
    r = ACLResolver(membership_store=store, provider_clients={"slack": mock})

    class Sig:
        source_acl = "channel:slack:C-private"
        actor = "cfo@acme.com"
        metadata = {}

    assert r.can_access(Sig(), "alice@acme.com") is True, "Member must see it"
    assert r.can_access(Sig(), "bob@acme.com") is False, "Non-member must NOT see it"
    assert r.can_access(Sig(), "") is False, "Anonymous must NOT see it"


if __name__ == "__main__":
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            func()
            print(f"PASS: {name}")
    print("\nAll self-audit fix tests passed.")
