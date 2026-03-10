"""FastAPI dashboard server — REST and WebSocket endpoints for live state streaming.

Exposes:
  GET /state    — full ConductorState snapshot as JSON
  WS  /ws       — WebSocket stream of DeltaEvent JSON messages

On WebSocket connect, the client immediately receives a full state snapshot
(belt-and-suspenders against missed events during connection setup).
Subsequent messages are DeltaEvent JSON objects broadcast by the state watcher.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from conductor.dashboard.watcher import state_watcher
from conductor.state.manager import StateManager


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


def create_app(state_path: Path) -> FastAPI:
    """Create and configure the FastAPI dashboard application.

    Args:
        state_path: Path to state.json watched for changes.

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

    @app.get("/state")
    async def get_state() -> JSONResponse:
        """Return the current ConductorState as JSON."""
        state = await asyncio.to_thread(state_manager.read_state)
        return JSONResponse(content=state.model_dump(mode="json"))

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WebSocket endpoint — sends initial state snapshot, then delta events."""
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

            # Keep connection alive; watcher broadcasts will push events
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    return app


__all__ = ["ConnectionManager", "create_app"]
