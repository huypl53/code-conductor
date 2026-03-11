"""FastAPI dashboard server — REST and WebSocket endpoints for live state streaming.

Exposes:
  GET /state    — full ConductorState snapshot as JSON
  WS  /ws       — WebSocket stream of DeltaEvent JSON messages

On WebSocket connect, the client immediately receives a full state snapshot
(belt-and-suspenders against missed events during connection setup).
Subsequent messages are DeltaEvent JSON objects broadcast by the state watcher.

WebSocket also accepts incoming intervention commands (JSON with action/agent_id)
and routes them to the orchestrator when provided.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from conductor.dashboard.watcher import state_watcher
from conductor.state.manager import StateManager

if TYPE_CHECKING:
    from conductor.orchestrator.orchestrator import Orchestrator

logger = logging.getLogger("conductor.dashboard.server")


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages to all clients."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and track it."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket from the active connections list."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        """Send message to all connected clients; remove dead connections on error."""
        dead: list[WebSocket] = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.disconnect(connection)


async def handle_intervention(data: str, orchestrator: Orchestrator) -> None:
    """Parse and route an incoming intervention command to the orchestrator.

    Args:
        data: Raw JSON string received from WebSocket.
        orchestrator: Orchestrator instance to route commands to.
    """
    try:
        command = json.loads(data)
    except json.JSONDecodeError:
        return  # Silently ignore malformed JSON

    action = command.get("action")
    agent_id = command.get("agent_id")

    if not isinstance(action, str) or not isinstance(agent_id, str):
        return  # Missing or invalid required fields

    try:
        if action == "cancel":
            await orchestrator.cancel_agent(agent_id)
        elif action == "feedback":
            message = command.get("message", "")
            await orchestrator.inject_guidance(agent_id, message)
        elif action == "redirect":
            message = command.get("message", "")
            await orchestrator.cancel_agent(agent_id, new_instructions=message)
        elif action == "pause":
            question = command.get("message", "pause requested from dashboard")
            if orchestrator._human_out is not None and orchestrator._human_in is not None:
                await orchestrator.pause_for_human_decision(
                    agent_id, question, orchestrator._human_out, orchestrator._human_in
                )
    except Exception:
        logger.exception("Error handling intervention command action=%s agent=%s", action, agent_id)


def create_app(state_path: Path, orchestrator: Orchestrator | None = None) -> FastAPI:
    """Create and configure the FastAPI dashboard application.

    Args:
        state_path: Path to state.json watched for changes.
        orchestrator: Optional orchestrator instance for routing intervention commands.
                      When None, incoming WebSocket messages are silently ignored.

    Returns:
        Configured FastAPI app with lifespan (state watcher task).
    """
    ws_manager = ConnectionManager()
    state_manager = StateManager(state_path)
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[type-arg]
        watcher_task = asyncio.create_task(
            state_watcher(state_path, ws_manager, stop_event)
        )
        yield
        stop_event.set()
        watcher_task.cancel()
        with suppress(asyncio.CancelledError):
            await watcher_task

    app = FastAPI(title="Conductor Dashboard", lifespan=lifespan)
    app.state.ws_manager = ws_manager
    app.state.state_manager = state_manager
    app.state.orchestrator = orchestrator

    @app.get("/state")
    async def get_state() -> JSONResponse:
        """Return the current ConductorState as JSON."""
        state = await asyncio.to_thread(state_manager.read_state)
        return JSONResponse(content=state.model_dump(mode="json"))

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint — sends initial state snapshot, then delta events.

        Also accepts intervention commands (JSON with action/agent_id) from the
        dashboard client and routes them to the orchestrator.
        """
        await ws_manager.connect(websocket)
        try:
            # Send full current state as first message (belt-and-suspenders)
            try:
                current_state = await asyncio.to_thread(state_manager.read_state)
                await websocket.send_text(
                    current_state.model_dump_json()
                )
            except Exception:
                pass

            # Keep connection alive; watcher broadcasts will push events.
            # Route incoming messages to orchestrator if available.
            while True:
                data = await websocket.receive_text()
                if app.state.orchestrator is not None:
                    await handle_intervention(data, app.state.orchestrator)
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    return app


__all__ = ["ConnectionManager", "create_app"]
