"""Phase 35: Agent monitoring panel tests.

Tests that AgentMonitorPane correctly mounts, updates, and removes
AgentPanel widgets in response to AgentStateUpdated messages.

IMPORTANT: Keep run_test() inline in each test -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""


def _make_state(agents_data, tasks_data=None):
    """Build a ConductorState from simple dicts for test brevity."""
    from conductor.state.models import (
        AgentRecord,
        AgentStatus,
        ConductorState,
        Task,
        TaskStatus,
    )

    agents = []
    for a in agents_data:
        agents.append(
            AgentRecord(
                id=a["id"],
                name=a["name"],
                role=a.get("role", "coder"),
                status=AgentStatus(a.get("status", "working")),
                current_task_id=a.get("current_task_id"),
            )
        )
    tasks = []
    for t in (tasks_data or []):
        tasks.append(
            Task(
                id=t["id"],
                title=t["title"],
                description=t.get("description", ""),
                status=TaskStatus(t.get("status", "in_progress")),
                assigned_agent=t.get("assigned_agent"),
            )
        )
    return ConductorState(agents=agents, tasks=tasks)


async def test_agent_panel_appears_for_working_agent():
    """Post AgentStateUpdated with one WORKING agent -> one AgentPanel appears."""
    from conductor.tui.messages import AgentStateUpdated
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel

    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentMonitorPane(id="agent-monitor")

    state = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "working", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Add auth", "assigned_agent": "a1"}],
    )

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        panels = pane.query(AgentPanel)
        assert len(panels) == 1
        assert panels[0].agent_id == "a1"


async def test_agent_panel_shows_name_task_status():
    """Panel title contains agent name and status; expanded content shows task title."""
    from conductor.tui.messages import AgentStateUpdated
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel

    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentMonitorPane(id="agent-monitor")

    state = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "working", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Add auth module", "assigned_agent": "a1"}],
    )

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        panel = pane.query_one(AgentPanel)
        assert "Agent 1" in str(panel.title)
        assert "working" in str(panel.title)


async def test_state_update_refreshes_existing_panel():
    """Post two AgentStateUpdated with same agent ID -> still one panel, title updated."""
    from conductor.tui.messages import AgentStateUpdated
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel

    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentMonitorPane(id="agent-monitor")

    state1 = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "working", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Add auth", "assigned_agent": "a1"}],
    )
    state2 = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "waiting", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Add auth", "assigned_agent": "a1"}],
    )

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        pane.post_message(AgentStateUpdated(state1))
        await pilot.pause()
        pane.post_message(AgentStateUpdated(state2))
        await pilot.pause()

        panels = pane.query(AgentPanel)
        assert len(panels) == 1
        assert "waiting" in str(panels[0].title)


async def test_expanded_panel_shows_activity():
    """Expand panel -> Static content includes task title text."""
    from conductor.tui.messages import AgentStateUpdated
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel

    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentMonitorPane(id="agent-monitor")

    state = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "working", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Implement login flow", "assigned_agent": "a1"}],
    )

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        panel = pane.query_one(AgentPanel)
        # Panel content should contain the task title
        task_static = panel.query_one("#panel-task", Static)
        # Access the internal content string set by Static.__init__ / update()
        content = str(task_static._Static__content)
        assert "Implement login flow" in content


async def test_completed_agent_panel_removed():
    """Post AgentStateUpdated with agent DONE -> panel removed from pane."""
    from conductor.tui.messages import AgentStateUpdated
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel

    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentMonitorPane(id="agent-monitor")

    state1 = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "working", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Add auth", "assigned_agent": "a1"}],
    )
    state2 = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "done", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Add auth", "assigned_agent": "a1"}],
    )

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        pane.post_message(AgentStateUpdated(state1))
        await pilot.pause()
        assert len(pane.query(AgentPanel)) == 1

        pane.post_message(AgentStateUpdated(state2))
        await pilot.pause()
        assert len(pane.query(AgentPanel)) == 0


async def test_empty_state_shows_no_agents():
    """Post AgentStateUpdated with empty agents list -> 'No agents active' shown."""
    from conductor.tui.messages import AgentStateUpdated
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel

    from textual.app import App, ComposeResult
    from textual.widgets import Static

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentMonitorPane(id="agent-monitor")

    # First add an agent, then clear all
    state1 = _make_state(
        [{"id": "a1", "name": "Agent 1", "status": "working", "current_task_id": "t1"}],
        [{"id": "t1", "title": "Add auth", "assigned_agent": "a1"}],
    )
    state2 = _make_state([], [])

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)

        # Initially "No agents active" should be visible
        empty_label = pane.query_one("#monitor-empty", Static)
        assert empty_label.display is True

        # Add agent -- empty label should hide
        pane.post_message(AgentStateUpdated(state1))
        await pilot.pause()
        assert empty_label.display is False

        # Remove all agents -- empty label should show again
        pane.post_message(AgentStateUpdated(state2))
        await pilot.pause()
        assert empty_label.display is True


async def test_multiple_agents_multiple_panels():
    """Post state with 2 WORKING agents -> 2 AgentPanel widgets."""
    from conductor.tui.messages import AgentStateUpdated
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel

    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentMonitorPane(id="agent-monitor")

    state = _make_state(
        [
            {"id": "a1", "name": "Agent 1", "status": "working", "current_task_id": "t1"},
            {"id": "a2", "name": "Agent 2", "status": "waiting", "current_task_id": "t2"},
        ],
        [
            {"id": "t1", "title": "Task one", "assigned_agent": "a1"},
            {"id": "t2", "title": "Task two", "assigned_agent": "a2"},
        ],
    )

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        panels = pane.query(AgentPanel)
        assert len(panels) == 2
        agent_ids = {p.agent_id for p in panels}
        assert agent_ids == {"a1", "a2"}
