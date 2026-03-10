---
phase: 09-dashboard-backend
plan: "01"
subsystem: conductor-dashboard-events
tags: [tdd, dashboard, event-classification, pydantic, strenum]
dependency_graph:
  requires: [conductor.state.models]
  provides: [conductor.dashboard.events]
  affects: [09-02, 09-03]
tech_stack:
  added: []
  patterns: [StrEnum + ConfigDict(use_enum_values=True) for clean JSON enum serialization, TDD red-green]
key_files:
  created:
    - packages/conductor-core/src/conductor/dashboard/__init__.py
    - packages/conductor-core/src/conductor/dashboard/events.py
    - packages/conductor-core/tests/test_dashboard_events.py
  modified: []
decisions:
  - "EventType uses StrEnum so values compare equal to plain strings — classify_delta compares task.status to 'completed'/'failed' string literals without needing to import TaskStatus"
  - "DeltaEvent.payload typed as dict (not dict[str, Any]) to keep model simple; dashboard consumers decide what to do with extra data"
  - "classify_delta returns [] when prev is None (initial snapshot) — avoids emitting TASK_ASSIGNED for every task on first load"
metrics:
  duration_seconds: 87
  completed_date: "2026-03-10"
  tasks_completed: 1
  files_created: 3
  files_modified: 0
---

# Phase 09 Plan 01: Dashboard Event Classification Summary

**One-liner:** Pure-logic event classifier diffing ConductorState snapshots into typed DeltaEvent list with smart notification flags for terminal task/agent transitions.

## What Was Built

The `conductor.dashboard.events` module is the pure-logic core of Phase 9. It provides:

- **`EventType(StrEnum)`** — 7 event values: `task_assigned`, `task_status_changed`, `task_completed`, `task_failed`, `agent_registered`, `agent_status_changed`, `intervention_needed`
- **`DeltaEvent(BaseModel)`** — Pydantic model with `type`, `task_id`, `agent_id`, `payload`, `is_smart_notification` fields; uses `ConfigDict(use_enum_values=True)` for clean JSON serialization
- **`classify_delta(prev, new)`** — Diffs two `ConductorState` snapshots; returns `[]` when `prev is None`, otherwise returns one `DeltaEvent` per change with smart notification flags on terminal transitions

Smart notification rules:
- `TASK_COMPLETED` and `TASK_FAILED` → `is_smart_notification=True`
- `INTERVENTION_NEEDED` (agent status→waiting) → `is_smart_notification=True`
- All other events → `is_smart_notification=False`

## Test Coverage

15 unit tests covering:
- `classify_delta(None, state)` returns `[]`
- `TASK_ASSIGNED` for new tasks
- `TASK_COMPLETED` with `is_smart_notification=True` on completed transition
- `TASK_FAILED` with `is_smart_notification=True` on failed transition
- `TASK_STATUS_CHANGED` for non-terminal transitions (in_progress, blocked)
- `AGENT_REGISTERED` for new agents
- `INTERVENTION_NEEDED` with `is_smart_notification=True` on waiting transition
- `AGENT_STATUS_CHANGED` for non-waiting transitions
- Identical state → empty list
- Multiple simultaneous changes (4 events in one delta)
- DeltaEvent JSON serialization produces clean string values (no `EventType.` prefix)
- All 7 EventType values serialize cleanly

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

### Files exist:
- [x] `packages/conductor-core/src/conductor/dashboard/__init__.py`
- [x] `packages/conductor-core/src/conductor/dashboard/events.py`
- [x] `packages/conductor-core/tests/test_dashboard_events.py`

### Commits:
- `48ed072` — test(09-01): add failing tests for EventType, DeltaEvent, classify_delta
- `95fa48d` — feat(09-01): implement EventType, DeltaEvent, classify_delta

### Test results: 15 passed, 0 failed

## Self-Check: PASSED
