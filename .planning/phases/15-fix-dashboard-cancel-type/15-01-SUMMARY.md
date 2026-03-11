---
phase: 15-fix-dashboard-cancel-type
plan: 01
subsystem: dashboard-server
tags: [bug-fix, dashboard, intervention, cancel-agent, test-contract]
dependency_graph:
  requires: [Phase 12 cancel_agent string-based API]
  provides: [correct dashboard cancel/redirect dispatch, correct test assertions]
  affects: [conductor.dashboard.server, dashboard intervention tests]
tech_stack:
  added: []
  patterns: [cancel_agent(agent_id), cancel_agent(agent_id, new_instructions=message)]
key_files:
  modified:
    - packages/conductor-core/src/conductor/dashboard/server.py
    - packages/conductor-core/tests/dashboard/test_server_interventions.py
decisions:
  - dashboard cancel branch calls cancel_agent(agent_id) with no second argument
  - dashboard redirect branch passes message string via new_instructions= keyword, not TaskSpec
  - test assertions use assert_awaited_once_with for strict contract validation
metrics:
  duration: 55s
  completed_date: "2026-03-11"
  tasks_completed: 2
  files_modified: 2
---

# Phase 15 Plan 01: Fix Dashboard Cancel/Redirect Type Summary

**One-liner:** Removed TaskSpec wrapping from dashboard intervention handlers so cancel_agent receives (agent_id) and (agent_id, new_instructions=str) as the Phase 12 API requires.

## What Was Built

Fixed the `handle_intervention` function in `server.py` which was still passing `TaskSpec` objects to `cancel_agent()` after Phase 12 changed the signature to accept `(agent_id: str, new_instructions: str | None = None)`. Updated test assertions to validate the correct string-based contract using `assert_awaited_once_with`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix server.py cancel and redirect branches | a8adb20 | packages/conductor-core/src/conductor/dashboard/server.py |
| 2 | Fix test assertions to validate correct contract | f6a567a | packages/conductor-core/tests/dashboard/test_server_interventions.py |

## Verification Results

- No TaskSpec references remain in server.py: confirmed via AST inspection
- All 8 intervention tests pass: `pytest tests/dashboard/test_server_interventions.py -v`
- Full suite: 298 passed, 0 failures, no regressions

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- [FOUND] packages/conductor-core/src/conductor/dashboard/server.py — modified
- [FOUND] packages/conductor-core/tests/dashboard/test_server_interventions.py — modified
- [FOUND] commit a8adb20 — Task 1 fix
- [FOUND] commit f6a567a — Task 2 test fix
