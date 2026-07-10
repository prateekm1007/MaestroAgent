"""
Tests for Phase 1.3 (semantic retrieval) and Phase 2.2 (corrections ledger).
"""

import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


@pytest.fixture
def temp_db():
    """Create a temp DB for isolation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.environ["MAESTRO_PERSONAL_DB"] = db_path
    yield db_path
    os.unlink(db_path)
    del os.environ["MAESTRO_PERSONAL_DB"]


class TestSemanticRetrieval:
    """Phase 1.3: FTS5-backed semantic retrieval tests."""

    def test_fts_index_initializes(self, temp_db):
        """FTS5 virtual table must initialize without error."""
        from maestro_personal_shell.semantic_retrieval import init_fts_index
        init_fts_index(temp_db)  # should not raise

    def test_index_and_search_signal(self, temp_db):
        """A signal must be searchable after indexing."""
        from maestro_personal_shell.semantic_retrieval import init_fts_index, index_signal, semantic_search
        init_fts_index(temp_db)

        signal = {
            "signal_id": "test-1",
            "entity": "AcmeCorp",
            "text": "AcmeCorp committed to signing the contract by Friday",
            "signal_type": "commitment_made",
            "user_email": "user@test.com",
            "timestamp": "2026-07-10T10:00:00Z",
        }
        index_signal(signal, db_path=temp_db)

        results = semantic_search("AcmeCorp contract", user_email="user@test.com", db_path=temp_db)
        assert len(results) > 0, "Must find the indexed signal"
        assert results[0]["entity"] == "AcmeCorp"
        assert "contract" in results[0]["text"]

    def test_search_ranks_relevant_signals_first(self, temp_db):
        """BM25 ranking must put the most relevant signal first."""
        from maestro_personal_shell.semantic_retrieval import init_fts_index, index_signal, semantic_search
        init_fts_index(temp_db)

        # Index 3 signals — one is clearly more relevant
        signals = [
            {
                "signal_id": "sig-1",
                "entity": "AcmeCorp",
                "text": "Random newsletter about marketing",
                "signal_type": "newsletter",
                "user_email": "user@test.com",
                "timestamp": "2026-07-01T10:00:00Z",
            },
            {
                "signal_id": "sig-2",
                "entity": "AcmeCorp",
                "text": "AcmeCorp contract renewal deadline Friday",
                "signal_type": "commitment_made",
                "user_email": "user@test.com",
                "timestamp": "2026-07-05T10:00:00Z",
            },
            {
                "signal_id": "sig-3",
                "entity": "OtherCorp",
                "text": "Completely unrelated meeting notes",
                "signal_type": "meeting",
                "user_email": "user@test.com",
                "timestamp": "2026-07-03T10:00:00Z",
            },
        ]
        for s in signals:
            index_signal(s, db_path=temp_db)

        results = semantic_search("AcmeCorp contract deadline", user_email="user@test.com", db_path=temp_db)
        assert len(results) > 0
        # The contract renewal signal should rank first
        assert results[0]["signal_id"] == "sig-2", \
            f"BM25 should rank sig-2 first, got {results[0]['signal_id']}"

    def test_search_respects_user_isolation(self, temp_db):
        """Semantic search must respect user_email scoping."""
        from maestro_personal_shell.semantic_retrieval import init_fts_index, index_signal, semantic_search
        init_fts_index(temp_db)

        # User A's signal
        index_signal({
            "signal_id": "user-a-sig",
            "entity": "SecretEntity",
            "text": "User A's private data about SecretEntity",
            "signal_type": "commitment_made",
            "user_email": "user-a@test.com",
            "timestamp": "2026-07-10T10:00:00Z",
        }, db_path=temp_db)

        # User B searches — must NOT see User A's signal
        results = semantic_search("SecretEntity", user_email="user-b@test.com", db_path=temp_db)
        assert len(results) == 0, "User B must not see User A's signals"

    def test_rebuild_fts_index(self, temp_db):
        """Rebuild must index all existing signals."""
        from maestro_personal_shell.semantic_retrieval import init_fts_index, rebuild_fts_index, semantic_search
        from maestro_personal_shell.api import init_db, save_signal_to_db
        init_db(temp_db)

        # Save signals via the normal API path (which indexes them)
        save_signal_to_db({
            "signal_id": "rebuild-1",
            "entity": "TestEntity",
            "text": "Test commitment for rebuild",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-10T10:00:00Z",
        }, db_path=temp_db, user_email="rebuild@test.com")

        # Rebuild from scratch
        count = rebuild_fts_index(temp_db, user_email="rebuild@test.com")
        assert count >= 1, "Rebuild must index existing signals"

        # Search must find them
        results = semantic_search("TestEntity", user_email="rebuild@test.com", db_path=temp_db)
        assert len(results) > 0

    def test_empty_query_returns_empty(self, temp_db):
        """An empty query must return empty (not all signals)."""
        from maestro_personal_shell.semantic_retrieval import get_relevant_signals
        results = get_relevant_signals("", db_path=temp_db)
        assert results == [], "Empty query must return empty, not all signals"


class TestCorrectionsLedger:
    """Phase 2.2: Corrections ledger tests."""

    def test_corrections_context_empty_on_day1(self, temp_db):
        """Corrections context must be empty when there are no corrections."""
        from maestro_personal_shell.outcome_tracker import get_corrections_context_for_llm
        ctx = get_corrections_context_for_llm(db_path=temp_db)
        assert ctx == "", "Must be empty on Day 1"

    def test_corrections_context_includes_corrected_signals(self, temp_db):
        """Corrections context must include dismissed/cancelled signals."""
        from maestro_personal_shell.api import init_db, save_signal_to_db
        from maestro_personal_shell.outcome_tracker import get_corrections_context_for_llm
        import sqlite3, json

        init_db(temp_db)

        # Save a signal
        save_signal_to_db({
            "signal_id": "corrected-sig",
            "entity": "DismissedEntity",
            "text": "This was dismissed by the user",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-10T10:00:00Z",
        }, db_path=temp_db, user_email="user@test.com")

        # Mark it as dismissed (simulate correction)
        conn = sqlite3.connect(temp_db)
        conn.execute(
            "UPDATE signals SET metadata = ? WHERE signal_id = ?",
            (json.dumps({"correction": "dismiss"}), "corrected-sig"),
        )
        conn.commit()
        conn.close()

        ctx = get_corrections_context_for_llm(db_path=temp_db, user_email="user@test.com")
        assert ctx, "Corrections context must not be empty when corrections exist"
        assert "DismissedEntity" in ctx, "Must include the corrected entity"
        assert "dismiss" in ctx, "Must include the correction action"
        assert "do NOT repeat" in ctx, "Must include the instruction to not repeat"

    def test_corrections_context_respects_user_isolation(self, temp_db):
        """User A's corrections must not appear in User B's context."""
        from maestro_personal_shell.api import init_db, save_signal_to_db
        from maestro_personal_shell.outcome_tracker import get_corrections_context_for_llm
        import sqlite3, json

        init_db(temp_db)

        # User A's corrected signal
        save_signal_to_db({
            "signal_id": "user-a-corrected",
            "entity": "UserAEntity",
            "text": "User A dismissed this",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-10T10:00:00Z",
        }, db_path=temp_db, user_email="user-a@test.com")

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "UPDATE signals SET metadata = ? WHERE signal_id = ?",
            (json.dumps({"correction": "dismiss"}), "user-a-corrected"),
        )
        conn.commit()
        conn.close()

        # User B's context must NOT include User A's correction
        ctx = get_corrections_context_for_llm(db_path=temp_db, user_email="user-b@test.com")
        assert ctx == "", "User B must not see User A's corrections"
        assert "UserAEntity" not in ctx if ctx else True

    def test_corrections_injected_into_llm_calibration_context(self, temp_db):
        """The _get_calibration_context function must include corrections."""
        from maestro_personal_shell.api import init_db, save_signal_to_db
        from maestro_personal_shell.llm_bridge import _get_calibration_context
        import sqlite3, json

        init_db(temp_db)

        save_signal_to_db({
            "signal_id": "calib-test-sig",
            "entity": "CalibEntity",
            "text": "Test for calibration context",
            "signal_type": "commitment_made",
            "timestamp": "2026-07-10T10:00:00Z",
        }, db_path=temp_db, user_email="user@test.com")

        conn = sqlite3.connect(temp_db)
        conn.execute(
            "UPDATE signals SET metadata = ? WHERE signal_id = ?",
            (json.dumps({"correction": "cancel"}), "calib-test-sig"),
        )
        conn.commit()
        conn.close()

        ctx = _get_calibration_context()
        assert "USER CORRECTIONS" in ctx or "CalibEntity" in ctx, \
            "Calibration context must include corrections"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
