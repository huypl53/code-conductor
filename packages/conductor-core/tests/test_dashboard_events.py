"""Unit tests for conductor.dashboard.events — EventType, DeltaEvent, classify_delta."""
from __future__ import annotations

import json

import pytest

from conductor.dashboard.events import DeltaEvent, EventType, classify_delta
from conductor.state.models import (
    AgentRecord,
    AgentStatus,
    ConductorState,
    Task,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_task(
    task_id: str = "t1",
    status: TaskStatus = TaskStatus.PENDING,
    title: str = "Task",
) -> Task:
    return Task(id=task_id, title=title, description="desc", status=status)


def make_agent(
    agent_id: str = "a1",
    status: AgentStatus = AgentStatus.IDLE,
    name: str = "Agent",
) -> AgentRecord:
    return AgentRecord(id=agent_id, name=name, role="worker", status=status)


def make_state(
    tasks: list[Task] | None = None,
    agents: list[AgentRecord] | None = None,
) -> ConductorState:
    return ConductorState(
        tasks=tasks or [],
        agents=agents or [],
    )


# ---------------------------------------------------------------------------
# classify_delta(None, state) — initial snapshot
# ---------------------------------------------------------------------------


def test_classify_delta_none_prev_returns_empty_list() -> None:
    """No delta when prev is None — initial state load."""
    state = make_state(tasks=[make_task()], agents=[make_agent()])
    result = classify_delta(None, state)
    assert result == []


# ---------------------------------------------------------------------------
# Task events
# ---------------------------------------------------------------------------


def test_classify_delta_new_task_returns_task_assigned() -> None:
    """Task present in new but not prev -> TASK_ASSIGNED."""
    prev = make_state()
    new = make_state(tasks=[make_task("t1")])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.TASK_ASSIGNED
    assert events[0].task_id == "t1"
    assert events[0].is_smart_notification is False


def test_classify_delta_task_completed_is_smart_notification() -> None:
    """PENDING -> COMPLETED produces TASK_COMPLETED with is_smart_notification=True."""
    prev = make_state(tasks=[make_task("t1", TaskStatus.IN_PROGRESS)])
    new = make_state(tasks=[make_task("t1", TaskStatus.COMPLETED)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.TASK_COMPLETED
    assert events[0].task_id == "t1"
    assert events[0].is_smart_notification is True


def test_classify_delta_task_failed_is_smart_notification() -> None:
    """IN_PROGRESS -> FAILED produces TASK_FAILED with is_smart_notification=True."""
    prev = make_state(tasks=[make_task("t1", TaskStatus.IN_PROGRESS)])
    new = make_state(tasks=[make_task("t1", TaskStatus.FAILED)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.TASK_FAILED
    assert events[0].task_id == "t1"
    assert events[0].is_smart_notification is True


def test_classify_delta_task_status_changed_not_terminal() -> None:
    """PENDING -> IN_PROGRESS produces TASK_STATUS_CHANGED (no smart notification)."""
    prev = make_state(tasks=[make_task("t1", TaskStatus.PENDING)])
    new = make_state(tasks=[make_task("t1", TaskStatus.IN_PROGRESS)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.TASK_STATUS_CHANGED
    assert events[0].task_id == "t1"
    assert events[0].is_smart_notification is False


def test_classify_delta_task_blocked_is_not_smart_notification() -> None:
    """PENDING -> BLOCKED produces TASK_STATUS_CHANGED (not a terminal event)."""
    prev = make_state(tasks=[make_task("t1", TaskStatus.PENDING)])
    new = make_state(tasks=[make_task("t1", TaskStatus.BLOCKED)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.TASK_STATUS_CHANGED
    assert events[0].is_smart_notification is False


# ---------------------------------------------------------------------------
# Agent events
# ---------------------------------------------------------------------------


def test_classify_delta_new_agent_returns_agent_registered() -> None:
    """Agent present in new but not prev -> AGENT_REGISTERED."""
    prev = make_state()
    new = make_state(agents=[make_agent("a1")])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.AGENT_REGISTERED
    assert events[0].agent_id == "a1"
    assert events[0].is_smart_notification is False


def test_classify_delta_agent_waiting_is_smart_notification() -> None:
    """WORKING -> WAITING produces INTERVENTION_NEEDED with is_smart_notification=True."""
    prev = make_state(agents=[make_agent("a1", AgentStatus.WORKING)])
    new = make_state(agents=[make_agent("a1", AgentStatus.WAITING)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.INTERVENTION_NEEDED
    assert events[0].agent_id == "a1"
    assert events[0].is_smart_notification is True


def test_classify_delta_agent_status_changed_not_waiting() -> None:
    """IDLE -> WORKING produces AGENT_STATUS_CHANGED (no smart notification)."""
    prev = make_state(agents=[make_agent("a1", AgentStatus.IDLE)])
    new = make_state(agents=[make_agent("a1", AgentStatus.WORKING)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.AGENT_STATUS_CHANGED
    assert events[0].agent_id == "a1"
    assert events[0].is_smart_notification is False


def test_classify_delta_agent_done_is_not_smart_notification() -> None:
    """WORKING -> DONE produces AGENT_STATUS_CHANGED (not INTERVENTION_NEEDED)."""
    prev = make_state(agents=[make_agent("a1", AgentStatus.WORKING)])
    new = make_state(agents=[make_agent("a1", AgentStatus.DONE)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    assert events[0].type == EventType.AGENT_STATUS_CHANGED
    assert events[0].is_smart_notification is False


# ---------------------------------------------------------------------------
# Identical state — no events
# ---------------------------------------------------------------------------


def test_classify_delta_identical_state_returns_empty_list() -> None:
    """When prev and new are identical, no events are emitted."""
    state = make_state(
        tasks=[make_task("t1", TaskStatus.IN_PROGRESS)],
        agents=[make_agent("a1", AgentStatus.WORKING)],
    )
    events = classify_delta(state, state)
    assert events == []


# ---------------------------------------------------------------------------
# Multiple simultaneous changes
# ---------------------------------------------------------------------------


def test_classify_delta_multiple_changes_in_one_snapshot() -> None:
    """Multiple task/agent changes in a single delta are all captured."""
    prev = make_state(
        tasks=[make_task("t1", TaskStatus.IN_PROGRESS)],
        agents=[make_agent("a1", AgentStatus.WORKING)],
    )
    new = make_state(
        tasks=[
            make_task("t1", TaskStatus.COMPLETED),
            make_task("t2", TaskStatus.PENDING),  # new task
        ],
        agents=[
            make_agent("a1", AgentStatus.WAITING),  # agent waiting
            make_agent("a2", AgentStatus.IDLE),  # new agent
        ],
    )
    events = classify_delta(prev, new)
    types = [e.type for e in events]
    assert EventType.TASK_COMPLETED in types
    assert EventType.TASK_ASSIGNED in types
    assert EventType.INTERVENTION_NEEDED in types
    assert EventType.AGENT_REGISTERED in types
    assert len(events) == 4


# ---------------------------------------------------------------------------
# DeltaEvent JSON serialization
# ---------------------------------------------------------------------------


def test_delta_event_json_serialization_clean_enum_values() -> None:
    """DeltaEvent.model_dump_json() produces clean string enum values (not 'EventType.task_failed')."""
    event = DeltaEvent(
        type=EventType.TASK_FAILED,
        task_id="t1",
        is_smart_notification=True,
    )
    data = json.loads(event.model_dump_json())
    assert data["type"] == "task_failed"
    assert data["task_id"] == "t1"
    assert data["is_smart_notification"] is True
    assert data["agent_id"] is None
    assert data["payload"] == {}


def test_delta_event_json_all_event_types_serialize_cleanly() -> None:
    """All EventType values serialize to lowercase strings."""
    for event_type in EventType:
        event = DeltaEvent(type=event_type)
        data = json.loads(event.model_dump_json())
        assert data["type"] == str(event_type)
        # Confirm no 'EventType.' prefix in value
        assert "EventType" not in data["type"]
        assert "." not in data["type"]


def test_event_type_is_str_enum() -> None:
    """EventType values are lowercase strings."""
    assert EventType.TASK_ASSIGNED == "task_assigned"
    assert EventType.TASK_STATUS_CHANGED == "task_status_changed"
    assert EventType.TASK_COMPLETED == "task_completed"
    assert EventType.TASK_FAILED == "task_failed"
    assert EventType.AGENT_REGISTERED == "agent_registered"
    assert EventType.AGENT_STATUS_CHANGED == "agent_status_changed"
    assert EventType.INTERVENTION_NEEDED == "intervention_needed"
