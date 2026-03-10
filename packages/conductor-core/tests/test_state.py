"""Tests for StateManager: file-locked atomic read-modify-write operations.

Covers CORD-01, CORD-02, CORD-03, CORD-06 requirements.
"""
from __future__ import annotations

import multiprocessing
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from conductor.state import (
    AgentRecord,
    ConductorState,
    Dependency,
    StateCorrupted,
    StateLockTimeout,
    Task,
    TaskStatus,
)
from conductor.state.manager import StateManager


# ---------------------------------------------------------------------------
# Module-level worker function for multiprocessing spawn compatibility
# ---------------------------------------------------------------------------


def _write_tasks_worker(state_path: Path, prefix: str, count: int) -> None:
    """Write `count` tasks to the state file, used by concurrent test."""
    manager = StateManager(state_path)
    for i in range(count):
        task_id = f"{prefix}-task-{i}"

        def _add(state: ConductorState, _id: str = task_id) -> None:
            state.tasks.append(
                Task(
                    id=_id,
                    title=f"Task {_id}",
                    description=f"Description for {_id}",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        manager.mutate(_add)


# ---------------------------------------------------------------------------
# CORD-01: Task, Agent, and Dependency round-trip fidelity
# ---------------------------------------------------------------------------


class TestCord01RoundTrip:
    """CORD-01: A Task, Agent, and Dependency can be written and read back."""

    def test_task_round_trip(self, tmp_path: Path) -> None:
        """Create StateManager, mutate to add a Task, read back, assert fields."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        task_id = "task-001"
        task_title = "Test Task"
        task_desc = "A test task description"

        def _add(state: ConductorState) -> None:
            state.tasks.append(
                Task(
                    id=task_id,
                    title=task_title,
                    description=task_desc,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        manager.mutate(_add)

        result = manager.read_state()
        assert len(result.tasks) == 1
        task = result.tasks[0]
        assert task.id == task_id
        assert task.title == task_title
        assert task.description == task_desc
        assert task.status == "pending"

    def test_full_state_round_trip(self, tmp_path: Path) -> None:
        """Add a Task, AgentRecord, and Dependency; read back, assert all three lists."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        def _add(state: ConductorState) -> None:
            state.tasks.append(
                Task(
                    id="t-001",
                    title="Task One",
                    description="First task",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            state.agents.append(
                AgentRecord(
                    id="agent-001",
                    name="Agent Alpha",
                    role="coder",
                    registered_at=datetime.now(UTC),
                )
            )
            state.dependencies.append(
                Dependency(task_id="t-002", depends_on="t-001")
            )

        manager.mutate(_add)

        result = manager.read_state()
        assert len(result.tasks) == 1
        assert len(result.agents) == 1
        assert len(result.dependencies) == 1
        assert result.tasks[0].id == "t-001"
        assert result.agents[0].id == "agent-001"
        assert result.dependencies[0].task_id == "t-002"
        assert result.dependencies[0].depends_on == "t-001"

    def test_empty_state_on_missing_file(self, tmp_path: Path) -> None:
        """read_state() on non-existent file returns ConductorState with empty lists."""
        state_path = tmp_path / "nonexistent.json"
        manager = StateManager(state_path)

        result = manager.read_state()
        assert isinstance(result, ConductorState)
        assert result.tasks == []
        assert result.agents == []
        assert result.dependencies == []
        assert result.version == "1"


# ---------------------------------------------------------------------------
# CORD-02: Concurrent writes do not corrupt state
# ---------------------------------------------------------------------------


class TestCord02ConcurrentWrites:
    """CORD-02: File locking prevents concurrent write corruption."""

    def test_assign_task(self, tmp_path: Path) -> None:
        """Add a task then assign it; read back and assert assignment and status."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        task_id = "task-assign-001"
        agent_id = "agent-001"

        def _add(state: ConductorState) -> None:
            state.tasks.append(
                Task(
                    id=task_id,
                    title="Assignable Task",
                    description="Will be assigned",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        manager.mutate(_add)
        manager.assign_task(task_id, agent_id)

        result = manager.read_state()
        assert len(result.tasks) == 1
        task = result.tasks[0]
        assert task.assigned_agent == agent_id
        assert task.status == "in_progress"

    def test_concurrent_writes_no_corruption(self, tmp_path: Path) -> None:
        """Two processes each write 10 tasks; final state has 20 tasks, none lost."""
        state_path = tmp_path / "state.json"

        ctx = multiprocessing.get_context("spawn")
        p1 = ctx.Process(
            target=_write_tasks_worker,
            args=(state_path, "alpha", 10),
        )
        p2 = ctx.Process(
            target=_write_tasks_worker,
            args=(state_path, "beta", 10),
        )

        p1.start()
        p2.start()
        p1.join(timeout=60)
        p2.join(timeout=60)

        assert p1.exitcode == 0, "alpha worker failed"
        assert p2.exitcode == 0, "beta worker failed"

        manager = StateManager(state_path)
        result = manager.read_state()
        assert len(result.tasks) == 20, (
            f"Expected 20 tasks, got {len(result.tasks)}: "
            f"{[t.id for t in result.tasks]}"
        )


# ---------------------------------------------------------------------------
# CORD-03: Status updates observable across StateManager instances
# ---------------------------------------------------------------------------


class TestCord03StatusUpdates:
    """CORD-03: Sub-agent can update status; orchestrator can observe it."""

    def test_update_task_status(self, tmp_path: Path) -> None:
        """Add a task, update to COMPLETED with output, read back and assert."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        task_id = "task-status-001"

        def _add(state: ConductorState) -> None:
            state.tasks.append(
                Task(
                    id=task_id,
                    title="Status Task",
                    description="Will be completed",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        manager.mutate(_add)
        manager.update_task_status(
            task_id, TaskStatus.COMPLETED, output={"result": "done"}
        )

        result = manager.read_state()
        task = result.tasks[0]
        assert task.status == "completed"
        assert task.outputs == {"result": "done"}

    def test_orchestrator_observes_status(self, tmp_path: Path) -> None:
        """Two separate StateManager instances on the same file — changes visible."""
        state_path = tmp_path / "state.json"
        agent_manager = StateManager(state_path)  # simulates sub-agent
        orchestrator_manager = StateManager(state_path)  # simulates orchestrator

        task_id = "task-obs-001"
        agent_id = "agent-001"

        def _add(state: ConductorState) -> None:
            state.tasks.append(
                Task(
                    id=task_id,
                    title="Observable Task",
                    description="Orchestrator will watch this",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        agent_manager.mutate(_add)
        agent_manager.assign_task(task_id, agent_id)
        agent_manager.update_task_status(task_id, TaskStatus.COMPLETED)

        result = orchestrator_manager.read_state()
        task = result.tasks[0]
        assert task.status == "completed"
        assert task.assigned_agent == agent_id


# ---------------------------------------------------------------------------
# CORD-06: All agents see the complete task list
# ---------------------------------------------------------------------------


class TestCord06AllTasksVisible:
    """CORD-06: All agents can read the full task list."""

    def test_all_tasks_visible(self, tmp_path: Path) -> None:
        """Add 3 tasks with different agents, read_state(), assert all 3 visible."""
        state_path = tmp_path / "state.json"
        manager = StateManager(state_path)

        tasks_data = [
            ("t-a", "agent-alpha"),
            ("t-b", "agent-beta"),
            ("t-c", "agent-gamma"),
        ]

        for task_id, agent_id in tasks_data:

            def _add(state: ConductorState, _tid: str = task_id) -> None:
                state.tasks.append(
                    Task(
                        id=_tid,
                        title=f"Task {_tid}",
                        description=f"Owned by some agent",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )

            manager.mutate(_add)
            manager.assign_task(task_id, agent_id)

        result = manager.read_state()
        assert len(result.tasks) == 3

        task_ids = {t.id for t in result.tasks}
        assert task_ids == {"t-a", "t-b", "t-c"}

        assignments = {t.id: t.assigned_agent for t in result.tasks}
        assert assignments["t-a"] == "agent-alpha"
        assert assignments["t-b"] == "agent-beta"
        assert assignments["t-c"] == "agent-gamma"
