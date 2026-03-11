# Phase 9: Dashboard Backend - Research

**Researched:** 2026-03-11
**Domain:** FastAPI WebSocket server, file-watching state broadcaster, event filtering
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-04 | Dashboard sends smart notifications for key events (errors, completions, intervention needed) | Server-side event classification from `ConductorState` transitions: TaskStatus.FAILED = error, TaskStatus.COMPLETED = completion, AgentStatus.WAITING = intervention needed. FastAPI WebSocket broadcasts typed delta events. REST `/state` endpoint delivers full snapshot to late-joining clients. |
</phase_requirements>

---

## Summary

Phase 9 adds a FastAPI WebSocket server (`DashboardServer`) that runs inside the same asyncio event loop as the `Orchestrator` (or alongside it via `uvicorn.Server.serve()`). It watches `.conductor/state.json` for changes using `watchfiles.awatch`, computes deltas by comparing the previous snapshot to the new one, classifies events into "smart notification" categories (error, completion, intervention needed), and broadcasts typed delta JSON payloads to all connected WebSocket clients.

The architecture has two integration points: (1) a `GET /state` REST endpoint that returns the current full `ConductorState` as a JSON snapshot — this is the "catch-up" endpoint new clients call before subscribing to WebSocket updates, and (2) a `WebSocket /ws` endpoint that streams delta events as they happen. The state watcher runs as a `lifespan` background task so it starts and stops cleanly with the server. No ACP log content reaches the WebSocket — only typed delta events derived from state model changes.

The project already has all prerequisite infrastructure: `StateManager` in `conductor.state`, `ConductorState` Pydantic models with `TaskStatus` / `AgentStatus` enums, and the full orchestrator/CLI running on asyncio. FastAPI 0.135.1 + uvicorn 0.41.0 + watchfiles 1.1.1 are the only new direct dependencies. The `DashboardServer` should live in `packages/conductor-core/src/conductor/dashboard/` to keep it co-located with the Python core but physically separated from CLI code.

**Primary recommendation:** FastAPI with WebSocket `ConnectionManager`, `watchfiles.awatch` for file watching, lifespan background task for watcher, `uvicorn.Server.serve()` for programmatic startup alongside the orchestrator.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastapi | >=0.135 | HTTP + WebSocket server framework | ASGI-native, asyncio-first, built-in WebSocket support, Pydantic integration |
| uvicorn | >=0.41 | ASGI server — runs the FastAPI app | FastAPI's standard runtime; `uvicorn.Server.serve()` allows programmatic start inside running asyncio loop |
| watchfiles | >=1.1 | Async file watcher using Rust notify backend | `awatch()` is a native async generator — no polling thread, no blocking, works directly in asyncio tasks |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic (already installed) | >=2.10 | Delta event models for typed WebSocket payloads | Already a project dependency; extend for event types |
| asyncio (stdlib) | 3.12+ | Concurrency between watcher task and WebSocket handlers | Always — already used throughout the project |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| watchfiles.awatch | Polling loop (asyncio.sleep + read_state) | Polling works but wastes CPU and has latency proportional to poll interval; watchfiles uses OS filesystem events — instant notification |
| FastAPI WebSocket | SSE (Server-Sent Events) | SSE is simpler but unidirectional (server→client only). Phase 10 will need bidirectional intervention commands from dashboard, so WebSocket is the right investment now |
| uvicorn.Server.serve() | subprocess / separate process | Subprocess adds IPC complexity; same-process `serve()` shares the asyncio loop and state manager directly — no serialization needed |

**Installation:**
```bash
uv add --package conductor-core "fastapi>=0.135" "uvicorn>=0.41" "watchfiles>=1.1"
```

---

## Architecture Patterns

### Recommended Project Structure
```
packages/conductor-core/src/conductor/
├── dashboard/
│   ├── __init__.py          # exports DashboardServer
│   ├── server.py            # FastAPI app, lifespan, ConnectionManager, routes
│   ├── events.py            # DeltaEvent Pydantic models, event classification
│   └── watcher.py           # state_watcher() coroutine using awatch
```

The CLI `run.py` will be extended to optionally start the dashboard server alongside the orchestrator using `asyncio.gather`.

### Pattern 1: Lifespan Background Watcher
**What:** Start the `state_watcher` coroutine as an `asyncio.create_task` in the FastAPI `lifespan` function. The watcher runs for the application's entire lifetime, broadcasting deltas to connected clients.
**When to use:** Always — the watcher must start before any WebSocket clients connect.

```python
# Source: https://fastapi.tiangolo.com/advanced/events/
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    watcher_task = asyncio.create_task(state_watcher(app.state.manager, app.state.ws_manager))
    yield
    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
```

### Pattern 2: WebSocket ConnectionManager
**What:** A `ConnectionManager` class holds the list of active `WebSocket` connections and provides `broadcast(message: str)`. Each `/ws` connection is added on accept and removed on `WebSocketDisconnect`.
**When to use:** Every time a client connects to `/ws`.

```python
# Source: https://fastapi.tiangolo.com/advanced/websockets/
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

### Pattern 3: REST Snapshot + WebSocket Delta (Catch-Up Pattern)
**What:** New clients call `GET /state` to get the full current `ConductorState` as JSON, then connect to `/ws` for incremental delta events. This prevents missed events during the window between page load and WebSocket connection.
**When to use:** Required for DASH-04 success criterion 4: "A new WebSocket client connecting mid-session receives the full current state via REST before receiving incremental updates."

```python
from conductor.state.models import ConductorState

@app.get("/state")
async def get_state() -> dict:
    """Return full current ConductorState snapshot for new client catch-up."""
    state: ConductorState = await asyncio.to_thread(app.state.manager.read_state)
    return state.model_dump()
```

### Pattern 4: State Watcher with watchfiles.awatch
**What:** An async loop that watches the state file path. On each change, reads the new state, computes delta vs. previous state, classifies events, and broadcasts typed delta payloads.
**When to use:** Run as the lifespan background task.

```python
# Source: https://watchfiles.helpmanual.io/api/watch/
from watchfiles import awatch
from pathlib import Path

async def state_watcher(
    state_path: Path,
    ws_manager: ConnectionManager,
    stop_event: asyncio.Event,
) -> None:
    prev_state: ConductorState | None = None
    async for _changes in awatch(str(state_path.parent), stop_event=stop_event):
        manager = StateManager(state_path)
        try:
            new_state = await asyncio.to_thread(manager.read_state)
        except Exception:
            continue
        events = classify_delta(prev_state, new_state)
        for event in events:
            await ws_manager.broadcast(event.model_dump_json())
        prev_state = new_state
```

### Pattern 5: Programmatic uvicorn alongside Orchestrator
**What:** Use `uvicorn.Server(config).serve()` inside `asyncio.gather()` alongside the orchestrator coroutine. This runs Uvicorn in the same asyncio loop without spawning a subprocess.
**When to use:** When `--dashboard` flag is passed to `conductor run`.

```python
# Source: https://github.com/Kludex/uvicorn/discussions/2457
import uvicorn

async def _run_async_with_dashboard(description, *, auto, repo):
    config = uvicorn.Config(create_dashboard_app(state_manager), host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    orch_coro = orchestrator.run_auto(description) if auto else orchestrator.run(description)
    await asyncio.gather(server.serve(), orch_coro)
```

### Pattern 6: Server-Side Event Classification
**What:** Compare previous and new `ConductorState` to derive typed delta events. The server — not the client — decides what is a "smart notification."
**When to use:** Inside `state_watcher` on every state change.

```python
from enum import StrEnum
from pydantic import BaseModel

class EventType(StrEnum):
    TASK_ASSIGNED = "task_assigned"
    TASK_STATUS_CHANGED = "task_status_changed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"           # smart notification: error
    AGENT_REGISTERED = "agent_registered"
    AGENT_STATUS_CHANGED = "agent_status_changed"
    INTERVENTION_NEEDED = "intervention_needed"  # smart notification

class DeltaEvent(BaseModel):
    type: EventType
    task_id: str | None = None
    agent_id: str | None = None
    payload: dict = {}
    is_smart_notification: bool = False   # pre-flagged server-side

def classify_delta(prev: ConductorState | None, new: ConductorState) -> list[DeltaEvent]:
    """Diff prev→new state and return typed delta events with smart notification flags."""
    events: list[DeltaEvent] = []
    if prev is None:
        return events  # initial state — no delta

    prev_tasks = {t.id: t for t in prev.tasks}
    for task in new.tasks:
        old = prev_tasks.get(task.id)
        if old is None:
            events.append(DeltaEvent(type=EventType.TASK_ASSIGNED, task_id=task.id))
        elif old.status != task.status:
            event_type = EventType.TASK_STATUS_CHANGED
            is_notification = False
            if task.status == "completed":
                event_type = EventType.TASK_COMPLETED
                is_notification = True
            elif task.status == "failed":
                event_type = EventType.TASK_FAILED
                is_notification = True
            events.append(DeltaEvent(
                type=event_type, task_id=task.id,
                payload={"status": task.status},
                is_smart_notification=is_notification,
            ))

    prev_agents = {a.id: a for a in prev.agents}
    for agent in new.agents:
        old_a = prev_agents.get(agent.id)
        if old_a is None:
            events.append(DeltaEvent(type=EventType.AGENT_REGISTERED, agent_id=agent.id))
        elif old_a.status != agent.status:
            is_notification = agent.status == "waiting"  # WAITING = intervention needed
            events.append(DeltaEvent(
                type=EventType.INTERVENTION_NEEDED if is_notification else EventType.AGENT_STATUS_CHANGED,
                agent_id=agent.id,
                payload={"status": agent.status},
                is_smart_notification=is_notification,
            ))

    return events
```

### Anti-Patterns to Avoid
- **Blocking `read_state` in the watcher without `asyncio.to_thread`:** `StateManager.read_state()` uses file I/O — call it via `asyncio.to_thread` to keep the event loop unblocked. (The existing codebase already does this pattern in `orchestrator.py`.)
- **Sending full state on every change:** Defeats the purpose of delta streaming; overwhelms the client on large state files.
- **Watching the state file directly (not parent dir):** Some OS file watchers replace files atomically (os.replace) — watching the file inode misses events. Watch the parent directory and filter by filename.
- **Starting Uvicorn with `uvicorn.run()` from an already-running asyncio loop:** Use `uvicorn.Server(config).serve()` to avoid "event loop already running" errors.
- **Letting Phase 10 filter raw ACP logs client-side:** Classification must happen in the Phase 9 watcher — DASH-04 explicitly says "the client does not filter raw events."

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async file watching | Custom polling loop or threading.Observer | `watchfiles.awatch` | Rust notify backend gives instant OS events; awatch is an async generator — no thread pool management |
| WebSocket connection tracking | Custom dict + lock | FastAPI `ConnectionManager` (official docs pattern) | No broadcast race conditions with single-threaded asyncio; well-documented pattern |
| ASGI server startup | Custom HTTP/socket server | `uvicorn.Server(config).serve()` | Handles all ASGI lifecycle, graceful shutdown, HTTP/WebSocket upgrade |
| JSON delta serialization | Custom diff dict | Pydantic `DeltaEvent.model_dump_json()` | Consistent schema, type-safe, forward-compatible |

**Key insight:** watchfiles + FastAPI WebSocket together give instant file-change-to-WebSocket-push in ~5 lines of asyncio code. The complexity is in the delta classification logic, not the plumbing.

---

## Common Pitfalls

### Pitfall 1: Watching File vs. Directory
**What goes wrong:** `watchfiles.awatch(state_path)` misses changes when `os.replace()` atomically swaps the file (the inode changes, and the original file path event is a deletion, not a modification).
**Why it happens:** `StateManager._atomic_write()` uses `os.replace(tmp_path, state_path)` — the state file is replaced, not written in-place.
**How to avoid:** Watch the parent directory: `awatch(str(state_path.parent))` then check if `state_path.name` is in the changed filenames.
**Warning signs:** Watcher runs but never fires events during testing.

### Pitfall 2: Broadcasting During Disconnect
**What goes wrong:** `broadcast()` iterates `active_connections` while a disconnect handler removes from the same list. RuntimeError: list changed during iteration.
**Why it happens:** `WebSocketDisconnect` exception fires while broadcast is mid-iteration.
**How to avoid:** Iterate over a copy: `for conn in list(self.active_connections)`. Wrap individual `send_text` in try/except `WebSocketDisconnect` and clean up the dead connection.

### Pitfall 3: Initial State Race
**What goes wrong:** Client connects to `/ws`, then calls `GET /state`, and misses delta events that fired in the gap.
**Why it happens:** State changes between REST call and WebSocket subscription.
**How to avoid:** Document that clients must connect to `/ws` first (buffering incoming events), then call `GET /state` to get the snapshot, then start processing the buffered events. Alternatively, send the current state as the first WebSocket message on connection. The success criterion says "full current state via REST before receiving incremental updates" — the server should send current state immediately on WebSocket connect too (belt-and-suspenders).

### Pitfall 4: Uvicorn Log Noise in Test Output
**What goes wrong:** Tests that create a `DashboardServer` emit uvicorn access logs to stdout, polluting pytest output.
**Why it happens:** Uvicorn default `log_level="info"` logs every HTTP/WS request.
**How to avoid:** Set `log_level="warning"` or `log_level="critical"` in `uvicorn.Config` for tests.

### Pitfall 5: watchfiles debounce batches changes
**What goes wrong:** Multiple rapid state writes (orchestrator spawning 5 agents at once) get batched into a single awatch event. The watcher reads the latest state but may have missed intermediate transitions.
**Why it happens:** `watchfiles.awatch` default `debounce=1600ms` batches filesystem events within the window.
**How to avoid:** For Conductor's use case this is fine — we only need the latest snapshot. Use `debounce=200` to tighten the window if sub-second latency is required for the success criterion "within 1 second."

---

## Code Examples

### Full DashboardServer Module Sketch

```python
# packages/conductor-core/src/conductor/dashboard/server.py
# Source: official FastAPI + watchfiles docs
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from watchfiles import awatch

from conductor.state.manager import StateManager
from conductor.state.models import ConductorState
from conductor.dashboard.events import classify_delta, DeltaEvent


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        for conn in list(self.active_connections):
            try:
                await conn.send_text(message)
            except Exception:
                self.disconnect(conn)


def create_app(state_path: Path) -> FastAPI:
    ws_manager = ConnectionManager()
    state_manager = StateManager(state_path)
    stop_event = asyncio.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(
            _state_watcher(state_path, ws_manager, stop_event)
        )
        yield
        stop_event.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app = FastAPI(lifespan=lifespan)
    app.state.ws_manager = ws_manager
    app.state.state_manager = state_manager

    @app.get("/state")
    async def get_state() -> dict:
        state = await asyncio.to_thread(state_manager.read_state)
        return state.model_dump()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        # Send current state immediately so client doesn't miss events
        state = await asyncio.to_thread(state_manager.read_state)
        await websocket.send_text(state.model_dump_json())
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    return app


async def _state_watcher(
    state_path: Path,
    ws_manager: ConnectionManager,
    stop_event: asyncio.Event,
) -> None:
    manager = StateManager(state_path)
    prev: ConductorState | None = None
    async for changes in awatch(
        str(state_path.parent),
        stop_event=stop_event,
        debounce=200,
    ):
        changed_names = {Path(c[1]).name for c in changes}
        if state_path.name not in changed_names:
            continue
        try:
            new_state = await asyncio.to_thread(manager.read_state)
        except Exception:
            continue
        for event in classify_delta(prev, new_state):
            await ws_manager.broadcast(event.model_dump_json())
        prev = new_state
```

### CLI Integration (adding --dashboard flag to `conductor run`)

```python
# Extend packages/conductor-core/src/conductor/cli/commands/run.py
import uvicorn
from conductor.dashboard.server import create_app

async def _run_async(description, *, auto, repo, dashboard_port=None):
    # ... existing setup code ...
    coros = [orch_task, asyncio.gather(_display_loop(...), _input_loop(...))]
    if dashboard_port is not None:
        dashboard_app = create_app(conductor_dir / "state.json")
        config = uvicorn.Config(dashboard_app, host="127.0.0.1", port=dashboard_port, log_level="warning")
        server = uvicorn.Server(config)
        coros.append(server.serve())
    await asyncio.gather(*coros)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` decorator | `lifespan` asynccontextmanager | FastAPI 0.95.0 | Cleaner startup/shutdown; old `on_event` deprecated |
| `watchgod` package | `watchfiles` package | 2022 (watchfiles v0.14) | Same author; Rust backend; `awatch` is async-native |
| `uvicorn.run()` | `uvicorn.Server(config).serve()` | uvicorn ~0.17 | Allows running inside existing asyncio loop |

**Deprecated/outdated:**
- `@app.on_event("startup")`: deprecated since 0.95.0, use `lifespan` parameter instead.
- `watchgod`: superseded by `watchfiles`; maintainer explicitly says "use watchfiles."

---

## Open Questions

1. **Dashboard server port configuration**
   - What we know: uvicorn can bind to any port; `127.0.0.1:8000` is convention
   - What's unclear: Should the port be hardcoded, CLI flag, or config file?
   - Recommendation: Add `--dashboard-port` CLI flag defaulting to `8000`; document it

2. **Dashboard server enabled by default or opt-in?**
   - What we know: Adding `--dashboard` flag to `conductor run` is the cleanest integration
   - What's unclear: Phase 9 success criterion says "starts alongside Conductor" — could mean always-on
   - Recommendation: Opt-in via `--dashboard` / `--dashboard-port` flag; always-on is Phase 10 concern

3. **watchfiles filter performance on repos with many files**
   - What we know: `awatch` watches the entire `.conductor/` directory
   - What's unclear: Any performance impact from `.conductor/sessions.json` changes also triggering the watcher
   - Recommendation: Filter in the loop: only process changes where `Path(c[1]).name == "state.json"`

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio 0.23 |
| Config file | `packages/conductor-core/pyproject.toml` (existing `[tool.pytest.ini_options]`) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_dashboard.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-04 | GET /state returns current ConductorState JSON | unit | `pytest tests/test_dashboard.py::test_get_state -x` | ❌ Wave 0 |
| DASH-04 | WebSocket client receives delta event within 1s of state change | integration | `pytest tests/test_dashboard.py::test_ws_delta_on_state_change -x` | ❌ Wave 0 |
| DASH-04 | TASK_FAILED event has is_smart_notification=True | unit | `pytest tests/test_dashboard_events.py::test_classify_task_failed -x` | ❌ Wave 0 |
| DASH-04 | TASK_COMPLETED event has is_smart_notification=True | unit | `pytest tests/test_dashboard_events.py::test_classify_task_completed -x` | ❌ Wave 0 |
| DASH-04 | AgentStatus.WAITING triggers INTERVENTION_NEEDED smart notification | unit | `pytest tests/test_dashboard_events.py::test_classify_intervention_needed -x` | ❌ Wave 0 |
| DASH-04 | New WS client receives full state snapshot on connect | integration | `pytest tests/test_dashboard.py::test_ws_initial_state_on_connect -x` | ❌ Wave 0 |
| DASH-04 | classify_delta(None, state) returns empty list (no delta from nothing) | unit | `pytest tests/test_dashboard_events.py::test_classify_no_delta_on_none_prev -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_dashboard_events.py tests/test_dashboard.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_dashboard_events.py` — unit tests for `classify_delta`, `DeltaEvent` model, smart notification flags
- [ ] `tests/test_dashboard.py` — integration tests for REST and WebSocket endpoints using `httpx.AsyncClient` + `starlette.testclient`
- [ ] `packages/conductor-core/src/conductor/dashboard/__init__.py` — package scaffold
- [ ] `packages/conductor-core/src/conductor/dashboard/events.py` — `DeltaEvent`, `EventType`, `classify_delta`
- [ ] `packages/conductor-core/src/conductor/dashboard/server.py` — FastAPI app, `ConnectionManager`, `create_app`
- [ ] `packages/conductor-core/src/conductor/dashboard/watcher.py` — `_state_watcher` coroutine
- [ ] Install: `uv add --package conductor-core "fastapi>=0.135" "uvicorn>=0.41" "watchfiles>=1.1"`

---

## Sources

### Primary (HIGH confidence)
- [FastAPI official docs — WebSockets](https://fastapi.tiangolo.com/advanced/websockets/) — ConnectionManager pattern, WebSocketDisconnect handling, broadcast
- [FastAPI official docs — Lifespan Events](https://fastapi.tiangolo.com/advanced/events/) — `asynccontextmanager` lifespan, `asyncio.create_task` background watcher pattern
- [watchfiles PyPI](https://pypi.org/project/watchfiles/) — version 1.1.1 (2025-10-14), Python >=3.9
- [watchfiles API docs — awatch](https://watchfiles.helpmanual.io/api/watch/) — async generator signature, stop_event, debounce parameter
- [FastAPI PyPI](https://pypi.org/project/fastapi/) — version 0.135.1 (2026-03-01), Python >=3.10
- [uvicorn PyPI](https://pypi.org/project/uvicorn/) — version 0.41.0 (2026-02-16)

### Secondary (MEDIUM confidence)
- [testdriven.io — FastAPI + WebSockets real-time dashboard](https://testdriven.io/blog/fastapi-postgres-websockets/) — REST snapshot + WebSocket delta catch-up pattern
- [uvicorn discussions — running inside existing loop](https://github.com/Kludex/uvicorn/discussions/2457) — `uvicorn.Server.serve()` pattern for programmatic startup

### Tertiary (LOW confidence)
- None — all critical claims verified with official docs or PyPI.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — FastAPI/uvicorn/watchfiles all verified on PyPI with current versions
- Architecture: HIGH — patterns from official FastAPI docs; `uvicorn.Server.serve()` from official GitHub discussion
- Pitfalls: HIGH — awatch/os.replace interaction from understanding of StateManager._atomic_write(); broadcast race from FastAPI docs pattern
- Event classification: HIGH — derived directly from existing `ConductorState`, `TaskStatus`, `AgentStatus` enums in the codebase

**Research date:** 2026-03-11
**Valid until:** 2026-06-11 (stable ecosystem; FastAPI/uvicorn/watchfiles all mature)
