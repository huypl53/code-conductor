---
phase: 23-resume-robustness
plan: 01
subsystem: tests
tags: [tdd, resume, review-only, exception-handling, spawn-loop]
dependency_graph:
  requires: []
  provides: [RESM-01-tests, RESM-02-tests]
  affects: [test_orchestrator.py]
tech_stack:
  added: []
  patterns: [pytest-asyncio, caplog, MagicMock mutate tracking, asyncio task exception capture]
key_files:
  created: []
  modified:
    - packages/conductor-core/tests/test_orchestrator.py
decisions:
  - "Used _track_mutate pattern from existing TestOrch04CompleteGate to intercept state mutations in review_only fallback tests"
  - "Used _failing_loop coroutine replacement (not ACPClient mock) for Test C to produce a real asyncio.Task with stored exception"
  - "caplog.at_level context manager used for log assertion scope isolation"
metrics:
  duration: "~10 minutes"
  completed: "2026-03-11T10:22:19Z"
  tasks_completed: 2
  files_modified: 1
---

# Phase 23 Plan 01: Resume Robustness — Test Coverage Summary

Lock-in contract tests for two crash-recovery code paths in the orchestrator: the `review_only` exception fallback in `_run_agent_loop` and the `marked_done` guard in the `resume()` spawn loop.

## Tests Added

### Class: TestReviewOnlyFallback (RESM-01)

3 new tests covering the `else` branch in `_run_agent_loop` when `review_only=True`:

- `test_review_only_exception_does_not_crash` — RuntimeError from `review_output` does not propagate out of `_run_agent_loop`
- `test_review_only_exception_logs_warning` — ValueError from `review_output` emits a WARNING log containing `"approving best-effort"`
- `test_review_only_exception_sets_approved_state` — RuntimeError from `review_output` results in a state mutation with `review_status="approved"`

### Class: TestResumeSpawnLoop (RESM-02)

3 new tests covering the resume spawn loop edge cases:

- `test_resume_marked_done_guard_allows_pending_task` — COMPLETED task + PENDING task that depends on it: only the pending task is spawned (the `marked_done` guard allows the loop to continue)
- `test_resume_all_completed_exits_immediately` — Two COMPLETED tasks: `_run_agent_loop` is never called, no hang
- `test_resume_failed_future_exception_retrieved` — Spawned task that raises `RuntimeError`: resume completes without crash, exception is logged at ERROR level with `"failed during resume"`

## Final Test Count

- Before: 61 tests
- After: 67 tests (6 added, 0 broken)

## Implementation Decisions

1. **_track_mutate pattern**: Reused the pattern from `TestOrch04CompleteGate.test_approved_review_marks_task_completed_with_approved_status` to intercept `state_mgr.mutate` calls and inspect resulting task state. Works for `review_only` path because `_make_complete_task_fn` is still called after the review attempt regardless of exception.

2. **_failing_loop coroutine for Test C**: Rather than patching `ACPClient` and `review_output` to orchestrate a failure path, replaced `_run_agent_loop` wholesale with `async def _failing_loop(...): raise RuntimeError(...)`. This produces a real `asyncio.Task` with `exception() != None`, which is exactly the code path under test (`fut.exception() is not None` in the resume loop).

3. **No ACPClient patching needed**: All new tests either use `review_only=True` (which bypasses ACPClient entirely) or replace `_run_agent_loop` wholesale (so ACPClient is never called). No need for `patch(f"{_ORCH}.ACPClient")`.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- packages/conductor-core/tests/test_orchestrator.py: FOUND
- Commit 2d5308a (TestReviewOnlyFallback): FOUND
- Commit ee3a99a (TestResumeSpawnLoop): FOUND
