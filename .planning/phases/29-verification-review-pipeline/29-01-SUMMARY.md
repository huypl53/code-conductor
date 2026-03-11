---
phase: 29-verification-review-pipeline
plan: "01"
subsystem: orchestrator
tags: [verifier, reviewer, stub-detection, two-stage-review, tdd]
dependency_graph:
  requires: []
  provides:
    - conductor.orchestrator.verifier.TaskVerifier
    - conductor.orchestrator.verifier.VerificationResult
    - conductor.orchestrator.verifier.DEFAULT_STUB_PATTERNS
    - conductor.orchestrator.reviewer.SpecVerdict
    - conductor.orchestrator.reviewer.QualityVerdict
    - conductor.orchestrator.reviewer.review_spec_compliance
    - conductor.orchestrator.reviewer.review_code_quality
  affects:
    - conductor.orchestrator.reviewer.review_output (refactored, backward compat preserved)
tech_stack:
  added:
    - subprocess.run with grep for wiring checks
  patterns:
    - TDD (RED → GREEN) for both tasks
    - Two-stage review with short-circuit (spec fail skips quality)
    - Substantive detection via regex patterns + line-count heuristic
key_files:
  created:
    - packages/conductor-core/src/conductor/orchestrator/verifier.py
    - packages/conductor-core/tests/test_verifier.py
  modified:
    - packages/conductor-core/src/conductor/orchestrator/reviewer.py
    - packages/conductor-core/tests/test_reviewer.py
decisions:
  - Wiring check uses file stem (no extension) for grep — catches `import mymodule` and `from pkg.mymodule import ...`
  - Substantive heuristic combines stub pattern match AND fewer than 10 non-comment lines (avoids flagging real files with TODO comments)
  - review_output() handles file-not-found without SDK call before delegating to two-stage review
  - Existing test_reviewer.py tests updated to work with two-stage mock patterns while preserving all behavioral assertions
metrics:
  duration: "~20 minutes"
  completed_date: "2026-03-11"
  tasks_completed: 2
  files_changed: 4
---

# Phase 29 Plan 01: TaskVerifier and Two-Stage Reviewer Refactor Summary

**One-liner:** New TaskVerifier with regex stub detection and grep-based wiring checks; reviewer refactored into spec-compliance-then-quality two-stage pipeline with backward-compatible wrapper.

## What Was Built

### Task 1: TaskVerifier module

New `verifier.py` providing:

- `VerificationResult` model: `exists`, `substantive`, `wired` booleans plus `stub_matches` list for debugging
- `DEFAULT_STUB_PATTERNS`: 6 regex patterns covering pass-only, NotImplementedError, TODO markers, return None, bare return, ellipsis body
- `TaskVerifier.verify()`: three-level check using file existence, regex pattern matching with line-count heuristic (stub patterns + <10 substantive lines = stub), and subprocess grep for wiring

Wiring check uses file stem (not full basename) so `grep mymodule` matches both `import mymodule` and `from pkg.mymodule import ...` in .py/.ts/.js files.

### Task 2: Two-stage reviewer refactor

`reviewer.py` now has:

- `SpecVerdict`: `spec_compliant`, `issues`, `revision_instructions`
- `QualityVerdict`: `quality_passed`, `quality_issues`, `revision_instructions`
- `review_spec_compliance()`: Stage 1 — does output match the task description?
- `review_code_quality()`: Stage 2 — defects, structure, security concerns
- `review_output()`: backward-compatible wrapper delegating to both stages; spec failure short-circuits quality review

`ReviewVerdict` model and `review_output()` signature unchanged — all callers continue to work without modification.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 756ce47 | feat(29-01): add TaskVerifier with stub detection and wiring checks |
| 2 | b9788d2 | feat(29-01): refactor reviewer into two-stage review with backward-compat wrapper |

## Test Coverage

- `test_verifier.py`: 22 tests covering VerificationResult model, DEFAULT_STUB_PATTERNS, missing files, all 6 stub patterns, real implementation detection, wiring (imported/not imported/JS reference), custom patterns
- `test_reviewer.py`: 27 tests covering SpecVerdict/QualityVerdict models, review_spec_compliance, review_code_quality, two-stage short-circuit behavior (4 scenarios), backward-compat review_output, content truncation

Full suite: 552 tests pass (0 failures).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] grep searched for file basename instead of stem**
- **Found during:** Task 1 wiring check implementation
- **Issue:** `grep "mymodule.py"` found no files because `main.py` contains `from src.mymodule import ...` — no `.py` suffix in the import
- **Fix:** Changed wiring check to use `target_path.stem` (e.g. "mymodule") instead of `target_path.name` ("mymodule.py")
- **Files modified:** packages/conductor-core/src/conductor/orchestrator/verifier.py

**2. [Rule 1 - Bug] Existing test_reviewer.py tests needed mock shape updates**
- **Found during:** Task 2 implementation
- **Issue:** Existing tests mocked sdk_query with ReviewVerdict-shaped data (`{approved, quality_issues, revision_instructions}`), but after refactoring the first call expects SpecVerdict-shaped data (`{spec_compliant, issues, revision_instructions}`)
- **Fix:** Updated test mocks to use stage-appropriate data shapes while preserving all behavioral assertions. All tests updated in-place with same semantic coverage.
- **Files modified:** packages/conductor-core/tests/test_reviewer.py

## Self-Check: PASSED

All files found on disk. Both commits verified in git history. 552 tests pass.
