"""Phase 43: AgentCell and OrchestratorStatusCell widget tests.

Tests that AgentCell and OrchestratorStatusCell render correctly,
transition through lifecycle states, and handle concurrent instances
with special-character IDs without CSS ID collisions.

IMPORTANT: Keep run_test() inline in each test -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)

Set CONDUCTOR_NO_ANIMATIONS=1 before running to disable shimmer/fade-in
for deterministic assertions.
"""
import os

os.environ["CONDUCTOR_NO_ANIMATIONS"] = "1"


async def test_agent_cell_header_content():
    """AgentCell mounts with agent name, role, and task title in the labeled header."""
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a1",
                agent_name="Alice",
                role="coder",
                task_title="Add auth module",
            )

    app = TestApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AgentCell)
        assert cell is not None

        from textual.widgets import Static
        label = cell.query_one(".cell-label", Static)
        label_text = str(label.renderable)
        assert "Alice" in label_text
        assert "coder" in label_text
        assert "Add auth module" in label_text


async def test_agent_cell_update_status():
    """AgentCell.update_status() transitions display without errors."""
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a2",
                agent_name="Bob",
                role="reviewer",
                task_title="Review PR",
            )

    app = TestApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AgentCell)

        from textual.widgets import Static
        # Transition to waiting
        cell.update_status("waiting")
        status_line = cell.query_one(".cell-status", Static)
        assert str(status_line.renderable) == "waiting"

        # Transition to done
        cell.update_status("done")
        status_line = cell.query_one(".cell-status", Static)
        assert str(status_line.renderable) == "done"


async def test_agent_cell_finalize_defensive():
    """AgentCell.finalize() is idempotent — safe before shimmer starts and after."""
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell

    # (a) finalize immediately without shimmer starting
    class TestAppA(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a3a",
                agent_name="Carol",
                role="planner",
                task_title="Plan sprint",
            )

    app_a = TestAppA()
    async with app_a.run_test() as pilot:
        cell = app_a.query_one(AgentCell)
        # Call finalize immediately — no shimmer started (ANIMATIONS=0), should not raise
        cell.finalize()
        assert cell._status == "done"

    # (b) finalize after shimmer may have started — shimmer timer should be None after
    class TestAppB(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a3b",
                agent_name="Dave",
                role="tester",
                task_title="Write tests",
            )

    app_b = TestAppB()
    async with app_b.run_test() as pilot:
        cell = app_b.query_one(AgentCell)
        # finalize cleans up shimmer timer
        cell.finalize()
        assert cell._shimmer_timer is None
        assert cell._status == "done"


async def test_orchestrator_status_cell_lifecycle():
    """OrchestratorStatusCell creates, updates, and finalizes as an ephemeral status cell."""
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import OrchestratorStatusCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield OrchestratorStatusCell(
                label="Orchestrator — delegating",
                description="Planning tasks...",
            )

    app = TestApp()
    async with app.run_test() as pilot:
        cell = app.query_one(OrchestratorStatusCell)
        assert cell is not None

        from textual.widgets import Static
        label_widget = cell.query_one("#orch-label", Static)
        body_widget = cell.query_one("#orch-body", Static)

        assert "Orchestrator" in str(label_widget.renderable)
        assert "Planning tasks" in str(body_widget.renderable)

        # Update description
        cell.update(description="Spawning 3 agents...")
        body_widget = cell.query_one("#orch-body", Static)
        assert "Spawning 3 agents" in str(body_widget.renderable)

        # Finalize and confirm update is locked out
        cell.finalize()
        cell.update(description="ignored")
        body_widget = cell.query_one("#orch-body", Static)
        # Body should still show the pre-finalize text
        assert "Spawning 3 agents" in str(body_widget.renderable)
        assert "ignored" not in str(body_widget.renderable)


async def test_multiple_agent_cells_no_id_collision():
    """Multiple AgentCells with special-char agent_ids mount without DuplicateIds error."""
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="agent.uuid-1",
                agent_name="Agent Alpha",
                role="coder",
                task_title="Task A",
            )
            yield AgentCell(
                agent_id="agent/uuid:2",
                agent_name="Agent Beta",
                role="reviewer",
                task_title="Task B",
            )
            yield AgentCell(
                agent_id="agent uuid 3",
                agent_name="Agent Gamma",
                role="planner",
                task_title="Task C",
            )

    app = TestApp()
    async with app.run_test() as pilot:
        cells = app.query(AgentCell)
        assert len(list(cells)) == 3

        # Each cell has a unique id starting with "acell-"
        cell_ids = [c.id for c in app.query(AgentCell)]
        assert all(cid is not None and cid.startswith("acell-") for cid in cell_ids)
        assert len(set(cell_ids)) == 3  # all unique

        # All 3 can be queried independently
        for cid in cell_ids:
            found = app.query_one(f"#{cid}", AgentCell)
            assert found is not None
