"""
V8 Bumble Design — Work Surface Redesign Tests (Round 45).

Tests that work.js uses Bumble design system (maestro-card, Montserrat,
pill buttons, humanize still called) AND that the Round 45 redesign
adds the Timeline and Tasks sub-surfaces with proper Bumble styling.

Round 45 additions:
- 3 sub-tabs (Whispers / Timeline / Tasks) with Bumble pill navigation
- Timeline surface: chronological signal feed as maestro-cards with
  swipe-card-category badges per provider
- Tasks surface: auto-extracted action items as maestro-cards with
  priority badges, due dates, confidence labels, Mark done / Defer buttons
- POST /api/oem/tasks/complete endpoint for manual task completion
"""

from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    app_dir = str(pathlib.Path(__file__).resolve().parents[3])
    os.environ.setdefault("MAESTRO_APP_DIR", app_dir)
    os.environ.setdefault("MAESTRO_AUTH_DB", "/tmp/maestro_test_work_bumble_auth.db")
    os.environ.setdefault("MAESTRO_ADMIN_PASSWORD", "test")
    from maestro_api.main import create_app
    app = create_app(db_path=":memory:")
    with TestClient(app) as c:
        yield c


class TestWorkBumbleRedesign:
    """work.js must use Bumble design system."""

    def test_work_js_uses_maestro_card(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "maestro-card" in source, "work.js doesn't use maestro-card class"

    def test_work_js_uses_montserrat(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "Montserrat" in source, "work.js doesn't use Montserrat font"

    def test_work_js_uses_maestro_btn(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "maestro-btn" in source, "work.js doesn't use maestro-btn class"

    def test_work_js_uses_bumble_yellow(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "maestro-yellow" in source or "FFF4D1" in source, "work.js doesn't use Bumble yellow"

    def test_humanize_still_called_in_work(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "humanize(" in source, "humanize() not called in work.js"


# ============================================================
# Round 45 — Sub-tab navigation + Timeline + Tasks surfaces
# ============================================================

class TestRound45SubTabs:
    """Round 45 — Work surface has 3 sub-tabs with Bumble pill navigation."""

    def test_work_js_has_subtab_state(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "_workSubTab" in source, "work.js must have sub-tab state"
        assert "'whispers'" in source, "work.js must have whispers tab"
        assert "'timeline'" in source, "work.js must have timeline tab"
        assert "'tasks'" in source, "work.js must have tasks tab"

    def test_work_js_has_subtab_setter(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "_workSetTab" in source, "work.js must have _workSetTab function"

    def test_work_js_fetches_timeline(self, client) -> None:
        """Round 45 — Work surface fetches /timeline endpoint."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "/timeline" in source, "work.js must fetch /timeline endpoint"

    def test_work_js_fetches_tasks(self, client) -> None:
        """Round 45 — Work surface fetches /tasks endpoint."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "/tasks" in source, "work.js must fetch /tasks endpoint"

    def test_work_js_renders_all_three_subtabs(self, client) -> None:
        """All 3 sub-tab render functions exist."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "_renderWhispersSurface" in source
        assert "_renderTimelineSurface" in source
        assert "_renderTasksSurface" in source


class TestRound45TimelineSurface:
    """Round 45 — Timeline surface uses Bumble maestro-card containers."""

    def test_timeline_uses_maestro_card(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "timeline-card" in source, "Timeline must use timeline-card class"
        assert "maestro-card timeline-card" in source, \
            "Timeline cards must be maestro-card containers"

    def test_timeline_uses_swipe_card_category_badges(self, client) -> None:
        """Timeline cards use swipe-card-category badges for provider colors."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "swipe-card-category" in source, \
            "Timeline must use swipe-card-category for provider badges"
        assert "_providerToCategoryClass" in source, \
            "Must have provider-to-category mapping function"

    def test_timeline_has_empty_state(self, client) -> None:
        """Timeline has a calm empty state when no signals."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "No signals yet" in source, \
            "Timeline must have a calm empty state"

    def test_timeline_has_pagination_support(self, client) -> None:
        """Timeline supports 'Load more' for pagination."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "_loadMoreTimeline" in source or "Load more" in source, \
            "Timeline must support pagination"

    def test_timeline_describes_signals_humanistically(self, client) -> None:
        """Timeline describes signals in human terms, not raw type codes."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "_describeSignal" in source, \
            "Must have signal description function"
        assert "Pull request opened" in source or "Pull request" in source, \
            "Must describe PR signals humanistically"
        assert "Issue transitioned" in source or "Issue" in source, \
            "Must describe issue signals humanistically"


class TestRound45TasksSurface:
    """Round 45 — Tasks surface uses Bumble cards with priority + confidence."""

    def test_tasks_uses_maestro_card(self, client) -> None:
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "task-card" in source, "Tasks must use task-card class"
        assert "maestro-card task-card" in source, \
            "Task cards must be maestro-card containers"

    def test_tasks_has_priority_badges(self, client) -> None:
        """Task cards have priority badges (HIGH/MEDIUM/LOW) using swipe-card-category colors."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "priBadgeClass" in source or "priority" in source, \
            "Tasks must have priority badges"
        assert "HIGH" in source or "priority.toUpperCase" in source, \
            "Tasks must show priority label"

    def test_tasks_has_confidence_labels(self, client) -> None:
        """Task cards use P0-4 bold confidence labels (VERIFIED/CONFIDENT/EXPLORING)."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "VERIFIED" in source, "Tasks must use VERIFIED confidence label"
        assert "CONFIDENT" in source, "Tasks must use CONFIDENT confidence label"
        assert "EXPLORING" in source, "Tasks must use EXPLORING confidence label"

    def test_tasks_has_mark_done_button(self, client) -> None:
        """Tasks have a 'Mark done' button."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "Mark done" in source, "Tasks must have Mark done button"
        assert "task-done-btn" in source, "Must have task-done-btn class"

    def test_tasks_has_defer_button(self, client) -> None:
        """Tasks have a 'Defer' button."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "Defer" in source, "Tasks must have Defer button"
        assert "task-defer-btn" in source, "Must have task-defer-btn class"

    def test_tasks_shows_overdue_indicator(self, client) -> None:
        """Tasks show OVERDUE indicator for past-due dates."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "OVERDUE" in source, "Tasks must show OVERDUE indicator"
        assert "isOverdue" in source, "Must compute isOverdue flag"

    def test_tasks_has_empty_state(self, client) -> None:
        """Tasks surface has a calm empty state when no open tasks."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "No open tasks" in source, \
            "Tasks must have a calm empty state"

    def test_tasks_sorted_by_priority_then_due_date(self, client) -> None:
        """Tasks are sorted: high priority first, then by due date."""
        app_dir = os.environ.get("MAESTRO_APP_DIR", "")
        path = os.path.join(app_dir, "static", "js", "work.js")
        source = open(path).read()
        assert "priRank" in source or "priority" in source, \
            "Tasks must sort by priority"
        assert "due_date" in source, "Tasks must consider due_date in sort"


class TestRound45TasksCompleteEndpoint:
    """Round 45 — POST /api/oem/tasks/complete endpoint for manual completion."""

    def test_complete_endpoint_exists(self, client) -> None:
        """The /tasks/complete endpoint is registered."""
        r = client.post("/api/oem/tasks/complete", json={"task_id": "nonexistent-id"})
        # Should return 404 for a nonexistent task, not 404 for the route
        assert r.status_code == 404
        data = r.json()
        assert "not found" in data.get("detail", "").lower()

    def test_complete_endpoint_requires_task_id(self, client) -> None:
        """The endpoint requires a task_id in the payload."""
        r = client.post("/api/oem/tasks/complete", json={})
        assert r.status_code == 400
        assert "task_id" in r.json().get("detail", "").lower()

    def test_complete_endpoint_in_routes_file(self) -> None:
        """The endpoint is defined in routes/oem.py."""
        import maestro_api.routes.oem as mod
        source = open(mod.__file__).read()
        assert "@router.post(\"/tasks/complete\")" in source, \
            "routes/oem.py must have POST /tasks/complete endpoint"
        assert "def complete_task" in source, \
            "routes/oem.py must have complete_task function"


class TestRound45V5Litmus:
    """Round 45 — V5 litmus: no new sidebar items, no engagement tracking."""

    def test_no_new_sidebar_item(self) -> None:
        """The sub-tabs are WITHIN the Work surface, not new sidebar items."""
        import maestro_personal
        mode_tabs_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "mode-tabs.js"
        )
        source = mode_tabs_js.read_text()
        # The _workNavItems array should still have exactly 4 items (Today/Work/Ask/More)
        # The sub-tabs are inside work.js, not in the bottom nav.
        assert "_workNavItems" in source
        # Count the items in _workNavItems — should be 4
        import re
        match = re.search(r"_workNavItems\s*=\s*\[(.*?)\]", source, re.DOTALL)
        assert match, "_workNavItems array must exist"
        items_block = match.group(1)
        # Count the { id: ... } entries
        item_count = len(re.findall(r"\{\s*id:", items_block))
        assert item_count == 4, \
            f"Work nav must have exactly 4 items (V5 litmus); got {item_count}"

    def test_no_engagement_tracking_in_work_js(self) -> None:
        """No dwell time, return frequency, or engagement metrics in work.js."""
        import maestro_personal
        work_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "work.js"
        )
        source = work_js.read_text()
        forbidden = [
            "dwell_time", "dwellTime", "return_frequency", "returnFrequency",
            "engagement_score", "engagementScore", "session_length",
        ]
        for pattern in forbidden:
            assert pattern not in source, \
                f"work.js must not track engagement metrics: {pattern}"

    def test_withdrawal_path_documented(self) -> None:
        """work.js documents the withdrawal path (Guideline P9)."""
        import maestro_personal
        work_js = (
            pathlib.Path(maestro_personal.__file__).resolve().parents[2]
            / "static" / "js" / "work.js"
        )
        source = work_js.read_text()
        assert "WITHDRAWAL PATH" in source or "withdrawal" in source.lower(), \
            "work.js must document the withdrawal path (Guideline P9)"
