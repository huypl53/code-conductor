"""Tests for conductor state models, enums, and error classes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from conductor.state import (
    AgentRecord,
    AgentStatus,
    ConductorState,
    Dependency,
    StateCorrupted,
    StateError,
    StateLockTimeout,
    Task,
    TaskStatus,
)


class TestTaskStatusEnum:
    def test_pending_serializes_as_plain_string(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        data = json.loads(task.model_dump_json())
        assert data["status"] == "pending"
        assert data["status"] != "TaskStatus.pending"

    def test_in_progress_serializes_as_plain_string(self) -> None:
        task = Task(id="t1", title="My Task", description="A description", status=TaskStatus.IN_PROGRESS)
        data = json.loads(task.model_dump_json())
        assert data["status"] == "in_progress"

    def test_all_task_status_values(self) -> None:
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.BLOCKED == "blocked"


class TestAgentStatusEnum:
    def test_idle_serializes_as_plain_string(self) -> None:
        agent = AgentRecord(id="a1", name="Agent One", role="worker")
        data = json.loads(agent.model_dump_json())
        assert data["status"] == "idle"
        assert data["status"] != "AgentStatus.idle"

    def test_all_agent_status_values(self) -> None:
        assert AgentStatus.IDLE == "idle"
        assert AgentStatus.WORKING == "working"
        assert AgentStatus.WAITING == "waiting"
        assert AgentStatus.DONE == "done"


class TestTaskModel:
    def test_create_with_minimal_fields(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        assert task.id == "t1"
        assert task.title == "My Task"
        assert task.description == "A description"

    def test_default_status_is_pending(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        assert task.status == "pending"

    def test_default_assigned_agent_is_none(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        assert task.assigned_agent is None

    def test_default_outputs_is_empty_dict(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        assert task.outputs == {}

    def test_created_at_is_utc_datetime(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        assert isinstance(task.created_at, datetime)
        assert task.created_at.tzinfo is not None

    def test_updated_at_is_utc_datetime(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        assert isinstance(task.updated_at, datetime)
        assert task.updated_at.tzinfo is not None


class TestAgentRecordModel:
    def test_create_with_minimal_fields(self) -> None:
        agent = AgentRecord(id="a1", name="Agent One", role="worker")
        assert agent.id == "a1"
        assert agent.name == "Agent One"
        assert agent.role == "worker"

    def test_default_status_is_idle(self) -> None:
        agent = AgentRecord(id="a1", name="Agent One", role="worker")
        assert agent.status == "idle"

    def test_default_current_task_id_is_none(self) -> None:
        agent = AgentRecord(id="a1", name="Agent One", role="worker")
        assert agent.current_task_id is None

    def test_registered_at_is_utc_datetime(self) -> None:
        agent = AgentRecord(id="a1", name="Agent One", role="worker")
        assert isinstance(agent.registered_at, datetime)
        assert agent.registered_at.tzinfo is not None


class TestDependencyModel:
    def test_stores_task_id_and_depends_on(self) -> None:
        dep = Dependency(task_id="t2", depends_on="t1")
        assert dep.task_id == "t2"
        assert dep.depends_on == "t1"


class TestConductorStateModel:
    def test_create_empty_no_args(self) -> None:
        state = ConductorState()
        assert state.version == "1"
        assert state.tasks == []
        assert state.agents == []
        assert state.dependencies == []

    def test_empty_state_is_serializable(self) -> None:
        state = ConductorState()
        data = json.loads(state.model_dump_json())
        assert data["version"] == "1"
        assert data["tasks"] == []
        assert data["agents"] == []
        assert data["dependencies"] == []

    def test_round_trip_with_tasks(self) -> None:
        task = Task(id="t1", title="My Task", description="A description")
        state = ConductorState(tasks=[task])
        json_str = state.model_dump_json()
        restored = ConductorState.model_validate_json(json_str)
        assert len(restored.tasks) == 1
        assert restored.tasks[0].id == "t1"
        assert restored.tasks[0].title == "My Task"
        assert restored.tasks[0].status == "pending"

    def test_round_trip_with_agents(self) -> None:
        agent = AgentRecord(id="a1", name="Agent One", role="worker")
        state = ConductorState(agents=[agent])
        json_str = state.model_dump_json()
        restored = ConductorState.model_validate_json(json_str)
        assert len(restored.agents) == 1
        assert restored.agents[0].id == "a1"
        assert restored.agents[0].status == "idle"

    def test_round_trip_with_dependencies(self) -> None:
        dep = Dependency(task_id="t2", depends_on="t1")
        state = ConductorState(dependencies=[dep])
        json_str = state.model_dump_json()
        restored = ConductorState.model_validate_json(json_str)
        assert len(restored.dependencies) == 1
        assert restored.dependencies[0].task_id == "t2"
        assert restored.dependencies[0].depends_on == "t1"

    def test_full_round_trip_with_all_fields(self) -> None:
        task = Task(id="t1", title="Task One", description="First task", status=TaskStatus.IN_PROGRESS)
        agent = AgentRecord(id="a1", name="Alpha", role="coder", status=AgentStatus.WORKING, current_task_id="t1")
        dep = Dependency(task_id="t2", depends_on="t1")
        state = ConductorState(tasks=[task], agents=[agent], dependencies=[dep])
        json_str = state.model_dump_json()
        restored = ConductorState.model_validate_json(json_str)
        assert restored.tasks[0].status == "in_progress"
        assert restored.agents[0].status == "working"
        assert restored.agents[0].current_task_id == "t1"
        assert restored.version == "1"


class TestErrorHierarchy:
    def test_state_error_can_be_raised_and_caught(self) -> None:
        with pytest.raises(StateError):
            raise StateError("base error")

    def test_state_lock_timeout_can_be_raised_and_caught(self) -> None:
        with pytest.raises(StateLockTimeout):
            raise StateLockTimeout("lock timed out")

    def test_state_corrupted_can_be_raised_and_caught(self) -> None:
        with pytest.raises(StateCorrupted):
            raise StateCorrupted("state is corrupted")

    def test_state_lock_timeout_inherits_from_state_error(self) -> None:
        with pytest.raises(StateError):
            raise StateLockTimeout("lock timed out")

    def test_state_corrupted_inherits_from_state_error(self) -> None:
        with pytest.raises(StateError):
            raise StateCorrupted("state is corrupted")
