---
phase: 04-orchestrator-core
plan: "02"
subsystem: orchestrator
tags: [graphlib, topological-sort, dependency-scheduling, file-ownership, tdd]

# Dependency graph
requires:
  - phase: 04-orchestrator-core plan 01
    provides: CycleError and FileConflictError error classes in orchestrator/errors.py
provides:
  - DependencyScheduler class wrapping graphlib.TopologicalSorter (CORD-04)
  - validate_file_ownership function for pre-spawn conflict detection (CORD-05)
  - 21 unit tests covering all wave/cycle/conflict scenarios
affects:
  - 04-orchestrator-core plan 03 (Orchestrator class uses DependencyScheduler and validate_file_ownership)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "graphlib.TopologicalSorter as stdlib DAG scheduler — prepare()/get_ready()/done()/is_active() protocol"
    - "Pairwise O(n^2) ownership conflict check as pre-spawn static validation gate"
    - "TDD RED-GREEN-REFACTOR: tests committed before implementation"

key-files:
  created:
    - packages/conductor-core/src/conductor/orchestrator/scheduler.py
    - packages/conductor-core/src/conductor/orchestrator/ownership.py
    - packages/conductor-core/tests/test_scheduler.py
    - packages/conductor-core/tests/test_file_ownership.py
  modified:
    - packages/conductor-core/src/conductor/orchestrator/__init__.py

key-decisions:
  - "DependencyScheduler accepts dict[str, set[str]] graph (not TaskSpec list) — decouples from Pydantic model, orchestrator builds graph at wire-up time"
  - "validate_file_ownership accepts list[(task_id, target_file)] tuples — same decoupling rationale, avoids coupling to TaskSpec before Plan 03 wires it"
  - "CycleError cycle list extracted from GraphCycleError.args[1] — enables graph debug output per Plan 01 decision"

patterns-established:
  - "Pattern: DependencyScheduler — graphlib.TopologicalSorter wrapper with prepare() in __init__; CycleError raised at construction time not at get_ready()"
  - "Pattern: validate_file_ownership — build ownership dict then pairwise scan; raise FileConflictError with structured task_a/task_b/files on first overlap found"

requirements-completed: [CORD-04, CORD-05]

# Metrics
duration: 2min
completed: 2026-03-10
---

# Phase 4 Plan 02: Dependency Scheduler and File Ownership Summary

**graphlib-backed DependencyScheduler with wave-ready protocol and pairwise file-ownership conflict detection with FileConflictError on overlap**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-10T16:16:13Z
- **Completed:** 2026-03-10T16:18:00Z
- **Tasks:** 2 features (TDD: RED + GREEN for each)
- **Files modified:** 5

## Accomplishments
- DependencyScheduler wraps graphlib.TopologicalSorter: ready/done/is_active protocol, CycleError on circular deps
- validate_file_ownership pairwise-checks (task_id, target_file) tuples, raises structured FileConflictError with task_a/task_b/files
- 21 tests pass covering diamond deps, 3-task conflict scenarios, self-cycles, empty graphs, sequential chains
- Both new modules exported from orchestrator public API in __init__.py

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests for DependencyScheduler and validate_file_ownership** - `cd8bcc5` (test)
2. **GREEN: DependencyScheduler and validate_file_ownership implementation** - `d09f2e2` (feat)
3. **Orchestrator __init__.py public API export** - `a083cdc` (feat)

## Files Created/Modified
- `packages/conductor-core/src/conductor/orchestrator/scheduler.py` - DependencyScheduler wrapping graphlib.TopologicalSorter
- `packages/conductor-core/src/conductor/orchestrator/ownership.py` - validate_file_ownership with FileConflictError
- `packages/conductor-core/tests/test_scheduler.py` - 13 CORD-04 tests (wave readiness, sequencing, diamond, cycles)
- `packages/conductor-core/tests/test_file_ownership.py` - 8 CORD-05 tests (no conflict, conflict detection, 3-task scenario)
- `packages/conductor-core/src/conductor/orchestrator/__init__.py` - Added DependencyScheduler and validate_file_ownership to public API

## Decisions Made
- DependencyScheduler accepts `dict[str, set[str]]` rather than `list[TaskSpec]` — decouples from Pydantic model; orchestrator builds the graph at wire-up time in Plan 03
- validate_file_ownership accepts `list[tuple[str, str]]` (task_id, target_file) for the same decoupling reason
- Both modules available directly via `from conductor.orchestrator import DependencyScheduler, validate_file_ownership`

## Deviations from Plan

None - plan executed exactly as written. errors.py (CycleError, FileConflictError) was already created by Plan 01 as expected.

## Issues Encountered
None.

## Next Phase Readiness
- DependencyScheduler and validate_file_ownership are ready for Plan 03 (Orchestrator class) to consume
- The dict-based graph interface means Plan 03 needs to build `{task_id: set(task.requires)}` from TaskSpec list before constructing DependencyScheduler
- The tuple-based ownership interface means Plan 03 needs to build `[(task.id, task.target_file) for task in tasks]` list

---
*Phase: 04-orchestrator-core*
*Completed: 2026-03-10*
