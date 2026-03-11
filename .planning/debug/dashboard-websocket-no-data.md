---
status: awaiting_human_verify
trigger: "dashboard-websocket-no-data"
created: 2026-03-11T00:00:00Z
updated: 2026-03-11T00:02:00Z
---

## Current Focus

hypothesis: CONFIRMED AND FIXED - The default `conductor` command (chat TUI mode) did not start a WebSocket server. Added `--dashboard-port` option to the chat command so the FastAPI server starts alongside the TUI.
test: Read conductor CLI entry point, chat.py, run.py, and vite.config.ts; added flag; all 449 tests pass
expecting: User runs `conductor --dashboard-port 8000` from project dir, then `npm run dev` in dashboard package, and sees live data
next_action: Await user verification

## Symptoms

expected: Dashboard should connect to the running conductor and show task/agent status
actual: Dashboard loads but shows empty/disconnected state - no data displayed
errors: No specific error messages reported, dashboard renders but empty
reproduction: 1) Start conductor TUI from /home/huypham/code/todo-app 2) Start dashboard with npm run dev from project dir 3) Open dashboard in browser
started: Current issue, unclear if it ever worked

## Eliminated

(none yet)

## Evidence

- timestamp: 2026-03-11T00:01:00Z
  checked: packages/conductor-core/src/conductor/cli/__init__.py
  found: Default `conductor` command (no subcommand) runs `ChatSession(resume_session_id=...).run()` — a pure TUI REPL with no network server
  implication: Chat mode never starts any WebSocket/HTTP server

- timestamp: 2026-03-11T00:01:00Z
  checked: packages/conductor-core/src/conductor/cli/commands/run.py lines 99-115
  found: Dashboard WebSocket server is ONLY started inside `conductor run --dashboard-port <PORT>`. When `dashboard_port is not None`, it creates a FastAPI app and runs uvicorn.
  implication: The server is behind an optional CLI flag, not started by default in any mode

- timestamp: 2026-03-11T00:01:00Z
  checked: packages/conductor-dashboard/vite.config.ts
  found: Vite dev server proxies `/ws` -> `ws://127.0.0.1:8000` and `/state` -> `http://127.0.0.1:8000`. Port 8000 is hardcoded.
  implication: Dashboard dev mode requires the FastAPI server running at port 8000

- timestamp: 2026-03-11T00:01:00Z
  checked: packages/conductor-dashboard/src/App.tsx getWsUrl()
  found: In dev mode (no `window.__CONDUCTOR_BACKEND_URL__`), connects to same-origin `/ws` — which goes through the Vite proxy to port 8000.
  implication: For dashboard to work in dev, FastAPI must run on port 8000

- timestamp: 2026-03-11T00:01:00Z
  checked: packages/conductor-core/src/conductor/cli/chat.py ChatSession
  found: Chat TUI handles delegation via DelegationManager, uses a .conductor/state.json path under cwd. No mention of dashboard server.
  implication: The chat TUI does write state.json (via orchestrator/delegation), but exposes no server

## Resolution

root_cause: The `conductor` default chat command does not start a WebSocket/HTTP dashboard server. The dashboard server only starts when `conductor run --dashboard-port <PORT>` is used. Since the user ran the bare `conductor` command (chat TUI), no server was listening on port 8000, so the dashboard finds nothing to connect to.
fix: Added `--dashboard-port` option to the `conductor` default (chat) command in `packages/conductor-core/src/conductor/cli/__init__.py`. When provided, starts a FastAPI/uvicorn server on that port alongside the chat session, then gracefully shuts it down when the chat exits.
verification: All 449 existing tests pass. `conductor --help` shows the new flag correctly.
files_changed:
  - packages/conductor-core/src/conductor/cli/__init__.py
