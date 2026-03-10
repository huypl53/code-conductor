---
phase: 06-escalation-and-intervention
plan: 01
subsystem: orchestrator
tags: [asyncio, escalation, permission-routing, tdd, logging, queues]

# Dependency graph
requires:
  - phase: 03-acp-communication-layer
    provides: PermissionHandler._AnswerFn contract and asyncio.Queue-based answer routing
  - phase: 04-orchestrator-core
    provides: OrchestratorError base class in errors.py
provides:
  - EscalationRouter: answer_fn-compatible router for auto and interactive modes
  - HumanQuery dataclass pushed to human_out queue for interactive escalation
  - DecisionLog dataclass for autonomous decision audit trail
  - _is_low_confidence heuristic using keyword set for routing decisions
  - EscalationError exception in orchestrator error hierarchy
affects: [07-cli, 08-integration, orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - asyncio.wait_for for human_in.get() — same timeout pattern as PermissionHandler
    - frozenset keyword lookup for O(1) confidence classification
    - dataclasses for lightweight transport objects (HumanQuery, DecisionLog)
    - logger.info audit trail for all autonomous decisions

key-files:
  created:
    - packages/conductor-core/src/conductor/orchestrator/escalation.py
    - packages/conductor-core/tests/test_escalation.py
  modified:
    - packages/conductor-core/src/conductor/orchestrator/errors.py
    - packages/conductor-core/src/conductor/orchestrator/__init__.py

key-decisions:
  - "EscalationRouter.resolve() always returns PermissionResultAllow — escalation routing never denies, it either uses the human's answer or falls back to 'proceed'"
  - "_LOW_CONFIDENCE_KEYWORDS frozenset contains destructive/sensitive ops: delete, drop, remove, irreversible, cannot be undone, production, deploy, billing, secret, credentials"
  - "Auto mode bypasses human_out/human_in queues entirely even when provided — mode takes strict precedence"
  - "Timeout fallback in interactive mode logs via logger.info and returns 'proceed' — no exception raised to caller"
  - "datetime.UTC alias used per project convention (ruff UP017)"

patterns-established:
  - "Auto mode logs every decision via logger.info with question, confidence, answer, rationale, timestamp"
  - "Interactive + low-confidence: push HumanQuery to human_out, await human_in.get() with asyncio.wait_for, catch TimeoutError and fall back"
  - "Interactive + high-confidence or no queues: auto-answer same as auto mode"

requirements-completed: [COMM-03, COMM-04]

# Metrics
duration: 15min
completed: 2026-03-11
---

# Phase 06 Plan 01: EscalationRouter Summary

**EscalationRouter with asyncio.Queue-based human escalation, keyword confidence heuristic, and autonomous decision logging for COMM-03/COMM-04**

## Performance

- **Duration:** 15 min
- **Started:** 2026-03-10T17:15:27Z
- **Completed:** 2026-03-10T17:30:00Z
- **Tasks:** 1 (TDD: RED + GREEN phases)
- **Files modified:** 4

## Accomplishments

- EscalationRouter implements _AnswerFn contract, routes all sub-agent questions in auto or interactive mode
- Auto mode: all questions answered autonomously, each decision logged as structured audit trail via logger.info
- Interactive mode: low-confidence questions pushed to human_out queue, answer read from human_in with configurable timeout and 'proceed' fallback
- _is_low_confidence heuristic uses frozenset of 10 sensitive keywords for O(1) classification
- EscalationError added to OrchestratorError hierarchy and exported from package __init__
- 27 tests covering all branches pass with 0 lint and 0 type errors

## Task Commits

Each task was committed atomically (TDD with two commits):

1. **RED: test(06-01): add failing tests for EscalationRouter** - `b9b15c2` (test)
2. **GREEN: feat(06-01): implement EscalationRouter** - `6d85e9a` (feat)

_Note: TDD tasks have two commits (test RED then feat GREEN)_

## Files Created/Modified

- `packages/conductor-core/src/conductor/orchestrator/escalation.py` - EscalationRouter, HumanQuery, DecisionLog, _is_low_confidence, _LOW_CONFIDENCE_KEYWORDS
- `packages/conductor-core/tests/test_escalation.py` - 27 tests covering COMM-03, COMM-04, error hierarchy, data models, confidence heuristic
- `packages/conductor-core/src/conductor/orchestrator/errors.py` - Added EscalationError subclass of OrchestratorError
- `packages/conductor-core/src/conductor/orchestrator/__init__.py` - Added exports for EscalationRouter, HumanQuery, DecisionLog, EscalationError

## Decisions Made

- EscalationRouter.resolve() always returns PermissionResultAllow — never deny, the router's job is routing not blocking
- Auto mode strictly ignores human_out/human_in even when provided — mode takes full precedence over queue availability
- Timeout fallback returns 'proceed' and logs — prevents deadlock without raising to caller
- _LOW_CONFIDENCE_KEYWORDS frozenset: delete, drop, remove, irreversible, cannot be undone, production, deploy, billing, secret, credentials

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed 4 ruff E501 line-too-long violations in escalation.py**
- **Found during:** Task 1 (GREEN phase ruff check)
- **Issue:** Docstring lines and logger.info format strings exceeded 88-char limit
- **Fix:** Wrapped long docstring lines, split logger.info format strings across continuation lines
- **Files modified:** packages/conductor-core/src/conductor/orchestrator/escalation.py
- **Verification:** `uv run ruff check` passes with "All checks passed!"
- **Committed in:** 6d85e9a (feat commit, fixed before committing)

---

**Total deviations:** 1 auto-fixed (Rule 1 - linting)
**Impact on plan:** Minor linting fix required by project ruff config. No scope creep.

## Issues Encountered

None.

## Next Phase Readiness

- EscalationRouter is ready to replace PermissionHandler's answer_fn in the Orchestrator wiring
- human_out/human_in queues need to be created and connected at Orchestrator.__init__ in interactive mode
- CLI phase (Phase 7/8) will wire up the queues and handle the human_out stream in the TUI

---
*Phase: 06-escalation-and-intervention*
*Completed: 2026-03-11*
