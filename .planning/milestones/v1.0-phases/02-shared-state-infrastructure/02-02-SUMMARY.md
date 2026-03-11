---
phase: 02-shared-state-infrastructure
plan: "02"
subsystem: state
tags: [python, filelock, pydantic, concurrency, atomic-write, tdd]

# Dependency graph
requires:
  - phase: 02-01
    provides: ConductorState, Task, AgentRecord, Dependency, TaskStatus models + StateError hierarchy
provides:
  - StateManager class with file-locked atomic read-modify-write (Pattern 1)
  - mutate() with FileLock(timeout=10s) + tempfile+fsync+os.replace atomic write
  - assign_task() and update_task_status() convenience mutation helpers
  - read_state() with StateCorrupted on parse failure, empty ConductorState on missing file
  - 8-test suite covering CORD-01, CORD-02, CORD-03, CORD-06
  - StateManager re-exported from conductor.state public API
affects:
  - 03-acp-layer (calls read_state() to observe task/agent status)
  - 04-orchestrator-core (calls assign_task() and update_task_status())

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pattern 1: FileLock(.json.lock) + read + mutate + _atomic_write (tempfile mkstemp in same dir, fsync, os.replace)"
    - "_spawn_write_tasks in installed package (not test module) for multiprocessing spawn pickle compatibility"
    - "Default FileLock timeout=10.0s (never -1) to prevent infinite deadlock"

key-files:
  created:
    - packages/conductor-core/src/conductor/state/manager.py
    - packages/conductor-core/tests/test_state.py
  modified:
    - packages/conductor-core/src/conductor/state/__init__.py

key-decisions:
  - "_spawn_write_tasks placed in conductor.state.manager (installed package) not tests/ — pytest importlib mode means spawned processes cannot find test modules"
  - "StateManager.mutate() updates state.updated_at after applying fn, before atomic write — ensures timestamp is always current"
  - "Lock file at state_path.with_suffix('.json.lock') — same directory as state.json guarantees same filesystem for os.replace"

# Metrics
duration: 8min
completed: 2026-03-10
---

# Phase 2 Plan 02: StateManager Summary

**File-locked atomic read-modify-write StateManager using FileLock + tempfile + fsync + os.replace, with concurrent write safety proven by 2-process x 10-task test**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-10T14:40:46Z
- **Completed:** 2026-03-10T14:49:00Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments

- Implemented `StateManager` class with `read_state()`, `mutate()`, `assign_task()`, `update_task_status()`, and `_atomic_write()` following research Pattern 1 exactly
- File locking via `FileLock` on `.json.lock` file (same directory as `state.json`) with 10s default timeout
- Atomic writes: `mkstemp(dir=state_path.parent)` → write → `fsync` → `os.replace` → temp cleanup on failure
- Concurrent write safety verified: 2 spawned processes each write 10 tasks, all 20 tasks survive with no corruption
- Cross-instance observation verified: separate `StateManager` instances pointing to same file see each other's changes
- All 8 tests pass; ruff and pyright report zero errors on the state module
- Full suite (37 tests including Plan 01 model tests) passes

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests for StateManager** - `de419da` (test)
2. **GREEN: Implement StateManager** - `b99809d` (feat)

_Note: Task used TDD — test commit (RED) followed by implementation commit (GREEN)._

## Files Created/Modified

- `packages/conductor-core/src/conductor/state/manager.py` - StateManager class with file-locked atomic read-modify-write + `_spawn_write_tasks` helper
- `packages/conductor-core/tests/test_state.py` - 8 tests covering CORD-01, 02, 03, 06 (task round-trip, concurrent writes, status updates, cross-instance observation, all-tasks visibility)
- `packages/conductor-core/src/conductor/state/__init__.py` - Added StateManager to public API re-exports

## Decisions Made

- Placed `_spawn_write_tasks` in the installed `conductor.state.manager` module rather than `tests/` — pytest's `--import-mode=importlib` means test modules are not on `sys.path` for spawned processes, which would cause `ModuleNotFoundError` when pickling the target for `multiprocessing.get_context("spawn")`.
- `mutate()` updates `state.updated_at` after the caller's `fn` runs, before the atomic write, ensuring the timestamp is always fresh.
- Lock file lives at `state_path.with_suffix(".json.lock")` in the same directory — guarantees same filesystem as `state.json`, which is required for `os.replace` to be atomic.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Moved worker function from test module to installed package**
- **Found during:** GREEN phase verification (concurrent test failed with `ModuleNotFoundError: No module named 'tests'`)
- **Issue:** The plan's instruction "module-level function for pickle compatibility with spawn" was necessary but not sufficient — pytest's `--import-mode=importlib` doesn't add `tests/` to `sys.path`, so spawned child processes cannot import from test modules
- **Fix:** Moved `_write_tasks_worker` into `conductor.state.manager` as `_spawn_write_tasks(state_path_str: str, ...)` with `state_path` as string (Path is not pickle-safe across modules); updated test to import and use `_spawn_write_tasks` from package
- **Files modified:** `packages/conductor-core/src/conductor/state/manager.py`, `packages/conductor-core/tests/test_state.py`
- **Commit:** b99809d (GREEN phase commit)

**2. [Rule 1 - Bug] Fixed ruff E402 / F401 violations during REFACTOR**
- **Found during:** GREEN phase ruff check — original draft placed `_spawn_write_tasks` before module-level imports, causing `E402 Module level import not at top of file` (8 violations) plus `F401 unused import` in the deferred import block
- **Fix:** Rewrote manager.py to put all imports at top and `_spawn_write_tasks` at bottom of file; moved datetime imports to top level
- **Files modified:** `packages/conductor-core/src/conductor/state/manager.py`
- **Committed in:** b99809d

---

**Total deviations:** 2 auto-fixed (Rule 1 — multiprocessing spawn path + lint violations)
**Impact on plan:** Both fixes were required for correctness/linting. No scope creep, no architectural change. The concurrent test now reliably passes in the project's pytest/uv environment.

## Issues Encountered

None blocking. The only unexpected work was the spawn-mode import path issue (well-documented Python multiprocessing limitation), resolved with a clean fix.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `StateManager` is the coordination primitive — all later phases use it
- Phase 3 (ACP Layer) can call `read_state()` to observe task/agent status
- Phase 4 (Orchestrator Core) can call `assign_task()` and `update_task_status()` for task lifecycle management
- No blockers for Phase 2 Plan 03 (if any) or Phase 3

---
*Phase: 02-shared-state-infrastructure*
*Completed: 2026-03-10*
