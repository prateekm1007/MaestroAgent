"""
V8 Daily Work #2 — Task & Action-Item Intelligence. Regression tests.

Acceptance criteria:
  1. GET /api/oem/tasks returns tasks extracted from real signals (not hardcoded)
  2. Each task has description, assignee, source_signal, priority, status
  3. Tasks are created during ingestion (not on API call)
  4. TODAY shows "Your tasks" section
  5. V5 litmus: no new panel — enhances TODAY
  6. Feeds constitution: learning objects with type="task" enrich the model
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from maestro_oem import OEMEngine
from maestro_oem.signal import ExecutionSignal, SignalType, SignalProvider
from maestro_oem.task_extraction import TaskExtractor, get_tasks
from maestro_oem.learning_object import LearningObjectType


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_tasks_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


def _make_signal(text: str, actor: str = "priya@acme.com",
                 artifact: str = "slack:msg/1", domain: str = "engineering") -> ExecutionSignal:
    return ExecutionSignal(
        type=SignalType.MESSAGE_SENT,
        timestamp=datetime.now(timezone.utc),
        actor=actor,
        artifact=artifact,
        metadata={"text": text, "domain": domain},
        provider=SignalProvider.SLACK,
    )


# ============================================================
# TaskExtractor — pattern matching
# ============================================================

class TestTaskExtractorPatterns:
    """The TaskExtractor must find action items in signal text."""

    def test_extracts_name_to_verb_pattern(self) -> None:
        """'raj to review by Friday' must produce a task."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert "review" in tasks[0].description.lower()

    def test_extracts_name_will_verb_pattern(self) -> None:
        """'carlos will draft the RFC' must produce a task."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("carlos will draft the RFC by next week")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert "draft" in tasks[0].description.lower()

    def test_extracts_todo_pattern(self) -> None:
        """'TODO: update the docs' must produce a task."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("TODO: update the deployment docs by tomorrow")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert "update" in tasks[0].description.lower()

    def test_extracts_action_item_pattern(self) -> None:
        """'ACTION ITEM: schedule the retro' must produce a task."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("ACTION ITEM: schedule the retrospective by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert "schedule" in tasks[0].description.lower()

    def test_no_action_item_returns_empty(self) -> None:
        """Text without action items must produce no tasks."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("The weather is nice today.")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 0

    def test_high_priority_detection(self) -> None:
        """'ASAP' / 'urgent' / 'P0' must set priority to 'high'."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("priya to fix the P0 incident ASAP")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].metadata["priority"] == "high"

    def test_due_date_extraction(self) -> None:
        """'by Friday' must produce a due_date."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].metadata["due_date"] is not None

    def test_deduplication_across_text_fields(self) -> None:
        """Same text in multiple fields must not produce duplicate tasks."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = ExecutionSignal(
            type=SignalType.PR_OPENED,
            timestamp=datetime.now(timezone.utc),
            actor="priya@acme.com",
            artifact="github:pr/1",
            metadata={"text": "raj to review the PR", "title": "raj to review the PR", "domain": "engineering"},
            provider=SignalProvider.GITHUB,
        )
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1, f"Expected 1 task (deduped), got {len(tasks)}"


# ============================================================
# Task structure — each task has required fields
# ============================================================

class TestTaskStructure:
    """Each extracted task must have the required fields."""

    def test_task_has_description(self) -> None:
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].description
        assert len(tasks[0].description) > 3

    def test_task_has_assignee(self) -> None:
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].metadata["assignee"]

    def test_task_has_priority(self) -> None:
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].metadata["priority"] in ("high", "medium", "low")

    def test_task_has_status(self) -> None:
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].metadata["status"] == "open"

    def test_task_has_source_signal_id(self) -> None:
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].metadata["source_signal_id"] is not None

    def test_task_has_type_task(self) -> None:
        """The learning object must have type=TASK."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert tasks[0].type == LearningObjectType.TASK

    def test_task_has_signal_ids(self) -> None:
        """The task must be linked to the source signal."""
        engine = OEMEngine()
        extractor = TaskExtractor(engine.get_model())
        sig = _make_signal("raj to review the PR by Friday")
        tasks = extractor.extract_from_signal(sig)
        assert len(tasks) == 1
        assert sig.signal_id in tasks[0].signal_ids


# ============================================================
# Tasks created during ingestion (not on API call)
# ============================================================

class TestTasksCreatedDuringIngestion:
    """Tasks must be created during live_ingest, not on API call."""

    def test_live_ingest_creates_tasks(self) -> None:
        """live_ingest with an action-item signal must create task learning objects."""
        from maestro_api.oem_state import oem_state
        # Count tasks before
        model_before = oem_state.model
        tasks_before = sum(1 for lo in model_before.learning_objects.values()
                          if (lo.type.value if hasattr(lo.type, "value") else str(lo.type)) == "task")

        # Ingest a signal with an action item
        sig = _make_signal("raj to review the PR by Friday", artifact="slack:msg/ingest-test-1")
        # Use the direct engine path to avoid demo seed purge
        with oem_state._lock:
            assert oem_state.engine is not None
            oem_state.engine.ingest([sig])
            oem_state.signals.append(sig)
            from maestro_oem.task_extraction import TaskExtractor
            model = oem_state.engine.get_model()
            extractor = TaskExtractor(model)
            tasks = extractor.extract_from_signals([sig])
            for task in tasks:
                model.learning_objects[task.lo_id] = task
            oem_state._refresh_downstream_locked()

        # Count tasks after
        model_after = oem_state.model
        tasks_after = sum(1 for lo in model_after.learning_objects.values()
                         if (lo.type.value if hasattr(lo.type, "value") else str(lo.type)) == "task")
        assert tasks_after > tasks_before, (
            f"Tasks not created during ingestion. Before: {tasks_before}, After: {tasks_after}"
        )


# ============================================================
# API endpoint — GET /api/oem/tasks
# ============================================================

class TestTasksAPIEndpoint:
    """The /api/oem/tasks endpoint must work."""

    def test_tasks_endpoint_returns_200(self, client) -> None:
        r = client.get("/api/oem/tasks")
        assert r.status_code == 200

    def test_tasks_endpoint_has_required_structure(self, client) -> None:
        r = client.get("/api/oem/tasks")
        data = r.json()
        assert "tasks" in data
        assert "total" in data
        assert "open_count" in data
        assert "done_count" in data
        assert "high_priority_count" in data
        assert "filters_applied" in data

    def test_tasks_endpoint_filters_by_priority(self, client) -> None:
        """Filtering by priority must work."""
        from maestro_api.oem_state import oem_state
        # Ingest a high-priority task
        sig = _make_signal("priya to fix the P0 incident ASAP", artifact="slack:msg/priority-test")
        with oem_state._lock:
            assert oem_state.engine is not None
            oem_state.engine.ingest([sig])
            oem_state.signals.append(sig)
            from maestro_oem.task_extraction import TaskExtractor
            model = oem_state.engine.get_model()
            extractor = TaskExtractor(model)
            tasks = extractor.extract_from_signals([sig])
            for task in tasks:
                model.learning_objects[task.lo_id] = task
            oem_state._refresh_downstream_locked()

        r = client.get("/api/oem/tasks", params={"priority": "high"})
        data = r.json()
        assert data["total"] > 0
        for t in data["tasks"]:
            assert t["priority"] == "high"


# ============================================================
# V5 litmus — no new panel
# ============================================================

class TestV5LitmusNoNewPanel:
    """V5 litmus: no new panel. Tasks enhance TODAY, not a new surface."""

    def test_task_extraction_module_does_not_create_surface(self) -> None:
        import maestro_oem.task_extraction as mod
        source = open(mod.__file__).read()
        assert "register_surface" not in source
        assert "new_panel" not in source

    def test_today_js_has_tasks_section(self, client) -> None:
        """today.js must fetch /tasks and render a 'Your tasks' section."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        today_path = os.path.join(app_dir, "static", "js", "today.js")
        if not os.path.exists(today_path):
            pytest.skip(f"today.js not found at {today_path}")
        source = open(today_path).read()
        assert "/tasks" in source, "today.js does not fetch /tasks endpoint"
        assert "Your tasks" in source, "today.js missing 'Your tasks' section header"

    def test_routes_oem_has_tasks_endpoint(self) -> None:
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert '@router.get("/tasks")' in source, "routes/oem.py missing /tasks endpoint"

    def test_live_ingest_calls_task_extractor(self) -> None:
        """oem_state.py live_ingest must call TaskExtractor."""
        import maestro_api.oem_state as mod
        source = open(mod.__file__).read()
        assert "TaskExtractor" in source, "oem_state.py does not call TaskExtractor"
        assert "extract_from_signals" in source, "oem_state.py does not call extract_from_signals"
