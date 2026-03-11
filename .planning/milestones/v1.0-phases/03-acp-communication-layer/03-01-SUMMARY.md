---
phase: 03-acp-communication-layer
plan: 01
subsystem: acp
tags: [claude-agent-sdk, asyncio, permissions, timeout, pytest-asyncio]

requires:
  - phase: 02-shared-state-infrastructure
    provides: StateManager.read_state() used inside default answer function for context-aware responses

provides:
  - ACPError/SessionError/PermissionTimeoutError exception hierarchy in conductor.acp.errors
  - PermissionHandler class with handle() callback matching claude-agent-sdk can_use_tool signature
  - Default-allow for regular tool requests, AskUserQuestion routed to configurable answer_fn
  - Timeout enforcement via asyncio.wait_for — returns PermissionResultDeny on timeout (safe default)
  - Default answer_fn reads StateManager via asyncio.to_thread, returns "proceed" for all questions

affects: [04-orchestrator-core, 05-cli]

tech-stack:
  added:
    - claude-agent-sdk>=0.1.48 (production dependency)
    - pytest-asyncio>=0.23 (dev dependency)
  patterns:
    - asyncio.wait_for timeout wrapping for all permission callbacks (safe default = deny)
    - asyncio.to_thread for StateManager.read_state() inside async callbacks
    - asyncio_mode=auto in pytest config — no per-test markers needed
    - TYPE_CHECKING guard for StateManager import to avoid circular deps

key-files:
  created:
    - packages/conductor-core/src/conductor/acp/errors.py
    - packages/conductor-core/src/conductor/acp/permission.py
    - packages/conductor-core/tests/test_acp_permission.py
  modified:
    - packages/conductor-core/src/conductor/acp/__init__.py
    - packages/conductor-core/pyproject.toml

key-decisions:
  - "PermissionHandler uses asyncio.wait_for for all async decision logic — ensures no deadlock from unanswered sub-agent prompts"
  - "Default answer resolves to 'proceed' for all questions — orchestrator can override via answer_fn param"
  - "asyncio.TimeoutError replaced with builtin TimeoutError (UP041 ruff rule, Python 3.11+)"
  - "TaskStatus uses uppercase enum keys (PENDING not pending) — consistent with StrEnum convention from Phase 2"

patterns-established:
  - "ACP callbacks wrap async logic in asyncio.wait_for — all sub-agent callbacks must enforce timeout"
  - "StateManager reads inside async context always use asyncio.to_thread — never block event loop"
  - "Permission routing: AskUserQuestion -> answer_fn, everything else -> default-allow with input passthrough"

requirements-completed: [COMM-01, COMM-02]

duration: 3min
completed: 2026-03-10
---

# Phase 3 Plan 1: ACP Permission Handler Summary

**PermissionHandler with asyncio timeout enforcement, AskUserQuestion routing, and StateManager-aware default answers using claude-agent-sdk 0.1.48**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-10T15:42:15Z
- **Completed:** 2026-03-10T15:45:01Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- ACP error hierarchy (ACPError, SessionError, PermissionTimeoutError) providing unified catch handling for ACP failures
- PermissionHandler.handle() routes AskUserQuestion to answer_fn and all other tools to default-allow
- Timeout via asyncio.wait_for returns PermissionResultDeny (safe default) — prevents orchestrator deadlock on unanswered prompts
- Default answer_fn reads state via asyncio.to_thread, avoiding event loop blocking
- All 7 permission tests pass; full suite 44/44 green; lint, format, pyright all clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dependencies and create ACP error hierarchy + permission handler tests (RED)** - `17d48b7` (test)
2. **Task 2: Implement PermissionHandler (GREEN + REFACTOR)** - `e83dcba` (feat)

_Note: TDD tasks have separate RED (test) and GREEN (feat) commits._

## Files Created/Modified

- `packages/conductor-core/src/conductor/acp/errors.py` - ACPError, SessionError, PermissionTimeoutError exception hierarchy
- `packages/conductor-core/src/conductor/acp/permission.py` - PermissionHandler with can_use_tool callback, timeout enforcement, AskUserQuestion routing
- `packages/conductor-core/src/conductor/acp/__init__.py` - Public exports for ACP package
- `packages/conductor-core/tests/test_acp_permission.py` - 7 tests covering routing, timeout, question answering, state context
- `packages/conductor-core/pyproject.toml` - Added claude-agent-sdk and pytest-asyncio deps; asyncio_mode=auto

## Decisions Made

- asyncio.wait_for wraps all permission callbacks — safe default ensures no deadlock when sub-agents ask questions that go unanswered
- asyncio.to_thread for synchronous StateManager.read_state() — never block the event loop from an async callback
- asyncio.TimeoutError replaced with builtin TimeoutError (Python 3.11+ UP041 ruff convention used throughout this project)
- PermissionResultDeny returned on timeout, PermissionTimeoutError raised internally (informational, not propagated)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed TaskStatus enum case in RED test**
- **Found during:** Task 2 (GREEN phase, first test run)
- **Issue:** Test used `TaskStatus.pending` but the StrEnum key is `TaskStatus.PENDING` (uppercase convention from Phase 2)
- **Fix:** Changed to `TaskStatus.PENDING` in `test_answer_from_state_context`
- **Files modified:** `tests/test_acp_permission.py`
- **Verification:** All 7 tests pass after fix
- **Committed in:** `e83dcba` (Task 2 commit)

**2. [Rule 1 - Bug] Fixed ruff UP041 lint error in permission.py**
- **Found during:** Task 2 (lint check after GREEN)
- **Issue:** `asyncio.TimeoutError` should be replaced with builtin `TimeoutError` per UP041 rule enforced by project ruff config
- **Fix:** Changed `except asyncio.TimeoutError` to `except TimeoutError`; also fixed E501 line-too-long
- **Files modified:** `src/conductor/acp/permission.py`
- **Verification:** `ruff check` passes after fix
- **Committed in:** `e83dcba` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - bugs)
**Impact on plan:** Both fixes necessary for correctness and compliance with project lint config. No scope creep.

## Issues Encountered

None — implementation matched the plan design exactly.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- PermissionHandler exported from `conductor.acp` and ready for use by orchestrator session management
- Remaining blocker from STATE.md still applies: ClaudeSDKClient session management and interrupt semantics need validation against SDK 0.1.48 docs before Phase 3 Plan 2 implementation
- Full test suite (44 tests) green with no regressions

---
*Phase: 03-acp-communication-layer*
*Completed: 2026-03-10*
