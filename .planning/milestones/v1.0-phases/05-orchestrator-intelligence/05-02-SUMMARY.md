---
phase: 05-orchestrator-intelligence
plan: "02"
subsystem: orchestrator
tags: [orchestrator, review, revision, tdd, quality-gate]
dependency_graph:
  requires: [05-01]
  provides: [_run_agent_loop, observe-review-revise-cycle]
  affects: [orchestrator.py, test_orchestrator.py]
tech_stack:
  added: []
  patterns: [observe-review-revise, single-session-revision-loop, best-effort-completion]
key_files:
  created: []
  modified:
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/tests/test_orchestrator.py
decisions:
  - "_run_agent_loop max_revisions parameter defaults to instance-level self._max_revisions — allows per-orchestrator config without per-call override"
  - "revision_num variable from for loop used directly as revision_count — loop variable captures final iteration index naturally"
  - "Existing tests updated to patch _run_agent_loop instead of _spawn_agent — clean rename, no backward-compat alias needed since tests are internal"
  - "Tests that test the full loop (spawn_writes_agent_record, spawn_builds_identity_prompt, etc.) now also patch review_output — required since _run_agent_loop calls it"
metrics:
  duration_minutes: 7
  tasks_completed: 1
  files_modified: 2
  completed_date: "2026-03-10"
---

# Phase 5 Plan 02: _run_agent_loop (Observe-Review-Revise Cycle) Summary

**One-liner:** Replaced fire-and-forget _spawn_agent() with _run_agent_loop() implementing a quality-gated observe-review-revise cycle where tasks only complete after ReviewVerdict.approved passes or max_revisions (default 2) is exhausted.

## What Was Built

`_run_agent_loop()` in `Orchestrator` replaces `_spawn_agent()` with a full observe-review-revise cycle:

1. **Observe:** Each iteration creates a new `StreamMonitor` and processes all messages from `client.stream_response()` — capturing `result_text` from `ResultMessage`.

2. **Review:** After streaming completes, calls `review_output()` with the task description, target file, agent summary, and repo path. Returns a `ReviewVerdict` with `approved` boolean and `revision_instructions`.

3. **Revise (conditional):** If `approved=False` and revisions remain, calls `client.send(revision_instructions)` on the still-open session, then re-enters `stream_response()`.

4. **Terminate:** Loop exits when `approved=True` (quality gate passed) or `revision_num == max_revisions` (best-effort). Task is always marked `COMPLETED` — never left hanging.

5. **State update:** After session closes, `_make_complete_task_fn()` now sets `review_status` (APPROVED or NEEDS_REVISION) and `revision_count` alongside `TaskStatus.COMPLETED`.

## Key Architecture

The entire loop runs inside **one** `async with ACPClient(...) as client:` block — the session is never closed and reopened between review and revision feedback. This is the critical invariant tested by `TestOrch05SessionOpenForRevision`.

## Test Classes Added

| Class | Tests | Validates |
|-------|-------|-----------|
| `TestOrch04CompleteGate` | 2 | review_status=APPROVED on pass, COMPLETED even on best-effort |
| `TestOrch05RevisionSend` | 1 | client.send() called exactly twice (initial + 1 revision) |
| `TestOrch05MaxRevisions` | 1 | 3 iterations with max_revisions=2, revision_count=2 |
| `TestOrch05SessionOpenForRevision` | 1 | __aexit__ called exactly once despite 3 revision iterations |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing tests patching _spawn_agent to patch _run_agent_loop**

- **Found during:** GREEN phase — tests patching `_spawn_agent` on Orchestrator class failed since `run()` now calls `self._run_agent_loop()`
- **Issue:** `test_run_respects_dependency_order`, `test_run_max_agents_cap`, `test_run_uses_min_max_agents` all patched the old method name
- **Fix:** Updated `patch.object(..., "_spawn_agent", ...)` to `patch.object(..., "_run_agent_loop", ...)` in 3 tests
- **Files modified:** `tests/test_orchestrator.py`
- **Commit:** 8f424b9

**2. [Rule 2 - Missing] Patched review_output in existing integration tests**

- **Found during:** GREEN phase — tests that exercise the full loop (not patching _run_agent_loop) now call `review_output()` which would try to read files
- **Issue:** `test_run_decomposes_and_spawns`, `test_spawn_writes_agent_record_before_session`, `test_spawn_builds_identity_prompt`, `test_run_updates_task_status_on_completion` all needed `review_output` mocked
- **Fix:** Added `patch(f"{_ORCH}.review_output", _approved_review_mock())` to each test's context manager
- **Files modified:** `tests/test_orchestrator.py`
- **Commit:** 8f424b9

## Self-Check: PASSED

- orchestrator.py: FOUND
- test_orchestrator.py: FOUND
- Commit 8f424b9: FOUND
- `_run_agent_loop` present in both files: CONFIRMED
- `TestOrch04CompleteGate` present in test file: CONFIRMED
- 159 tests passing: CONFIRMED
- ruff clean on modified files: CONFIRMED
