---
phase: 29-verification-review-pipeline
plan: "02"
subsystem: orchestrator
tags: [verifier, orchestrator, integration, testing]
dependency_graph:
  requires: ["29-01"]
  provides: ["verifier-integration", "updated-exports"]
  affects: ["orchestrator-loop", "task-completion", "revision-cycle"]
tech_stack:
  added: []
  patterns: ["patch TaskVerifier at orchestrator level for test isolation"]
key_files:
  modified:
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/src/conductor/orchestrator/__init__.py
    - packages/conductor-core/tests/test_orchestrator.py
decisions:
  - "Patch conductor.orchestrator.orchestrator.TaskVerifier (not the verifier module) so tests control the instance created in __init__"
  - "Verifier called after file existence gate to avoid duplicate file-not-found handling"
  - "VerificationResult import kept in orchestrator.py even though only TaskVerifier is used — symmetry with verifier module export"
metrics:
  duration: "~15 minutes"
  completed_date: "2026-03-11"
  tasks_completed: 2
  files_modified: 3
---

# Phase 29 Plan 02: Wire Verifier into Orchestrator Loop Summary

**One-liner:** TaskVerifier wired into `_run_agent_loop` after review approval gate — stub detection triggers revision, unwired files warn but complete, all types re-exported from package `__init__.py`.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Wire TaskVerifier into orchestrator and update exports | a659a5c | orchestrator.py, __init__.py |
| 2 | Add integration tests for verifier in orchestrator loop | cfcc9ee | tests/test_orchestrator.py |

## What Was Built

### Task 1: Verifier Integration

Added to `orchestrator.py`:
- Import `TaskVerifier, VerificationResult` from verifier module
- `self._verifier = TaskVerifier(repo_path=repo_path)` in `__init__`
- Verification block in `_run_agent_loop` after the file existence gate: calls `self._verifier.verify(task_spec.target_file)` when `verdict.approved and task_spec.target_file`
- Non-substantive result: overrides `verdict` to `approved=False` with stub-specific revision instructions, triggering the existing revision loop
- Unwired result: `logger.warning(...)` only — does not block completion

Updated `__init__.py` exports:
- Added `TaskVerifier`, `VerificationResult`, `DEFAULT_STUB_PATTERNS` from verifier module
- Added `SpecVerdict`, `QualityVerdict`, `review_spec_compliance`, `review_code_quality` from reviewer module (new Stage 1/2 functions from plan 01)

### Task 2: Integration Tests

Added `TestVerifierIntegration` class to `tests/test_orchestrator.py` with 3 tests:

1. **test_stub_detection_triggers_revision** — Mocks verifier to return `substantive=False` on first call, `substantive=True` on second. Verifies `client.send()` called at least twice (initial + revision) and the revision message contains "stub" or "placeholder".

2. **test_unwired_file_still_completes** — Mocks verifier with `substantive=True, wired=False`. Verifies task completes with `review_status="approved"` — wiring is warning-only.

3. **test_fully_verified_completes** — Mocks verifier with all True. Verifies normal completion and `verify()` called exactly once.

## Verification

- All exports importable: `from conductor.orchestrator import TaskVerifier, VerificationResult, SpecVerdict, QualityVerdict` — OK
- Verifier wired: `grep -n "TaskVerifier\|_verifier" orchestrator.py` shows import at line 29, instantiation at 141, call at 815
- Test suite: 555 passed (552 original + 3 new), 0 failures

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — exists, contains `TaskVerifier` at lines 29, 141, 815
- [x] `packages/conductor-core/src/conductor/orchestrator/__init__.py` — exists, contains `TaskVerifier`, `VerificationResult`, `DEFAULT_STUB_PATTERNS`, `SpecVerdict`, `QualityVerdict`, `review_spec_compliance`, `review_code_quality`
- [x] `packages/conductor-core/tests/test_orchestrator.py` — exists, contains `TestVerifierIntegration` with 208 new lines (>20 minimum)
- [x] Commit `a659a5c` — verified in git log
- [x] Commit `cfcc9ee` — verified in git log
