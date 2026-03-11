---
phase: 09-dashboard-backend
plan: "02"
subsystem: api
tags: [fastapi, uvicorn, watchfiles, websocket, httpx, dashboard, streaming]

# Dependency graph
requires:
  - phase: 09-dashboard-backend-01
    provides: EventType, DeltaEvent, classify_delta — event classification module
  - phase: 02-shared-state-infrastructure
    provides: StateManager.read_state, ConductorState models
provides:
  - FastAPI app with GET /state (REST snapshot) and WebSocket /ws (delta stream)
  - ConnectionManager with broadcast and dead-connection cleanup
  - state_watcher coroutine using watchfiles.awatch on parent directory
  - CLI --dashboard-port flag that starts dashboard server alongside orchestrator
  - Integration tests for REST, WebSocket, and smart notification classification
affects:
  - 10-dashboard-frontend

# Tech tracking
tech-stack:
  added: [fastapi>=0.135, uvicorn>=0.41, watchfiles>=1.1, httpx>=0.27 (dev)]
  patterns:
    - "ConnectionManager pattern: accept/disconnect/broadcast with dead-connection cleanup on send error"
    - "Lifespan asynccontextmanager: create_task on enter, cancel+suppress(CancelledError) on exit"
    - "state_watcher watches parent directory (not file) for inode-swap safety with os.replace"
    - "asyncio.to_thread for all StateManager.read_state() calls — never block event loop"
    - "WebSocket sends full state snapshot as first message (belt-and-suspenders on connect)"

key-files:
  created:
    - packages/conductor-core/src/conductor/dashboard/server.py
    - packages/conductor-core/src/conductor/dashboard/watcher.py
    - packages/conductor-core/tests/test_dashboard.py
  modified:
    - packages/conductor-core/src/conductor/dashboard/__init__.py
    - packages/conductor-core/src/conductor/cli/commands/run.py
    - packages/conductor-core/pyproject.toml
    - uv.lock

key-decisions:
  - "Watch parent directory (not state_path directly) — watchfiles misses atomic os.replace inode swaps when watching the file itself"
  - "debounce=200ms on awatch — prevents burst processing when StateManager writes multiple times rapidly"
  - "broadcast iterates list(active_connections) copy — avoids mutation-during-iteration when disconnecting dead clients"
  - "uvicorn.Server.serve() added to asyncio.gather in _run_async — dashboard runs concurrently without blocking orchestrator"
  - "gather_extras list pattern — clean conditional task injection into gather without restructuring existing coroutines"

patterns-established:
  - "FastAPI lifespan manages background watcher task lifecycle"
  - "WebSocket endpoint: connect → send snapshot → receive loop → disconnect on WebSocketDisconnect"

requirements-completed: [DASH-04]

# Metrics
duration: 3min
completed: "2026-03-10"
---

# Phase 09 Plan 02: Dashboard Backend Server Summary

**FastAPI server with WebSocket delta streaming, file-watching state watcher, and CLI --dashboard-port integration wired into asyncio.gather**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-10T18:55:16Z
- **Completed:** 2026-03-10T18:58:26Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- FastAPI app `create_app(state_path)` with GET /state returning full ConductorState JSON and WebSocket /ws sending delta events via ConnectionManager
- `state_watcher` coroutine using `watchfiles.awatch` on parent directory with debounce=200ms, broadcasting `DeltaEvent` JSON on state changes
- CLI `--dashboard-port` flag starts `uvicorn.Server` in `asyncio.gather` alongside orchestrator; prints dashboard URL on startup
- 6 integration tests: REST snapshot, WebSocket initial state, broadcast delivery, smart notification classification, second-client snapshot, dead-connection cleanup

## Task Commits

Each task was committed atomically:

1. **Task 1: Install dependencies + create server and watcher modules** - `4ad5933` (feat)
2. **Task 2: Integration tests + CLI --dashboard flag wiring** - `5c2c919` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `packages/conductor-core/src/conductor/dashboard/server.py` — FastAPI app, ConnectionManager, create_app, GET /state, WebSocket /ws routes
- `packages/conductor-core/src/conductor/dashboard/watcher.py` — state_watcher coroutine using watchfiles.awatch
- `packages/conductor-core/src/conductor/dashboard/__init__.py` — updated to also export create_app, ConnectionManager
- `packages/conductor-core/tests/test_dashboard.py` — 6 integration tests for REST and WebSocket endpoints
- `packages/conductor-core/src/conductor/cli/commands/run.py` — --dashboard-port flag, uvicorn.Server in asyncio.gather
- `packages/conductor-core/pyproject.toml` — added fastapi, uvicorn, watchfiles, httpx (dev)
- `uv.lock` — updated lockfile

## Decisions Made

- Watch parent directory (not state_path directly): watchfiles misses atomic os.replace inode swaps when watching the file itself
- broadcast iterates `list(active_connections)` copy to avoid mutation-during-iteration when removing dead clients
- `gather_extras` list pattern cleanly injects the optional `server.serve()` coroutine into `asyncio.gather` without restructuring existing code

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed asyncio event loop error in test_ws_broadcast_delivers_delta_event**
- **Found during:** Task 2 (Integration tests)
- **Issue:** Test used `asyncio.get_event_loop().run_until_complete()` inside a sync test function — raises `RuntimeError: There is no current event loop` in Python 3.13
- **Fix:** Converted test to `@pytest.mark.asyncio` and used `AsyncMock` to directly exercise `ConnectionManager.broadcast()` — cleaner unit test that doesn't depend on TestClient's event loop
- **Files modified:** packages/conductor-core/tests/test_dashboard.py
- **Verification:** All 281 tests pass including the fixed test
- **Committed in:** `5c2c919` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Auto-fix necessary for Python 3.13 compatibility. Resulting test is a cleaner unit test for ConnectionManager.broadcast().

## Issues Encountered

None beyond the test asyncio fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Dashboard server backend complete; Phase 10 (React dashboard) can consume GET /state and WebSocket /ws
- `conductor run --dashboard-port 8000` starts the full stack (orchestrator + dashboard server)
- Smart notifications (TASK_FAILED, TASK_COMPLETED, INTERVENTION_NEEDED) flagged server-side via `is_smart_notification=True`

---
*Phase: 09-dashboard-backend*
*Completed: 2026-03-10*
