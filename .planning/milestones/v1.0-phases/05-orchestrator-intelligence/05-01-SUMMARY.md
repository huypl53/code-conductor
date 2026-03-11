---
phase: 05-orchestrator-intelligence
plan: "01"
subsystem: orchestrator
tags: [claude-agent-sdk, pydantic, streaming, review, tdd, pytest]

# Dependency graph
requires:
  - phase: 04-orchestrator-core
    provides: OrchestratorError hierarchy, Task model, ACPClient, orchestrator loop
provides:
  - StreamMonitor class dispatching AssistantMessage/ToolUseBlock/TaskProgressMessage/TaskNotificationMessage/ResultMessage
  - ReviewVerdict Pydantic model with JSON schema for structured output
  - review_output() async function with file-missing early return and content truncation
  - ReviewError exception in orchestrator error hierarchy
  - ReviewStatus enum and Task.review_status/revision_count fields (backward-compat)
affects: [05-02-orchestrator-intelligence, 08-cli, future-phases]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "TDD: RED (ImportError) -> GREEN (all pass) for each new module"
    - "isinstance dispatch on SDK types for typed streaming message handling"
    - "asyncio.to_thread for file I/O inside async orchestrator context"
    - "Content truncation: first 4000 + last 4000 chars with truncation notice for large files"
    - "XML boundary tags in prompt template (file_content, agent_summary) for prompt injection mitigation"

key-files:
  created:
    - packages/conductor-core/src/conductor/orchestrator/monitor.py
    - packages/conductor-core/src/conductor/orchestrator/reviewer.py
    - packages/conductor-core/tests/test_monitor.py
    - packages/conductor-core/tests/test_reviewer.py
  modified:
    - packages/conductor-core/src/conductor/orchestrator/errors.py
    - packages/conductor-core/src/conductor/orchestrator/__init__.py
    - packages/conductor-core/src/conductor/state/models.py

key-decisions:
  - "StreamMonitor does NOT take StateManager — lightweight, state writes happen in orchestrator (Plan 02)"
  - "review_output() uses asyncio.to_thread for file reads — avoids blocking event loop under parallelism"
  - "Content truncation at 8000 chars (first 4000 + last 4000) preserves module declarations and end-of-file implementations"
  - "ReviewStatus.PENDING/APPROVED/NEEDS_REVISION StrEnum with backward-compatible defaults on Task"
  - "ReviewError is simple OrchestratorError subclass — no special attributes needed"

patterns-established:
  - "Pattern: SDK message dispatch via isinstance chain (AssistantMessage -> ToolUseBlock -> TaskProgressMessage -> TaskNotificationMessage -> ResultMessage -> no-op)"
  - "Pattern: File existence guard before SDK call — early return ReviewVerdict(approved=False) avoids unnecessary LLM cost"
  - "Pattern: Mock SDK types via MagicMock with __class__ override for unit tests without instantiating real SDK objects"

requirements-completed: [ORCH-03, ORCH-04]

# Metrics
duration: 4min
completed: 2026-03-10
---

# Phase 5 Plan 01: Orchestrator Intelligence Summary

**StreamMonitor typed message dispatch (ORCH-03) and ReviewVerdict/review_output() quality review (ORCH-04) as standalone, fully tested modules with TDD coverage.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-10T16:44:02Z
- **Completed:** 2026-03-10T16:47:22Z
- **Tasks:** 2/2
- **Files modified:** 7

## Accomplishments

- StreamMonitor processes all 4 SDK streaming message types (AssistantMessage with ToolUseBlock, TaskProgressMessage, TaskNotificationMessage, ResultMessage) with typed isinstance dispatch
- ReviewVerdict Pydantic model produces valid JSON schema for SDK structured output; review_output() handles approved, file-missing, and no-structured-output cases with content truncation for large files
- Task model extended with ReviewStatus enum and review_status/revision_count fields (all defaults, backward-compatible)
- ReviewError added to orchestrator error hierarchy
- All 154 tests pass (21 new + 133 pre-existing), ruff clean

## Task Commits

Each task was committed atomically:

1. **Task 1: StreamMonitor + ReviewStatus enum + ReviewError (TDD)** - `ab44a96` (feat)
2. **Task 2: ReviewVerdict model + review_output() function (TDD)** - `63451a6` (feat)

_Note: TDD tasks included RED phase (ImportError confirmed) then GREEN phase (all tests pass)._

## Files Created/Modified

- `packages/conductor-core/src/conductor/orchestrator/monitor.py` - StreamMonitor class with typed message dispatch
- `packages/conductor-core/src/conductor/orchestrator/reviewer.py` - ReviewVerdict model, REVIEW_PROMPT_TEMPLATE, review_output()
- `packages/conductor-core/src/conductor/orchestrator/errors.py` - Added ReviewError(OrchestratorError)
- `packages/conductor-core/src/conductor/orchestrator/__init__.py` - Exported StreamMonitor, ReviewVerdict, review_output, ReviewError
- `packages/conductor-core/src/conductor/state/models.py` - Added ReviewStatus enum, Task.review_status, Task.revision_count
- `packages/conductor-core/tests/test_monitor.py` - 10 tests for ORCH-03 StreamMonitor dispatch
- `packages/conductor-core/tests/test_reviewer.py` - 11 tests for ORCH-04 ReviewVerdict and review_output()

## Decisions Made

- StreamMonitor does NOT hold a StateManager reference — keeps it pure and testable; state writes belong in the orchestrator
- review_output() uses asyncio.to_thread for file reads to avoid blocking the event loop when multiple agents complete simultaneously
- Content truncation uses first 4000 + last 4000 chars strategy (preserving module-level declarations and end-of-file implementations, the most review-relevant sections)
- ReviewError is a simple subclass with no special attributes — the message string carries sufficient context for the orchestrator error handler

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Ruff flagged unsorted import block in monitor.py (I001) — auto-fixed with `ruff --fix` immediately after initial creation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- StreamMonitor and review_output() are ready to be wired into the orchestrator's _run_agent_loop() in Plan 02
- Plan 02 will replace `async for _ in client.stream_response(): pass` with `monitor.process(message)` and add post-completion review call
- All contracts (StreamMonitor.process(), review_output(), ReviewVerdict, ReviewError) are defined and tested

---
*Phase: 05-orchestrator-intelligence*
*Completed: 2026-03-10*

## Self-Check: PASSED

- FOUND: packages/conductor-core/src/conductor/orchestrator/monitor.py
- FOUND: packages/conductor-core/src/conductor/orchestrator/reviewer.py
- FOUND: packages/conductor-core/tests/test_monitor.py
- FOUND: packages/conductor-core/tests/test_reviewer.py
- FOUND: .planning/phases/05-orchestrator-intelligence/05-01-SUMMARY.md
- FOUND commit: ab44a96 (Task 1)
- FOUND commit: 63451a6 (Task 2)
