---
phase: 31-tui-foundation
plan: 01
subsystem: tui
tags: [textual, tui, event-loop, delegation, cli]
dependency_graph:
  requires: []
  provides: [tui-foundation, conductor-app, delegation-cleanup]
  affects: [cli-entry-point, delegation-manager]
tech_stack:
  added: [textual>=4.0, pytest-textual-snapshot>=0.4]
  patterns: [Textual App root, headless run_test() pilot, logger.info over console.print]
key_files:
  created:
    - packages/conductor-core/src/conductor/tui/__init__.py
    - packages/conductor-core/src/conductor/tui/app.py
    - packages/conductor-core/src/conductor/tui/messages.py
    - packages/conductor-core/src/conductor/tui/conductor.tcss
    - packages/conductor-core/tests/test_tui_foundation.py
  modified:
    - packages/conductor-core/pyproject.toml
    - packages/conductor-core/src/conductor/cli/__init__.py
    - packages/conductor-core/src/conductor/cli/delegation.py
    - packages/conductor-core/tests/test_phase22_visibility.py
    - packages/conductor-core/tests/test_delegation.py
decisions:
  - console=None kept as default in DelegationManager for backward compat with existing tests
  - STATUS_UPDATE_INTERVAL constant kept exported for backward compat (value, not method)
  - pick_session() import kept in cli/__init__.py for --resume flag
  - test_phase22_visibility.py updated to verify methods are ABSENT (not test them)
  - test_delegation.py updated to check logger.info instead of console.print for announcements
metrics:
  duration: 353s
  completed: "2026-03-11"
  tasks_completed: 3
  files_created: 5
  files_modified: 5
---

# Phase 31 Plan 01: TUI Foundation Summary

**One-liner:** Textual ConductorApp replaces asyncio.run() as sole event loop owner; delegation.py stripped of ANSI terminal manipulation.

## What Was Built

### Files Created

- **`conductor/tui/__init__.py`** — Empty module marker with docstring
- **`conductor/tui/app.py`** — ConductorApp Textual root with placeholder label, background task tracking (`_track_task`/`_background_tasks`), clean `action_quit()`, and skeleton `on_mount()`
- **`conductor/tui/messages.py`** — Internal event bus: `TokenChunk`, `ToolActivity`, `StreamDone`, `TokensUpdated`, `DelegationStarted`, `DelegationComplete`
- **`conductor/tui/conductor.tcss`** — Skeleton CSS layout (Screen, #app-body, #placeholder-label)
- **`tests/test_tui_foundation.py`** — 7 headless tests: app starts, app exits cleanly, no prompt_toolkit in tui imports, DelegationManager has no status/ANSI methods, DelegationManager constructable without console, no asyncio.run() in CLI, background task tracking

### Files Modified

- **`pyproject.toml`** — Added `textual>=4.0` to dependencies; `pytest-textual-snapshot>=0.4` to dev group
- **`cli/__init__.py`** — Removed `asyncio.run(_run_chat_with_dashboard(...))` and the entire `_run_chat_with_dashboard` async function; replaced with `ConductorApp(...).run()`; removed module-level `_console`
- **`cli/delegation.py`** — Deleted `_status_updater`, `_print_live_status`, `_clear_status_lines`, `_last_status_line_count`; replaced `console.print()` lifecycle calls with `logger.info()`; made `console` parameter optional (`console=None` default); kept `STATUS_UPDATE_INTERVAL` constant for backward compat
- **`tests/test_phase22_visibility.py`** — Replaced VISB-01 tests (which tested deleted methods) with tests that assert those methods are ABSENT; escalation bridge tests kept intact
- **`tests/test_delegation.py`** — Updated `test_delegation_announcement_printed` → `test_delegation_announcement_logged` to use `caplog` instead of checking `console.print`

## Key Decisions Made

1. **`console=None` kept for backward compat** — DelegationManager keeps console as optional first parameter; existing tests that pass a MagicMock console still work without modification (except the announcement test)
2. **`STATUS_UPDATE_INTERVAL` constant kept** — The value is imported by test_phase22_visibility.py; keeping it avoids a more invasive test change while the constant itself causes no harm
3. **`pick_session()` kept in cli/__init__.py** — Needed for `--resume` flag; import is lazy (inside callback body) so it doesn't pollute the TUI import chain
4. **No `asyncio.run()` anywhere in TUI path** — Verified by both static grep and Test 6
5. **`_run_chat_with_dashboard` fully deleted** — All uvicorn/ChatSession logic moves to `ConductorApp.on_mount()` incrementally in Phases 32-37

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DelegationManager constructor signature changed to maintain backward compat**

- **Found during:** Task 2 (GREEN phase) — existing tests pass `console=console, repo_path=...` as keyword args
- **Issue:** Plan said to change constructor to `(repo_path, console=None, ...)` but existing tests use `DelegationManager(console=..., repo_path=...)` positional-style kwargs
- **Fix:** Kept `console` as the first parameter but made it optional (`console: Console | None = None`); `repo_path` remains second with empty string default
- **Files modified:** `cli/delegation.py`

**2. [Rule 1 - Bug] test_phase22_visibility.py needed significant update**

- **Found during:** Task 2 (full suite check) — imported `STATUS_UPDATE_INTERVAL` and called deleted methods
- **Issue:** Phase 22 tests tested methods that were explicitly deleted in Phase 31; test file needed to be updated to verify the methods are gone, not test their behavior
- **Fix:** Rewrote VISB-01 section to assert methods are absent; kept escalation bridge tests; preserved integration tests
- **Files modified:** `tests/test_phase22_visibility.py`

**3. [Rule 1 - Bug] test_delegation.py announcement test used console.print**

- **Found during:** Task 2 (full suite check) — test checked `console.print` calls for "Delegating to team" which now goes to `logger.info`
- **Fix:** Renamed test to `test_delegation_announcement_logged`, switched to `caplog` fixture
- **Files modified:** `tests/test_delegation.py`

## Test Results

- **test_tui_foundation.py:** 7/7 passed
- **Full suite:** 585 passed (579 baseline + 6 new TUI foundation tests)
- **No regressions**

## Self-Check: PASSED

Files verified:
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/__init__.py` — EXISTS
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/app.py` — EXISTS
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/messages.py` — EXISTS
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/conductor.tcss` — EXISTS
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/tests/test_tui_foundation.py` — EXISTS

Commits verified:
- `22f3797` — feat(31-01): add textual dependency and tui module scaffold
- `80c1f4c` — feat(31-01): ConductorApp, delegation cleanup, CLI entry point rewire
- `ddd521f` — test(31-01): add runtime audit tests (Tests 6-7) to test_tui_foundation
