"""Event classification module for the dashboard backend.

Provides EventType enum, DeltaEvent model, and classify_delta function that
diffs two ConductorState snapshots into typed delta events with smart
notification flags.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from conductor.state.models import ConductorState


class EventType(StrEnum):
    """Typed events emitted by classify_delta for dashboard consumers."""

    TASK_ASSIGNED = "task_assigned"
    TASK_STATUS_CHANGED = "task_status_changed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    AGENT_REGISTERED = "agent_registered"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    INTERVENTION_NEEDED = "intervention_needed"


class DeltaEvent(BaseModel):
    """A single classified delta event between two ConductorState snapshots.

    Fields:
        type: The event classification.
        task_id: Relevant task ID, or None for agent-only events.
        agent_id: Relevant agent ID, or None for task-only events.
        payload: Arbitrary extra data (status before/after, etc.).
        is_smart_notification: True for terminal/blocking events that warrant
            a push notification to the dashboard user.
    """

    model_config = ConfigDict(use_enum_values=True)

    type: EventType
    task_id: str | None = None
    agent_id: str | None = None
    payload: dict = {}
    is_smart_notification: bool = False


def classify_delta(
    prev: ConductorState | None,
    new: ConductorState,
) -> list[DeltaEvent]:
    """Diff two ConductorState snapshots and return a list of typed delta events.

    Args:
        prev: The previous state snapshot, or None for the initial load.
        new: The current state snapshot.

    Returns:
        Empty list when prev is None (initial state — no meaningful delta).
        Otherwise a list of DeltaEvent describing every change between
        prev and new.
    """
    if prev is None:
        return []

    events: list[DeltaEvent] = []

    # --- Task diffing ---
    prev_tasks = {t.id: t for t in prev.tasks}
    for task in new.tasks:
        if task.id not in prev_tasks:
            # New task appeared
            events.append(DeltaEvent(type=EventType.TASK_ASSIGNED, task_id=task.id))
            continue

        prev_task = prev_tasks[task.id]
        if task.status != prev_task.status:
            if task.status == "completed":
                events.append(
                    DeltaEvent(
                        type=EventType.TASK_COMPLETED,
                        task_id=task.id,
                        is_smart_notification=True,
                    )
                )
            elif task.status == "failed":
                events.append(
                    DeltaEvent(
                        type=EventType.TASK_FAILED,
                        task_id=task.id,
                        is_smart_notification=True,
                    )
                )
            else:
                events.append(
                    DeltaEvent(
                        type=EventType.TASK_STATUS_CHANGED,
                        task_id=task.id,
                    )
                )

    # --- Agent diffing ---
    prev_agents = {a.id: a for a in prev.agents}
    for agent in new.agents:
        if agent.id not in prev_agents:
            # New agent appeared
            events.append(
                DeltaEvent(type=EventType.AGENT_REGISTERED, agent_id=agent.id)
            )
            continue

        prev_agent = prev_agents[agent.id]
        if agent.status != prev_agent.status:
            if agent.status == "waiting":
                events.append(
                    DeltaEvent(
                        type=EventType.INTERVENTION_NEEDED,
                        agent_id=agent.id,
                        is_smart_notification=True,
                    )
                )
            else:
                events.append(
                    DeltaEvent(
                        type=EventType.AGENT_STATUS_CHANGED,
                        agent_id=agent.id,
                    )
                )

    return events
