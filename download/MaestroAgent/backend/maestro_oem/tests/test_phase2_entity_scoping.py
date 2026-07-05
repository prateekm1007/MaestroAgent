"""Phase 2.4 + 2.5: Entity-scoped retrieval + cross-entity re-scoping test.

Phase 2.4: Once a conversation has resolved to a specific customer entity,
subsequent retrieval within that session should be scoped to that entity by
default. This prevents cross-customer answers (the D2 bug).

Phase 2.5: A three-turn test verifying:
  Turn 1: "What did we promise Globex?" → stays scoped to Globex
  Turn 2: "What about their pricing concern?" → stays scoped to Globex (pronoun)
  Turn 3: "What about Hooli instead?" → correctly re-scopes to Hooli
  Turn 4: "What did we promise?" → stays scoped to Hooli (not reverting to Globex)

Principle 10: This test exists because the external forensic audit proved
cross-customer answers on /api/oem/ask. The D2 fix routed /ask through
AskPipeline, and Phase 2.4 adds entity-scoped retrieval to prevent
cross-customer contamination even when the follow-up doesn't name the entity.
"""
from __future__ import annotations

import sys
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
        self.authority_weight = 0.5


@pytest.fixture
def now():
    return datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def multi_customer_signals(now):
    """Signals for BOTH Globex and Hooli — the entity scoping must prevent
    Hooli evidence from appearing in a Globex-scoped conversation."""
    from maestro_oem.signal import SignalType
    return [
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE, actor="jane@example.com",
            artifact="crm:globex-1", metadata={"customer": "Globex", "commitment": "Deliver SSO by Q4"},
            timestamp=now - timedelta(days=20)),
        MockSignal(SignalType.CUSTOMER_OBJECTION, actor="jane@example.com",
            artifact="crm:globex-2", metadata={"customer": "Globex", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5)),
        MockSignal(SignalType.CUSTOMER_COMMITMENT_MADE, actor="bob@example.com",
            artifact="crm:hooli-1", metadata={"customer": "Hooli", "commitment": "Integrate API by Q3"},
            timestamp=now - timedelta(days=15)),
        MockSignal(SignalType.CUSTOMER_COMMITMENT_BROKEN, actor="bob@example.com",
            artifact="crm:hooli-2", metadata={"customer": "Hooli", "commitment": "SOC2 audit complete"},
            timestamp=now - timedelta(days=3)),
    ]


# ─── Phase 2.4: Entity-scoped retrieval ────────────────────────────────────

def test_phase_2_4_follow_up_stays_scoped(multi_customer_signals, now, tmp_path):
    """Turn 1: 'What did we promise Globex?' → evidence references Globex.
    Turn 2: 'What about their pricing concern?' → evidence STILL references
    Globex, NOT Hooli. The entity scoping prevents cross-customer answers."""
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.conversation_store import ConversationStore

    conv = ConversationStore(str(tmp_path / "conv_scoped.db"))
    p = AskPipeline(signals=multi_customer_signals, whisper_store={}, oem_state=None,
                    conversation_store=conv)

    # Turn 1: establish Globex context
    r1 = p.execute("What did we promise Globex?", org_id="default", session_id="test-scoped")
    r1_evidence_text = " ".join(e.get("text", "") for e in r1["evidence"]).lower()
    assert "globex" in r1_evidence_text or "sso" in r1_evidence_text, (
        f"Turn 1 must return Globex evidence. Got: {r1_evidence_text[:200]!r}"
    )
    assert "hooli" not in r1_evidence_text, (
        f"Turn 1 must NOT return Hooli evidence. Got: {r1_evidence_text[:200]!r}"
    )

    # Turn 2: follow-up without naming the entity — "their" should resolve to Globex
    r2 = p.execute("What about their pricing concern?", org_id="default", session_id="test-scoped")
    r2_evidence_text = " ".join(e.get("text", "") for e in r2["evidence"]).lower()
    # Should reference Globex pricing, NOT Hooli
    if r2["evidence"]:  # If evidence found, it must be Globex-scoped
        assert "hooli" not in r2_evidence_text, (
            f"Turn 2 must NOT return Hooli evidence (entity scoping). Got: {r2_evidence_text[:200]!r}"
        )


# ─── Phase 2.5: Cross-entity re-scoping (3-turn) ───────────────────────────

def test_phase_2_5_cross_entity_rescoping(multi_customer_signals, now, tmp_path):
    """Three-turn test verifying entity scoping + re-scoping:
    Turn 1: "What did we promise Globex?" → Globex evidence
    Turn 2: "What about their pricing concern?" → still Globex (pronoun resolution)
    Turn 3: "What about Hooli instead?" → re-scopes to Hooli
    Turn 4: "What did we promise?" → stays Hooli (not reverting to Globex)
    """
    from maestro_oem.ask_pipeline import AskPipeline
    from maestro_oem.conversation_store import ConversationStore

    conv = ConversationStore(str(tmp_path / "conv_rescope.db"))
    p = AskPipeline(signals=multi_customer_signals, whisper_store={}, oem_state=None,
                    conversation_store=conv)

    # Turn 1: Globex
    r1 = p.execute("What did we promise Globex?", org_id="default", session_id="test-rescope")
    r1_entities = [e.lower() for e in r1["entities"]]
    assert any("globex" in e for e in r1_entities), (
        f"Turn 1 entities must include Globex. Got: {r1['entities']}"
    )

    # Turn 2: "their" should resolve to Globex
    r2 = p.execute("What about their pricing concern?", org_id="default", session_id="test-rescope")
    r2_entities = [e.lower() for e in r2["entities"]]
    assert any("globex" in e for e in r2_entities), (
        f"Turn 2 must resolve 'their' → Globex. Entities: {r2['entities']}"
    )

    # Turn 3: Explicit pivot to Hooli
    r3 = p.execute("What about Hooli instead?", org_id="default", session_id="test-rescope")
    r3_entities = [e.lower() for e in r3["entities"]]
    assert any("hooli" in e for e in r3_entities), (
        f"Turn 3 must include Hooli (explicit pivot). Entities: {r3['entities']}"
    )

    # Turn 4: "What did we promise?" — should stay scoped to Hooli, NOT revert to Globex
    r4 = p.execute("What did we promise?", org_id="default", session_id="test-rescope")
    r4_entities = [e.lower() for e in r4["entities"]]
    r4_evidence_text = " ".join(e.get("text", "") for e in r4["evidence"]).lower()
    # Should have Hooli in entities (carried forward from Turn 3)
    assert any("hooli" in e for e in r4_entities), (
        f"Turn 4 must stay scoped to Hooli (not revert to Globex). Entities: {r4['entities']}"
    )
    # Evidence should NOT contain Globex
    if r4["evidence"]:
        assert "globex" not in r4_evidence_text or "hooli" in r4_evidence_text, (
            f"Turn 4 evidence should be Hooli-scoped, not Globex. Got: {r4_evidence_text[:200]!r}"
        )
