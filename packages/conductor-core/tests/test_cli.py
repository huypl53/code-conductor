"""Tests for the Conductor CLI."""

import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import conductor

from conductor.state.models import (
    AgentRecord,
    AgentStatus,
    ConductorState,
    Task,
    TaskStatus,
)


def test_conductor_help() -> None:
    """Test that conductor --help runs successfully."""
    result = subprocess.run(
        ["uv", "run", "conductor", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "conductor" in result.stdout.lower()


def test_conductor_version() -> None:
    """Test that the conductor module has a version string."""
    assert isinstance(conductor.__version__, str)


def test_build_table_empty() -> None:
    """_build_table with empty state returns Rich Table with 4 header columns, zero data rows."""
    from conductor.cli.display import _build_table

    table = _build_table(ConductorState())

    # Table should have header columns
    col_names = [col.header for col in table.columns]
    assert "Agent" in col_names
    assert "Role" in col_names
    assert "Task" in col_names
    assert "Status" in col_names

    # No data rows
    assert table.row_count == 0


def test_build_table_with_agents() -> None:
    """_build_table with 2 tasks returns 2 rows with correct agent/task data."""
    from conductor.cli.display import _build_table

    agent = AgentRecord(
        id="agent-1",
        name="Alice",
        role="Backend Developer",
        status=AgentStatus.WORKING,
        current_task_id="task-1",
    )
    task_assigned = Task(
        id="task-1",
        title="Implement auth",
        description="Add JWT auth",
        status=TaskStatus.IN_PROGRESS,
        assigned_agent="agent-1",
    )
    task_unassigned = Task(
        id="task-2",
        title="Write tests",
        description="Add unit tests",
        status=TaskStatus.PENDING,
        assigned_agent=None,
    )

    state = ConductorState(agents=[agent], tasks=[task_assigned, task_unassigned])
    table = _build_table(state)

    assert table.row_count == 2

    # Check column data by inspecting rendered cells
    # Column 0 = Agent, 1 = Role, 2 = Task, 3 = Status
    agent_col = table.columns[0]
    role_col = table.columns[1]
    task_col = table.columns[2]

    agent_cells = list(agent_col._cells)
    role_cells = list(role_col._cells)
    task_cells = list(task_col._cells)

    assert "Alice" in agent_cells
    assert "Backend Developer" in role_cells
    assert "Implement auth" in task_cells

    # Unassigned task row shows "-"
    assert "-" in agent_cells
    assert "Write tests" in task_cells


def test_build_table_status_styles() -> None:
    """Status column applies correct styles: green=COMPLETED, red=FAILED, yellow=IN_PROGRESS."""
    from rich.text import Text

    from conductor.cli.display import _build_table

    tasks = [
        Task(id="t1", title="Done task", description="", status=TaskStatus.COMPLETED),
        Task(id="t2", title="Failed task", description="", status=TaskStatus.FAILED),
        Task(
            id="t3",
            title="Active task",
            description="",
            status=TaskStatus.IN_PROGRESS,
        ),
    ]

    state = ConductorState(tasks=tasks)
    table = _build_table(state)

    assert table.row_count == 3

    status_col = table.columns[3]
    status_cells = list(status_col._cells)

    # Each status cell should be a Rich Text with the appropriate style
    completed_cell = status_cells[0]
    failed_cell = status_cells[1]
    in_progress_cell = status_cells[2]

    assert isinstance(completed_cell, Text)
    assert isinstance(failed_cell, Text)
    assert isinstance(in_progress_cell, Text)

    assert "green" in str(completed_cell.style)
    assert "red" in str(failed_cell.style)
    assert "yellow" in str(in_progress_cell.style)


def test_dispatch_cancel() -> None:
    """_dispatch_command('cancel agent-1') calls orchestrator.cancel_agent('agent-1')."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.cancel_agent = AsyncMock()
    mock_orch.inject_guidance = AsyncMock()

    asyncio.run(_dispatch_command("cancel agent-1", mock_orch))

    mock_orch.cancel_agent.assert_awaited_once_with("agent-1")
    mock_orch.inject_guidance.assert_not_awaited()


def test_dispatch_feedback() -> None:
    """_dispatch_command('feedback agent-1 great work on the models') calls inject_guidance."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.cancel_agent = AsyncMock()
    mock_orch.inject_guidance = AsyncMock()

    asyncio.run(_dispatch_command("feedback agent-1 great work on the models", mock_orch))

    mock_orch.inject_guidance.assert_awaited_once_with("agent-1", "great work on the models")
    mock_orch.cancel_agent.assert_not_awaited()


def test_dispatch_redirect() -> None:
    """_dispatch_command('redirect agent-1 work on auth instead') calls cancel_agent with new_instructions."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.cancel_agent = AsyncMock()
    mock_orch.inject_guidance = AsyncMock()

    asyncio.run(_dispatch_command("redirect agent-1 work on auth instead", mock_orch))

    mock_orch.cancel_agent.assert_awaited_once_with("agent-1", new_instructions="work on auth instead")
    mock_orch.inject_guidance.assert_not_awaited()


def test_dispatch_unknown() -> None:
    """_dispatch_command('blah') does not call any orchestrator method."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.cancel_agent = AsyncMock()
    mock_orch.inject_guidance = AsyncMock()

    asyncio.run(_dispatch_command("blah", mock_orch))

    mock_orch.cancel_agent.assert_not_awaited()
    mock_orch.inject_guidance.assert_not_awaited()


def test_dispatch_status() -> None:
    """_dispatch_command('status') with a state_manager reads state and builds table."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.cancel_agent = AsyncMock()
    mock_orch.inject_guidance = AsyncMock()

    mock_sm = MagicMock()
    mock_sm.read_state.return_value = ConductorState(
        tasks=[Task(id="t1", title="Test task", description="desc")]
    )

    asyncio.run(_dispatch_command("status", mock_orch, state_manager=mock_sm))

    mock_sm.read_state.assert_called_once()


def test_dispatch_pause_calls_pause_for_human_decision() -> None:
    """_dispatch_command('pause agent-1 Why is this file modified?') calls pause_for_human_decision."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.pause_for_human_decision = AsyncMock()

    human_out: asyncio.Queue = asyncio.Queue()
    human_in: asyncio.Queue = asyncio.Queue()

    asyncio.run(
        _dispatch_command(
            "pause agent-1 Why is this file modified?",
            mock_orch,
            human_out=human_out,
            human_in=human_in,
        )
    )

    mock_orch.pause_for_human_decision.assert_awaited_once_with(
        "agent-1", "Why is this file modified?", human_out, human_in
    )


def test_dispatch_pause_missing_args_prints_usage() -> None:
    """_dispatch_command('pause') with too few args prints usage and does NOT call pause_for_human_decision."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.pause_for_human_decision = AsyncMock()
    mock_console = MagicMock()

    asyncio.run(
        _dispatch_command("pause", mock_orch, console=mock_console)
    )

    mock_orch.pause_for_human_decision.assert_not_awaited()
    # Console should have printed some error/usage message
    mock_console.print.assert_called()


def test_dispatch_pause_no_queues_prints_error() -> None:
    """_dispatch_command('pause agent-1 question') with human_out=None prints error, no pause call."""
    from conductor.cli.input_loop import _dispatch_command

    mock_orch = MagicMock()
    mock_orch.pause_for_human_decision = AsyncMock()
    mock_console = MagicMock()

    asyncio.run(
        _dispatch_command(
            "pause agent-1 Is this correct?",
            mock_orch,
            console=mock_console,
            human_out=None,
            human_in=None,
        )
    )

    mock_orch.pause_for_human_decision.assert_not_awaited()
    mock_console.print.assert_called()


def test_run_interactive_routes_input(tmp_path: "Path") -> None:  # type: ignore[name-defined]
    """_run_async constructs Orchestrator with correct mode based on auto flag."""
    from pathlib import Path

    from conductor.cli.commands.run import _run_async

    async def _run_coro() -> None:
        return None

    with (
        patch("conductor.cli.commands.run.StateManager") as mock_sm_cls,
        patch("conductor.cli.commands.run.Orchestrator") as mock_orch_cls,
        patch("conductor.cli.commands.run.Live"),
        patch("conductor.cli.commands.run._display_loop", new=AsyncMock(return_value=None)),
        patch("conductor.cli.commands.run._input_loop", new=AsyncMock(return_value=None)),
    ):
        mock_sm = MagicMock()
        mock_sm.read_state.return_value = MagicMock(tasks=[], agents=[])
        mock_sm_cls.return_value = mock_sm

        # Test auto=True
        mock_orch_auto = MagicMock()
        mock_orch_auto.run_auto = AsyncMock(return_value=None)
        mock_orch_auto.run = AsyncMock(return_value=None)
        mock_orch_cls.return_value = mock_orch_auto

        asyncio.run(_run_async("test feature", auto=True, repo=tmp_path))

        mock_orch_cls.assert_called_once()
        call_kwargs = mock_orch_cls.call_args.kwargs
        assert call_kwargs["mode"] == "auto"

        mock_orch_cls.reset_mock()

        # Test auto=False (interactive)
        mock_orch_interactive = MagicMock()
        mock_orch_interactive.run_auto = AsyncMock(return_value=None)
        mock_orch_interactive.run = AsyncMock(return_value=None)
        mock_orch_cls.return_value = mock_orch_interactive

        asyncio.run(_run_async("test feature", auto=False, repo=tmp_path))

        mock_orch_cls.assert_called_once()
        call_kwargs = mock_orch_cls.call_args.kwargs
        assert call_kwargs["mode"] == "interactive"
