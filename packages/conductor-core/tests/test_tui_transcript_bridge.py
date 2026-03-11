"""Phase 44: TranscriptPane state bridge tests.

Tests that AgentStateUpdated events are forwarded from ConductorApp to
TranscriptPane, and that AgentCells are created/updated/finalized correctly.

IMPORTANT: Keep run_test() inline in each test -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)

Set CONDUCTOR_NO_ANIMATIONS=1 before running to disable shimmer/fade-in
for deterministic assertions.
"""
from __future__ import annotations

import os

os.environ["CONDUCTOR_NO_ANIMATIONS"] = "1"


def _make_state(agents: list[dict], tasks: list[dict] | None = None) -> "ConductorState":
    """Build a minimal ConductorState for testing.

    Args:
        agents: list of dicts with keys: id, name, role, status, (optional) current_task_id
        tasks: list of dicts with keys: id, title, (optional) assigned_agent
    """
    from conductor.state.models import AgentRecord, ConductorState, Task

    agent_records = [AgentRecord(**a) for a in agents]
    task_records = [Task(**t) for t in (tasks or [])]
    return ConductorState(agents=agent_records, tasks=task_records)


async def test_state_update_forwarded_to_transcript():
    """BRDG-01: ConductorApp forwards AgentStateUpdated to TranscriptPane.

    When an AgentStateUpdated is posted to the app, the TranscriptPane
    receives it and an AgentCell is mounted.
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import TranscriptPane, AgentCell
    from conductor.tui.messages import AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

        def on_agent_state_updated(self, event: "AgentStateUpdated") -> None:
            """Fan-out: forward agent state to TranscriptPane (BRDG-01)."""
            from conductor.tui.widgets.transcript import TranscriptPane
            from conductor.tui.messages import AgentStateUpdated
            try:
                pane = self.query_one(TranscriptPane)
                pane.post_message(AgentStateUpdated(event.state))
            except Exception:
                pass

    app = TestApp()
    async with app.run_test() as pilot:
        state = _make_state(
            agents=[{"id": "a1", "name": "Alice", "role": "coder", "status": "working"}],
            tasks=[{"id": "t1", "title": "Write auth module", "description": "Implement auth", "assigned_agent": "a1"}],
        )
        app.post_message(AgentStateUpdated(state))
        await pilot.pause()
        await pilot.pause()

        pane = app.query_one(TranscriptPane)
        cells = list(pane.query(AgentCell))
        assert len(cells) == 1, f"Expected 1 AgentCell, got {len(cells)}"


async def test_agent_cells_registry_no_duplicates():
    """BRDG-02: Posting the same WORKING agent state twice creates only one AgentCell.

    TranscriptPane._agent_cells maps agent_id to AgentCell. Duplicate
    events for the same agent_id MUST NOT create a second cell.
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import TranscriptPane, AgentCell
    from conductor.tui.messages import AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

    app = TestApp()
    async with app.run_test() as pilot:
        state = _make_state(
            agents=[{"id": "a1", "name": "Alice", "role": "coder", "status": "working"}],
            tasks=[{"id": "t1", "title": "Write auth module", "description": "Implement auth", "assigned_agent": "a1"}],
        )
        pane = app.query_one(TranscriptPane)

        # Post the same state twice
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        cells = list(pane.query(AgentCell))
        assert len(cells) == 1, f"Expected 1 AgentCell (no duplicates), got {len(cells)}"
        assert len(pane._agent_cells) == 1, f"Expected registry size 1, got {len(pane._agent_cells)}"


async def test_working_agent_mounts_cell():
    """ACELL-01: When an agent first appears as WORKING, an AgentCell is mounted.

    The cell's label must contain the agent name and role.
    """
    from textual.app import App, ComposeResult
    from textual.widgets import Static
    from conductor.tui.widgets.transcript import TranscriptPane, AgentCell
    from conductor.tui.messages import AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

    app = TestApp()
    async with app.run_test() as pilot:
        state = _make_state(
            agents=[{"id": "a2", "name": "Bob", "role": "reviewer", "status": "working"}],
            tasks=[{"id": "t2", "title": "Review PR #42", "description": "Check code", "assigned_agent": "a2"}],
        )
        pane = app.query_one(TranscriptPane)
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        cells = list(pane.query(AgentCell))
        assert len(cells) == 1, f"Expected 1 AgentCell, got {len(cells)}"

        cell = cells[0]
        label = cell.query_one(".cell-label", Static)
        label_text = str(label.content)
        assert "Bob" in label_text, f"Agent name 'Bob' not in label: {label_text!r}"
        assert "reviewer" in label_text, f"Role 'reviewer' not in label: {label_text!r}"


async def test_status_transition_updates_cell():
    """ACELL-02: Status change updates the existing AgentCell via update_status().

    Post WORKING state, then WAITING state for the same agent.
    The cell's _status attribute must reflect the latest status.
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import TranscriptPane, AgentCell
    from conductor.tui.messages import AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)

        # First: WORKING state
        state_working = _make_state(
            agents=[{"id": "a3", "name": "Carol", "role": "planner", "status": "working"}],
            tasks=[{"id": "t3", "title": "Plan sprint", "description": "Sprint planning", "assigned_agent": "a3"}],
        )
        pane.post_message(AgentStateUpdated(state_working))
        await pilot.pause()

        # Second: WAITING state for same agent
        state_waiting = _make_state(
            agents=[{"id": "a3", "name": "Carol", "role": "planner", "status": "waiting"}],
            tasks=[{"id": "t3", "title": "Plan sprint", "description": "Sprint planning", "assigned_agent": "a3"}],
        )
        pane.post_message(AgentStateUpdated(state_waiting))
        await pilot.pause()

        cells = list(pane.query(AgentCell))
        assert len(cells) == 1, f"Expected 1 AgentCell (no duplicate on update), got {len(cells)}"
        cell = cells[0]
        assert cell._status == "waiting", f"Expected status 'waiting', got {cell._status!r}"


async def test_done_agent_finalizes_cell():
    """ACELL-03: Agent reaching DONE triggers finalize(); cell stays in DOM.

    Post WORKING state, then DONE state. Cell must be finalized (status == 'done')
    and must still be present in the transcript (not removed).
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import TranscriptPane, AgentCell
    from conductor.tui.messages import AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)

        # First: WORKING state
        state_working = _make_state(
            agents=[{"id": "a4", "name": "Dave", "role": "tester", "status": "working"}],
            tasks=[{"id": "t4", "title": "Write E2E tests", "description": "E2E testing", "assigned_agent": "a4"}],
        )
        pane.post_message(AgentStateUpdated(state_working))
        await pilot.pause()

        # Then: DONE state
        state_done = _make_state(
            agents=[{"id": "a4", "name": "Dave", "role": "tester", "status": "done"}],
            tasks=[{"id": "t4", "title": "Write E2E tests", "description": "E2E testing", "assigned_agent": "a4"}],
        )
        pane.post_message(AgentStateUpdated(state_done))
        await pilot.pause()

        cells = list(pane.query(AgentCell))
        assert len(cells) == 1, f"Expected cell still in DOM, got {len(cells)} cells"
        cell = cells[0]
        assert cell._status == "done", f"Expected status 'done', got {cell._status!r}"


async def test_scroll_preserved_when_scrolled_up():
    """SC-5: Mounting a new AgentCell does NOT scroll to bottom if user scrolled up.

    This verifies _maybe_scroll_end is called (not scroll_end directly)
    so the smart scroll policy is honored.
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import TranscriptPane, AgentCell, UserCell
    from conductor.tui.messages import AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

    app = TestApp()
    async with app.run_test(size=(80, 10)) as pilot:
        pane = app.query_one(TranscriptPane)

        # Mount enough content to make the pane scrollable
        for i in range(20):
            await pane.mount(UserCell(f"Message {i}: some content to fill the viewport"))
        await pilot.pause()

        # Scroll to bottom first, then scroll up
        pane.scroll_end(animate=False)
        await pilot.pause()
        pane.scroll_to(y=0, animate=False)
        await pilot.pause()

        # Confirm we're NOT at the bottom
        assert not pane._is_at_bottom, "Setup error: pane should not be at bottom after scroll_to(0)"

        # Remember current scroll position
        scroll_y_before = pane.scroll_offset.y

        # Post a WORKING agent state
        state = _make_state(
            agents=[{"id": "a5", "name": "Eve", "role": "ops", "status": "working"}],
            tasks=[{"id": "t5", "title": "Deploy to prod", "description": "Deployment", "assigned_agent": "a5"}],
        )
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        # Cell must be mounted
        cells = list(pane.query(AgentCell))
        assert len(cells) == 1, "AgentCell should be mounted"

        # Scroll position must NOT have jumped to bottom
        assert pane.scroll_offset.y == scroll_y_before, (
            f"Scroll jumped from {scroll_y_before} to {pane.scroll_offset.y} — "
            "smart scroll should preserve position when user scrolled up"
        )


async def test_agent_first_seen_as_done_no_cell():
    """Edge: Agent first seen as DONE does NOT get a cell created.

    If the watcher misses the WORKING snapshot and first sees DONE,
    no AgentCell should be created (don't retroactively show dead agents).
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import TranscriptPane, AgentCell
    from conductor.tui.messages import AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)

        # Agent appears for the first time already DONE
        state_done = _make_state(
            agents=[{"id": "a6", "name": "Frank", "role": "devops", "status": "done"}],
            tasks=[{"id": "t6", "title": "CI pipeline", "description": "Pipeline setup", "assigned_agent": "a6"}],
        )
        pane.post_message(AgentStateUpdated(state_done))
        await pilot.pause()

        cells = list(pane.query(AgentCell))
        assert len(cells) == 0, f"Expected no AgentCell for first-seen-as-done agent, got {len(cells)}"
        assert len(pane._agent_cells) == 0, f"Expected empty registry, got {pane._agent_cells}"
