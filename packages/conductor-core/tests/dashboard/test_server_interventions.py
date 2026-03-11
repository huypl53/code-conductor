"""Tests for WebSocket intervention command handling in the dashboard server.

Tests verify that the backend correctly parses cancel/feedback/redirect commands
and routes them to the appropriate orchestrator methods.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

from conductor.dashboard.server import create_app
from conductor.state.models import ConductorState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_empty_state(state_path: Path) -> None:
    """Write a minimal valid state to disk."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = ConductorState()
    state_path.write_text(state.model_dump_json())


def make_mock_orchestrator() -> MagicMock:
    """Create a mock orchestrator with AsyncMock intervention methods."""
    orchestrator = MagicMock()
    orchestrator.cancel_agent = AsyncMock()
    orchestrator.inject_guidance = AsyncMock()
    return orchestrator


# ---------------------------------------------------------------------------
# Test 1: cancel action -> orchestrator.cancel_agent called
# ---------------------------------------------------------------------------


def test_ws_cancel_action_calls_cancel_agent(tmp_path: Path) -> None:
    """WebSocket receives cancel action -> orchestrator.cancel_agent called with agent_id."""
    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    mock_orch = make_mock_orchestrator()
    app = create_app(state_path, orchestrator=mock_orch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # Receive initial snapshot
            ws.receive_text()
            # Send cancel command
            ws.send_text(json.dumps({"action": "cancel", "agent_id": "a1"}))

    mock_orch.cancel_agent.assert_awaited_once_with("a1")


# ---------------------------------------------------------------------------
# Test 2: feedback action -> orchestrator.inject_guidance called with message
# ---------------------------------------------------------------------------


def test_ws_feedback_action_calls_inject_guidance(tmp_path: Path) -> None:
    """WebSocket receives feedback action -> orchestrator.inject_guidance called with message."""
    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    mock_orch = make_mock_orchestrator()
    app = create_app(state_path, orchestrator=mock_orch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
            ws.send_text(
                json.dumps(
                    {"action": "feedback", "agent_id": "a1", "message": "looks good"}
                )
            )

    mock_orch.inject_guidance.assert_called_once_with("a1", "looks good")


# ---------------------------------------------------------------------------
# Test 3: redirect action -> orchestrator.cancel_agent called with new instructions
# ---------------------------------------------------------------------------


def test_ws_redirect_action_calls_cancel_agent_with_new_spec(tmp_path: Path) -> None:
    """WebSocket receives redirect action -> orchestrator.cancel_agent called with new instructions."""
    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    mock_orch = make_mock_orchestrator()
    app = create_app(state_path, orchestrator=mock_orch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
            ws.send_text(
                json.dumps(
                    {
                        "action": "redirect",
                        "agent_id": "a1",
                        "message": "new instructions here",
                    }
                )
            )

    mock_orch.cancel_agent.assert_awaited_once_with("a1", new_instructions="new instructions here")


# ---------------------------------------------------------------------------
# Test 4: Malformed JSON -> no crash, connection stays alive
# ---------------------------------------------------------------------------


def test_ws_malformed_json_no_crash(tmp_path: Path) -> None:
    """WebSocket receives malformed JSON -> no crash, connection stays alive."""
    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    mock_orch = make_mock_orchestrator()
    app = create_app(state_path, orchestrator=mock_orch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
            # Send malformed JSON — should not crash
            ws.send_text("{not valid json!!!")
            # Connection still alive — can send another valid message
            ws.send_text(json.dumps({"action": "feedback", "agent_id": "a1", "message": "ok"}))

    # inject_guidance called from the second (valid) message
    mock_orch.inject_guidance.assert_called_once_with("a1", "ok")
    # cancel_agent not called
    mock_orch.cancel_agent.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5: orchestrator=None -> intervention messages silently ignored
# ---------------------------------------------------------------------------


def test_ws_orchestrator_none_messages_silently_ignored(tmp_path: Path) -> None:
    """create_app with orchestrator=None -> intervention messages silently ignored, no crash."""
    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    # Create app without orchestrator
    app = create_app(state_path)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            snapshot = ws.receive_text()
            # Send intervention command — should be silently ignored
            ws.send_text(json.dumps({"action": "cancel", "agent_id": "a1"}))

    # No exception means test passes
    data = json.loads(snapshot)
    assert "tasks" in data


# ---------------------------------------------------------------------------
# Test 6: Existing behavior unchanged — initial snapshot still sent
# ---------------------------------------------------------------------------


def test_ws_initial_snapshot_still_sent_with_orchestrator(tmp_path: Path) -> None:
    """create_app with orchestrator parameter still sends initial state snapshot."""
    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    mock_orch = make_mock_orchestrator()
    app = create_app(state_path, orchestrator=mock_orch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            snapshot_text = ws.receive_text()

    data = json.loads(snapshot_text)
    assert "tasks" in data
    assert "agents" in data
    assert "version" in data


# ---------------------------------------------------------------------------
# Test 7: pause action -> orchestrator.pause_for_human_decision called
# ---------------------------------------------------------------------------


def test_ws_pause_action_calls_pause_for_human_decision(tmp_path: Path) -> None:
    """WebSocket receives pause action -> orchestrator.pause_for_human_decision called."""
    import asyncio

    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    mock_orch = make_mock_orchestrator()
    mock_orch.pause_for_human_decision = AsyncMock()
    # Set up _human_out and _human_in so the pause branch does not skip
    mock_orch._human_out = asyncio.Queue()
    mock_orch._human_in = asyncio.Queue()
    app = create_app(state_path, orchestrator=mock_orch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
            ws.send_text(
                json.dumps(
                    {"action": "pause", "agent_id": "a1", "message": "question?"}
                )
            )

    mock_orch.pause_for_human_decision.assert_called_once()
    call_args = mock_orch.pause_for_human_decision.call_args
    assert call_args[1].get("agent_id") == "a1" or call_args[0][0] == "a1"
    # Question should be passed
    assert "question?" in str(call_args)


# ---------------------------------------------------------------------------
# Test 8: pause action with no queues -> silently skips, no crash
# ---------------------------------------------------------------------------


def test_ws_pause_action_no_queues_silently_skips(tmp_path: Path) -> None:
    """pause action when orchestrator._human_out is None silently skips, no crash."""
    state_path = tmp_path / "state.json"
    write_empty_state(state_path)

    mock_orch = make_mock_orchestrator()
    mock_orch.pause_for_human_decision = AsyncMock()
    mock_orch._human_out = None
    mock_orch._human_in = None
    app = create_app(state_path, orchestrator=mock_orch)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_text()
            ws.send_text(
                json.dumps(
                    {"action": "pause", "agent_id": "a1", "message": "question?"}
                )
            )

    # pause_for_human_decision should NOT be called when queues are None
    mock_orch.pause_for_human_decision.assert_not_called()
