"""Phase 1.2 regression: ledger-first routing for overdue/commitment queries.

Roadmap §1.2: 'Route overdue questions to structured ledger state before
semantic retrieval. FTS may retrieve evidence, but it must not determine
overdue status.'

This test verifies:
  1. route_to_ledger() returns at_risk entries for 'overdue' intent
  2. route_to_ledger() returns disputed + at_risk for 'broken' intent
  3. route_to_ledger() returns active + at_risk for 'commitment' intent
  4. ledger_entries_to_evidence() produces [LEDGER state=...] format
  5. Non-ledger intents (general, temporal) return None
"""
import os, sys, pathlib, tempfile, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

from maestro_personal_shell.ledger_routing import (
    route_to_ledger, ledger_entries_to_evidence,
    get_overdue_commitments, get_broken_commitments, get_active_commitments,
)
from maestro_personal_shell.commitment_ledger import init_ledger_table, upsert_ledger_entry
from maestro_personal_shell.db_util import get_db_conn


def _fresh_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False, prefix="ledger12_")
    tmp.close()
    init_ledger_table(tmp.name)
    return tmp.name


def _seed_ledger(db_path, user_email="test@local"):
    """Seed 5 ledger entries in different states."""
    entries = [
        # active commitment
        {"entity": "Alex", "state": "active", "action": "send pricing deck",
         "deadline_text": "Friday", "commitment_type": "explicit"},
        # at_risk (overdue)
        {"entity": "Riley", "state": "at_risk", "action": "send security questionnaire",
         "deadline_text": "end of week", "commitment_type": "explicit"},
        # at_risk (overdue)
        {"entity": "Priya", "state": "at_risk", "action": "send compliance report",
         "deadline_text": "June 30", "commitment_type": "explicit"},
        # disputed (broken)
        {"entity": "Morgan", "state": "disputed", "action": "present Nova results",
         "deadline_text": "", "commitment_type": "explicit"},
        # completed
        {"entity": "Sam", "state": "completed_claimed", "action": "deliver API integration",
         "deadline_text": "March 15", "commitment_type": "explicit"},
    ]
    for e in entries:
        upsert_ledger_entry(
            classification={
                "is_commitment": True,
                "commitment_type": e["commitment_type"],
                "state": e["state"],
                "owner": "user",
                "recipient": "",
                "action": e["action"],
                "deadline_text": e["deadline_text"],
                "deadline_datetime": "",
                "confidence": 0.8,
                "evidence_quote": e["action"],
            },
            signal={"signal_id": f"sig_{e['entity']}", "entity": e["entity"], "text": e["action"]},
            user_email=user_email,
            db_path=db_path,
        )
    return db_path


def test_overdue_intent_returns_at_risk():
    """Phase 1.2: 'overdue' intent must return at_risk ledger entries."""
    db = _fresh_db()
    _seed_ledger(db)
    entries = route_to_ledger("overdue", "test@local", db)
    assert entries is not None, "overdue intent must route to ledger"
    entities = [e["entity"] for e in entries]
    assert "Riley" in entities, f"Riley (at_risk) not in overdue: {entities}"
    assert "Priya" in entities, f"Priya (at_risk) not in overdue: {entities}"


def test_broken_intent_returns_disputed_and_at_risk():
    """Phase 1.2: 'broken' intent must return disputed + at_risk entries."""
    db = _fresh_db()
    _seed_ledger(db)
    entries = route_to_ledger("broken", "test@local", db)
    assert entries is not None
    entities = [e["entity"] for e in entries]
    assert "Morgan" in entities, f"Morgan (disputed) not in broken: {entities}"
    assert "Riley" in entities, f"Riley (at_risk) not in broken: {entities}"


def test_commitment_intent_returns_active_and_at_risk():
    """Phase 1.2: 'commitment' intent must return active + at_risk entries."""
    db = _fresh_db()
    _seed_ledger(db)
    entries = route_to_ledger("commitment", "test@local", db)
    assert entries is not None
    entities = [e["entity"] for e in entries]
    assert "Alex" in entities, f"Alex (active) not in commitment: {entities}"
    assert "Riley" in entities, f"Riley (at_risk) not in commitment: {entities}"


def test_relational_intent_returns_broken_entities():
    """Phase 1.2: 'relational' intent must return at_risk + disputed."""
    db = _fresh_db()
    _seed_ledger(db)
    entries = route_to_ledger("relational", "test@local", db)
    assert entries is not None
    entities = [e["entity"] for e in entries]
    assert "Riley" in entities or "Morgan" in entities, (
        f"relational must include broken entities: {entities}"
    )


def test_general_intent_returns_none():
    """Phase 1.2: non-ledger intents must return None (no ledger routing)."""
    db = _fresh_db()
    _seed_ledger(db)
    assert route_to_ledger("general", "test@local", db) is None
    assert route_to_ledger("temporal", "test@local", db) is None
    assert route_to_ledger("contradiction", "test@local", db) is None


def test_ledger_evidence_format():
    """Phase 1.2: ledger_entries_to_evidence must produce [LEDGER state=...] format."""
    db = _fresh_db()
    _seed_ledger(db)
    entries = route_to_ledger("overdue", "test@local", db)
    evidence = ledger_entries_to_evidence(entries)
    assert len(evidence) > 0
    for e in evidence:
        assert "[LEDGER state=" in e["text"], (
            f"Evidence must contain [LEDGER state=...] prefix: {e['text']}"
        )
        assert "entity" in e


def test_ledger_first_over_fts():
    """Phase 1.2: the ledger is authoritative for overdue status.

    Even if FTS doesn't find 'overdue' keyword, the ledger must return
    at_risk entries. This is the core of ledger-first routing.
    """
    db = _fresh_db()
    _seed_ledger(db)
    # Query the ledger directly — no FTS involved
    overdue = get_overdue_commitments("test@local", db)
    assert len(overdue) >= 2, f"Expected 2+ overdue entries, got {len(overdue)}"
    # Riley and Priya are at_risk
    entities = [e["entity"] for e in overdue]
    assert "Riley" in entities
    assert "Priya" in entities


if __name__ == "__main__":
    test_overdue_intent_returns_at_risk()
    print("Phase 1.2 test 1/7: overdue returns at_risk — PASS")
    test_broken_intent_returns_disputed_and_at_risk()
    print("Phase 1.2 test 2/7: broken returns disputed + at_risk — PASS")
    test_commitment_intent_returns_active_and_at_risk()
    print("Phase 1.2 test 3/7: commitment returns active + at_risk — PASS")
    test_relational_intent_returns_broken_entities()
    print("Phase 1.2 test 4/7: relational returns broken entities — PASS")
    test_general_intent_returns_none()
    print("Phase 1.2 test 5/7: general returns None — PASS")
    test_ledger_evidence_format()
    print("Phase 1.2 test 6/7: evidence format correct — PASS")
    test_ledger_first_over_fts()
    print("Phase 1.2 test 7/7: ledger-first over FTS — PASS")
    print("\nPhase 1.2 ledger-first routing tests PASSED")
