---
phase: 03-acp-communication-layer
plan: 02
subsystem: acp
tags: [claude-agent-sdk, asyncio, session-management, context-manager, streaming, hooks]

requires:
  - phase: 03-acp-communication-layer
    plan: 01
    provides: PermissionHandler.handle() callback and ACPError/SessionError hierarchy consumed by ACPClient

provides:
  - ACPClient async context manager wrapping ClaudeSDKClient for sub-agent session lifecycle
  - PreToolUse keepalive hook always registered alongside can_use_tool (mandatory SDK quirk)
  - PermissionHandler.handle wired as can_use_tool callback
  - SessionError raised when send/stream called after context manager exits
  - stream_response() async generator yielding sub-agent messages in real time
  - interrupt() method for future Phase 6 task cancellation

affects: [04-orchestrator-core, 05-cli]

tech-stack:
  added: []
  patterns:
    - ACPClient as async context manager — enter creates SDK client, exit closes and sets _closed flag
    - PreToolUse keepalive hook (SyncHookJSONOutput) always paired with can_use_tool — undocumented SDK requirement
    - TYPE_CHECKING guard for PermissionHandler import to avoid circular deps
    - list[SettingSource] cast for ["project"] literal — pyright-correct without runtime overhead

key-files:
  created:
    - packages/conductor-core/src/conductor/acp/client.py
    - packages/conductor-core/tests/test_acp_client.py
  modified:
    - packages/conductor-core/src/conductor/acp/__init__.py

key-decisions:
  - "ACPClient uses _closed flag set in __aexit__ finally block — ensures flag is set even if disconnect raises"
  - "SyncHookJSONOutput(continue_=True) used for keepalive return type — satisfies pyright HookJSONOutput union type check"
  - "setting_sources parameter typed as list[SettingSource] not list[str] — enforces SDK type contract at call site"
  - "Test bound method equality uses == not is — Python recreates bound method objects on each attribute access"

patterns-established:
  - "ACPClient wraps SDK lifecycle: __aenter__ creates+enters SDK, __aexit__ exits+sets _closed in finally"
  - "PreToolUse keepalive hook is mandatory SDK companion to can_use_tool — always register both or neither"
  - "Mock SDK context managers in tests via CapturingConstructor pattern — captures ClaudeAgentOptions before async entry"

requirements-completed: [COMM-01, COMM-02]

duration: 4min
completed: 2026-03-10
---

# Phase 3 Plan 2: ACPClient Summary

**ACPClient async context manager wrapping ClaudeSDKClient with session lifecycle, PreToolUse keepalive hook, PermissionHandler integration, and streaming — all SDK interactions mocked in 11 tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-10T15:47:43Z
- **Completed:** 2026-03-10T15:51:56Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- ACPClient wraps ClaudeSDKClient as async context manager — opens on enter, closes on exit, raises SessionError after close
- PreToolUse keepalive hook (SyncHookJSONOutput) always registered when permission_handler is provided — prevents silent SDK failures
- PermissionHandler.handle wired as can_use_tool callback with correct bound method equality semantics
- stream_response() async generator yields all messages from receive_response() in real time
- All 11 ACPClient tests pass; full suite 55/55 green; ruff lint + pyright clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ACPClient tests (RED)** - `33778e1` (test)
2. **Task 2: Implement ACPClient and update package exports (GREEN + REFACTOR)** - `d226e78` (feat)

_Note: TDD tasks have separate RED (test) and GREEN (feat) commits._

## Files Created/Modified

- `packages/conductor-core/src/conductor/acp/client.py` - ACPClient class with session lifecycle, streaming, options wiring
- `packages/conductor-core/tests/test_acp_client.py` - 11 tests covering lifecycle, streaming, and options (all mocked)
- `packages/conductor-core/src/conductor/acp/__init__.py` - Added ACPClient to public exports

## Decisions Made

- `_closed` flag set in `__aexit__` `finally` block — guarantees flag is set even if SDK disconnect raises an exception
- `SyncHookJSONOutput(continue_=True)` used for keepalive — correct return type satisfying pyright's `HookJSONOutput` union check (not a plain `dict`)
- `setting_sources` parameter typed as `list[SettingSource]` rather than `list[str]` — enforces SDK contract at call site, avoids cast gymnastics inside `__init__`
- Bound method equality in test uses `==` not `is` — Python creates new bound method objects on each attribute access, so `handler.handle is handler.handle` is `False`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed bound method identity check in test**
- **Found during:** Task 2 (GREEN phase, first test run)
- **Issue:** `assert options.can_use_tool is handler.handle` failed because Python creates a new bound method object on each attribute access — `handler.handle is handler.handle` is always `False`
- **Fix:** Captured `handle_ref = handler.handle` before patching, then used `assert options.can_use_tool == handle_ref` (equality compares the underlying function + instance)
- **Files modified:** `tests/test_acp_client.py`
- **Verification:** All 11 tests pass after fix
- **Committed in:** `d226e78` (Task 2 commit)

**2. [Rule 1 - Bug] Fixed ruff E501 line-too-long in client.py**
- **Found during:** Task 2 (lint check after GREEN)
- **Issue:** Two lines exceeding 88-char limit in `ClaudeAgentOptions` construction
- **Fix:** Extracted `resolved_tools` and `resolved_sources` local variables
- **Files modified:** `src/conductor/acp/client.py`
- **Verification:** `ruff check` passes after fix
- **Committed in:** `d226e78` (Task 2 commit)

**3. [Rule 1 - Bug] Fixed pyright type errors for SyncHookJSONOutput return and SettingSource typing**
- **Found during:** Task 2 (pyright check after lint)
- **Issue 1:** Keepalive returning `dict[str, bool]` not assignable to `HookJSONOutput` union — required `SyncHookJSONOutput` TypedDict
- **Issue 2:** `list[str]` not assignable to `list[SettingSource]` (invariant list type) — fixed by typing parameter as `list[SettingSource]`
- **Fix:** Changed keepalive return to `SyncHookJSONOutput(continue_=True)`, changed parameter type annotation to `list[SettingSource] | None`
- **Files modified:** `src/conductor/acp/client.py`
- **Verification:** `pyright` reports 0 errors after fix
- **Committed in:** `d226e78` (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 - bugs)
**Impact on plan:** All auto-fixes necessary for correctness and compliance with project type-check config. No scope creep.

## Issues Encountered

None — implementation matched the plan design exactly after the auto-fixes above.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- ACPClient exported from `conductor.acp` and ready for use by orchestrator session management (Phase 4)
- Full test suite (55 tests) green with no regressions
- Blocker from STATE.md resolved: ClaudeSDKClient session management and interrupt semantics validated against SDK 0.1.48 during implementation

---
*Phase: 03-acp-communication-layer*
*Completed: 2026-03-10*
