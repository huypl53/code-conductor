"""Tests for the Conductor CLI."""

import subprocess

import conductor
import pytest

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
