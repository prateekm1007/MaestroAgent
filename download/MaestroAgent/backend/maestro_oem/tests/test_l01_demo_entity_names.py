"""L-01 fix: Remove demo entity names from production synonym map.

The prior adversarial audit found (L-01):
> Entity synonyms include "globex", "initech", "hooli", "acme", "umbrella"
> — these should not be in production synonym lists.

The naive fix (just delete them) would break recall for queries like
"everything about Globex" because RecallEngine._resolve_entities() only
uses ENTITY_SYNONYMS — it doesn't extract customer names from signal
metadata.

The proper fix (P13: derive inputs from evidence):
  1. Remove demo names from ENTITY_SYNONYMS["customer"]
  2. Add signal-derived customer-name resolution to RecallEngine
     (same pattern AskPipeline already uses — Phase A)
  3. Customer names are DERIVED from signal metadata, not hardcoded

Adversarial tests (write first, watch fail, then fix):

  1. test_no_demo_entity_names_in_synonym_map
     ENTITY_SYNONYMS must NOT contain globex/initech/hooli/acme/umbrella.

  2. test_recall_resolves_customer_from_signal_metadata
     "everything about Globex" must still resolve to entity "Globex"
     AFTER demo names are removed — because the engine extracts customer
     names from signal metadata, not from a hardcoded synonym list.

  3. test_recall_finds_cross_entity_still_works
     The existing test_recall_finds_cross_entity must still pass after
     the fix — proves no regression in cross-entity recall.

  4. test_recall_resolves_real_customer_name_not_in_synonyms
     A customer named "AcmeCorp" (not in any synonym map) must resolve
     when signals reference it — proving the engine derives from evidence.

P2: Untested code is unverified code.
P13: Inputs must be DERIVED from real evidence, not hardcoded.
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


@pytest.fixture
def now():
    return datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)


# ═══ L-01: Demo entity names must NOT be in synonym map ════════════════════

def test_no_demo_entity_names_in_synonym_map():
    """ENTITY_SYNONYMS must NOT contain demo customer names."""
    from maestro_oem.recall_engine import ENTITY_SYNONYMS

    demo_names = {"globex", "initech", "hooli", "acme", "umbrella"}
    for canonical, synonyms in ENTITY_SYNONYMS.items():
        for syn in synonyms:
            assert syn.lower() not in demo_names, (
                f"Demo entity name '{syn}' found in ENTITY_SYNONYMS['{canonical}']. "
                f"Demo names must be derived from signal metadata, not hardcoded (L-01, P13)."
            )


# ═══ Recall must resolve customer names from signal metadata ═══════════════

def test_recall_resolves_customer_from_signal_metadata(now):
    """'everything about Globex' must resolve to entity 'Globex' via
    signal metadata, NOT via a hardcoded synonym."""
    from maestro_oem.recall_engine import RecallEngine
    from maestro_oem.signal import SignalType

    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:1",
            metadata={"customer": "Globex", "commitment": "Deliver SSO by Q4"},
            timestamp=now - timedelta(days=20),
        ),
        MockSignal(
            SignalType.CUSTOMER_OBJECTION,
            actor="jane@example.com",
            artifact="crm:2",
            metadata={"customer": "Globex", "objection_type": "pricing"},
            timestamp=now - timedelta(days=5),
        ),
    ]

    engine = RecallEngine(
        whisper_history_store=None,
        signals=signals,
        oem_state=None,
    )

    # This must work WITHOUT "globex" in the synonym map — the engine
    # must extract "Globex" from signal metadata.
    result = engine.recall("everything about Globex", org_id="default")

    # The engine must find results (signals about Globex)
    assert result.get("found") is True or len(result.get("items", [])) > 0, (
        f"RecallEngine must resolve 'Globex' from signal metadata. "
        f"Result: found={result.get('found')}, items={len(result.get('items', []))}"
    )


def test_recall_resolves_real_customer_name_not_in_synonyms(now):
    """A customer named 'AcmeCorp' (not in any synonym map, not a demo name)
    must resolve when signals reference it — proving the engine derives
    customer names from evidence, not from a hardcoded list."""
    from maestro_oem.recall_engine import RecallEngine
    from maestro_oem.signal import SignalType

    signals = [
        MockSignal(
            SignalType.CUSTOMER_COMMITMENT_MADE,
            actor="jane@example.com",
            artifact="crm:acmecorp-1",
            metadata={"customer": "AcmeCorp", "commitment": "Deliver API integration"},
            timestamp=now - timedelta(days=10),
        ),
    ]

    engine = RecallEngine(
        whisper_history_store=None,
        signals=signals,
        oem_state=None,
    )

    result = engine.recall("what did we promise AcmeCorp?", org_id="default")

    # Must find the AcmeCorp signal — proves customer-name resolution is
    # derived from signal metadata, not from a synonym list
    assert result.get("found") is True or len(result.get("items", [])) > 0, (
        f"RecallEngine must resolve 'AcmeCorp' from signal metadata "
        f"(a name that was NEVER in any synonym map). "
        f"Result: found={result.get('found')}, items={len(result.get('items', []))}"
    )
