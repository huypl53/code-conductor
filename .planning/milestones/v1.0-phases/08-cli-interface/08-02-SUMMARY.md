---
phase: 08-cli-interface
plan: "02"
subsystem: cli
tags: [asyncio, rich, cli, input-loop, interactive, orchestrator, tdd]

requires:
  - phase: 08-cli-interface
    plan: "01"
    provides: "_display_loop, _build_table, asyncio.gather skeleton in run.py"
  - phase: 06-escalation-and-intervention
    provides: "HumanQuery dataclass, human_out/human_in asyncio.Queue pattern"
  - phase: 04-orchestrator-core
    provides: "Orchestrator.cancel_agent, Orchestrator.inject_guidance"

provides:
  - Async _input_loop concurrent with orchestrator execution (asyncio.wait FIRST_COMPLETED)
  - _dispatch_command routing cancel/feedback/redirect/status/quit commands
  - Human question pump: HumanQuery from human_out displayed at terminal, answer put to human_in
  - conductor run --interactive fully wired with bidirectional communication

affects:
  - 09-dashboard-backend (CLI is primary entry point; input loop pattern documented)

tech-stack:
  added: []
  patterns:
    - TDD (RED tests before GREEN implementation)
    - asyncio.wait FIRST_COMPLETED to race terminal input vs. queue events
    - Console(stderr=True) for input loop to avoid corrupting Rich Live on stdout
    - asyncio.Queue[HumanQuery] and asyncio.Queue[str] typed generics for type safety

key-files:
  created:
    - packages/conductor-core/src/conductor/cli/input_loop.py
  modified:
    - packages/conductor-core/src/conductor/cli/commands/run.py
    - packages/conductor-core/tests/test_cli.py

key-decisions:
  - "_ainput uses asyncio.to_thread(input) — asyncio.to_thread(input) cannot be cancelled from Python (thread blocks until Enter), gather CancelledError handles coroutine cleanup"
  - "asyncio.wait FIRST_COMPLETED races input_task vs queue_task — prevents blocking on one while the other has data"
  - "Console(stderr=True) for input loop — avoids corrupting Rich Live table rendered on stdout"
  - "HumanQuery imported in input_loop.py for typed Queue[HumanQuery] — eliminates pyright reportAttributeAccessIssue on .question"
  - "_input_loop patched in test_run_interactive_routes_input — prevents stdin reads in pytest captured output mode"

metrics:
  duration: 4min
  completed: "2026-03-11"
  tasks: 2
  files: 3
---

# Phase 8 Plan 02: Interactive Input Loop Summary

**Async _dispatch_command routing cancel/feedback/redirect/status/quit plus asyncio.wait FIRST_COMPLETED loop pumping HumanQuery events to the terminal — wired into run command's asyncio.gather for full bidirectional CLI**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-10T18:28:15Z
- **Completed:** 2026-03-11
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Built `_input_loop` using `asyncio.wait(FIRST_COMPLETED)` pattern to concurrently race terminal input against `HumanQuery` events from `human_out` queue
- Implemented `_dispatch_command` routing five commands: `cancel`, `feedback`, `redirect`, `status`, `quit/exit` — each calling the appropriate orchestrator method with confirmation output
- Added human question pump: `HumanQuery` objects printed at terminal with `[bold yellow]Agent question:[/]` prefix; user answer collected and put to `human_in`
- Wired `_input_loop` into `asyncio.gather` in `commands/run.py` alongside `_display_loop` and `orch_task`
- Typed queue generics as `asyncio.Queue[HumanQuery]` / `asyncio.Queue[str]` for pyright correctness

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for _dispatch_command** - `6f7bba9` (test)
2. **Task 1 GREEN: input_loop module implementation** - `a15d1b1` (feat)
3. **Task 2: Wire _input_loop into run command gather** - `8b25e20` (feat)
4. **Task 2 fix: ruff/pyright lint corrections** - `5a21c74` (fix)

_Note: Task 1 used TDD — test commit precedes implementation commit._

## Files Created/Modified

- `packages/conductor-core/src/conductor/cli/input_loop.py` — `_ainput`, `_dispatch_command`, `_input_loop` with full command routing and human question pump
- `packages/conductor-core/src/conductor/cli/commands/run.py` — `_input_loop` added to `asyncio.gather`, `Console(stderr=True)` for input loop, typed queue generics
- `packages/conductor-core/tests/test_cli.py` — 5 new dispatch tests + `_input_loop` patch in routing test

## Decisions Made

- Used `asyncio.wait(FIRST_COMPLETED)` instead of `asyncio.create_task` racing with a direct await — correctly handles two competing async sources without blocking
- `Console(stderr=True)` passed explicitly to `_input_loop` — confirmation messages, agent questions, and errors appear on stderr, never interfering with the Rich Live table on stdout
- `asyncio.to_thread(input)` thread cannot be cancelled — documented with comment in run.py; acceptable for CLI (process exits)
- Patched `_input_loop` in existing routing test — clean fix, test focuses on Orchestrator mode routing not stdin behavior

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pyright type error: Queue[object] missing .question attribute**
- **Found during:** Task 2 (pyright check)
- **Issue:** `human_out: asyncio.Queue[object]` caused `reportAttributeAccessIssue` when accessing `query.question`
- **Fix:** Imported `HumanQuery` in `input_loop.py`, typed `human_out: asyncio.Queue[HumanQuery]` and `human_in: asyncio.Queue[str]`; mirrored in `run.py`
- **Files modified:** `input_loop.py`, `run.py`
- **Commit:** `5a21c74`

**2. [Rule 1 - Bug] Fixed ruff E501: line too long in _dispatch_command**
- **Found during:** Task 2 (ruff check)
- **Issue:** f-string on single line exceeded 88 char limit
- **Fix:** Split into two string parts (f-string prefix + literal continuation)
- **Files modified:** `input_loop.py`
- **Commit:** `5a21c74`

**3. [Rule 2 - Missing] Added _input_loop patch to existing routing test**
- **Found during:** Task 2 (test run)
- **Issue:** `test_run_interactive_routes_input` tried to read stdin when `_input_loop` was added to gather
- **Fix:** Added `patch("conductor.cli.commands.run._input_loop", new=AsyncMock(return_value=None))` to existing `with` block
- **Files modified:** `tests/test_cli.py`
- **Commit:** `8b25e20`

---

**Total deviations:** 3 auto-fixed (Rules 1, 1, 2)
**Impact on plan:** All minor correctness/type fixes. No scope creep.

## Issues Encountered

- `asyncio.Queue[object]` typing caused pyright error on `.question` access — fixed by importing and using concrete `HumanQuery` type
- pytest stdin capture raised `OSError` when `_input_loop` joined `asyncio.gather` — fixed by patching `_input_loop` in the routing test

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `conductor run "description" --interactive` is fully functional: displays agent table, accepts typed commands, pumps agent questions to terminal
- Plan 03 (if any) or Phase 9 (dashboard backend) can use `_build_table` and the established asyncio patterns
- All 260 tests pass, ruff clean, pyright clean

## Self-Check: PASSED

All files verified present:
- packages/conductor-core/src/conductor/cli/input_loop.py
- packages/conductor-core/src/conductor/cli/commands/run.py
- packages/conductor-core/tests/test_cli.py
- .planning/phases/08-cli-interface/08-02-SUMMARY.md

All commits verified:
- 6f7bba9 (TDD RED: failing dispatch tests)
- a15d1b1 (TDD GREEN: input_loop implementation)
- 8b25e20 (wire _input_loop into run command)
- 5a21c74 (ruff/pyright fixes)

---
*Phase: 08-cli-interface*
*Completed: 2026-03-11*
