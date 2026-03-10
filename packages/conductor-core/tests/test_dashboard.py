"""Integration tests for conductor.dashboard.server — REST and WebSocket endpoints."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from conductor.dashboard.events import DeltaEvent, EventType, classify_delta
from conductor.dashboard.server import create_app
from conductor.state.manager import StateManager
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


def write_state(state_path: Path, state: ConductorState) -> None:
    """Write ConductorState to disk via StateManager."""
    manager = StateManager(state_path)
    # Use a fresh write: serialize to JSON and write atomically
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(state.model_dump_json())


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
    return ConductorState(tasks=tasks or [], agents=agents or [])


# ---------------------------------------------------------------------------
# Test 1: GET /state returns 200 with valid ConductorState JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_state_returns_200_with_valid_json(tmp_path: Path) -> None:
    """GET /state returns 200 and full ConductorState JSON with known task ids."""
    state_path = tmp_path / "state.json"
    initial_state = make_state(
        tasks=[make_task("t1", title="Task One"), make_task("t2", title="Task Two")]
    )
    write_state(state_path, initial_state)

    app = create_app(state_path)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/state")

    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    task_ids = [t["id"] for t in data["tasks"]]
    assert "t1" in task_ids
    assert "t2" in task_ids
    assert "agents" in data


# ---------------------------------------------------------------------------
# Test 2: WebSocket client receives full state snapshot as first message on connect
# ---------------------------------------------------------------------------


def test_ws_initial_state_snapshot_on_connect(tmp_path: Path) -> None:
    """WebSocket client receives the current state as the first message on connect."""
    state_path = tmp_path / "state.json"
    initial_state = make_state(
        tasks=[make_task("t1"), make_task("t2")],
        agents=[make_agent("a1")],
    )
    write_state(state_path, initial_state)

    app = create_app(state_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            first_message = ws.receive_text()

    data = json.loads(first_message)
    assert "tasks" in data
    task_ids = [t["id"] for t in data["tasks"]]
    assert "t1" in task_ids
    assert "t2" in task_ids


# ---------------------------------------------------------------------------
# Test 3: WebSocket broadcast delivers delta events to connected client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_broadcast_delivers_delta_event(tmp_path: Path) -> None:
    """ConnectionManager.broadcast() sends a message to connected WebSocket clients.

    Tests the broadcast mechanism by directly exercising ConnectionManager with
    a mock WebSocket — the watcher E2E is a manual integration test.
    """
    from unittest.mock import AsyncMock, MagicMock

    from conductor.dashboard.server import ConnectionManager

    manager = ConnectionManager()

    # Create a mock WebSocket that records sent messages
    messages: list[str] = []
    mock_ws = MagicMock()

    async def capture_send(msg: str) -> None:
        messages.append(msg)

    mock_ws.send_text = AsyncMock(side_effect=capture_send)
    manager.active_connections.append(mock_ws)

    event = DeltaEvent(type=EventType.TASK_ASSIGNED, task_id="t99")
    await manager.broadcast(event.model_dump_json())

    assert len(messages) == 1
    data = json.loads(messages[0])
    assert data["type"] == "task_assigned"
    assert data["task_id"] == "t99"


# ---------------------------------------------------------------------------
# Test 4: TASK_FAILED delta event has is_smart_notification=True
# ---------------------------------------------------------------------------


def test_classify_task_failed_is_smart_notification() -> None:
    """classify_delta produces TASK_FAILED with is_smart_notification=True."""
    prev = make_state(tasks=[make_task("t1", TaskStatus.IN_PROGRESS)])
    new = make_state(tasks=[make_task("t1", TaskStatus.FAILED)])
    events = classify_delta(prev, new)
    assert len(events) == 1
    event = events[0]
    assert event.type == EventType.TASK_FAILED
    assert event.task_id == "t1"
    assert event.is_smart_notification is True


# ---------------------------------------------------------------------------
# Test 5: New WS client connecting mid-session receives current snapshot
# ---------------------------------------------------------------------------


def test_ws_second_client_receives_current_snapshot(tmp_path: Path) -> None:
    """A second WebSocket client connecting mid-session receives the current state."""
    state_path = tmp_path / "state.json"
    initial_state = make_state(tasks=[make_task("t-snap")])
    write_state(state_path, initial_state)

    app = create_app(state_path)

    with TestClient(app) as client:
        # Connect first client
        with client.websocket_connect("/ws") as ws1:
            snap1 = ws1.receive_text()
            data1 = json.loads(snap1)
            assert any(t["id"] == "t-snap" for t in data1["tasks"])

        # Connect second client (simulates mid-session reconnect)
        with client.websocket_connect("/ws") as ws2:
            snap2 = ws2.receive_text()
            data2 = json.loads(snap2)
            assert any(t["id"] == "t-snap" for t in data2["tasks"])


# ---------------------------------------------------------------------------
# Test 6: ConnectionManager dead-connection cleanup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connection_manager_removes_dead_connections(tmp_path: Path) -> None:
    """ConnectionManager.broadcast() removes connections that raise on send_text."""
    from unittest.mock import AsyncMock, MagicMock

    from conductor.dashboard.server import ConnectionManager

    manager = ConnectionManager()

    # Create a dead connection that raises on send_text
    dead_ws = MagicMock()
    dead_ws.send_text = AsyncMock(side_effect=RuntimeError("connection closed"))
    manager.active_connections.append(dead_ws)

    assert len(manager.active_connections) == 1
    await manager.broadcast("hello")
    # Dead connection should be removed
    assert dead_ws not in manager.active_connections
    assert len(manager.active_connections) == 0
