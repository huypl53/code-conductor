---
phase: 12-fix-cli-cancel-redirect
plan: "01"
subsystem: orchestrator
tags: [bug-fix, cli, orchestrator, tdd, cancel, redirect]
dependency_graph:
  requires: []
  provides: [cancel_agent-new-signature]
  affects: [packages/conductor-core/src/conductor/orchestrator/orchestrator.py]
tech_stack:
  added: []
  patterns: [state-lookup-instead-of-caller-supplied-spec, safe-no-op-for-unknown-agent]
key_files:
  created: []
  modified:
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/tests/test_orchestrator.py
decisions:
  - cancel_agent reconstructs TaskSpec from state internally — caller (CLI) only needs agent_id
  - Unknown agent_id returns early as safe no-op (not an error, not a re-spawn)
  - Old TestComm05CancelReassign tests updated to use new API shape (no corrected_spec positional arg)
metrics:
  duration_minutes: 10
  completed_date: "2026-03-11"
  tasks_completed: 2
  files_modified: 2
---

# Phase 12 Plan 01: Fix CLI cancel_agent Signature Mismatch Summary

**One-liner:** Fixed `cancel_agent(agent_id, new_instructions=None)` signature so CLI cancel/redirect commands execute without TypeError by reconstructing TaskSpec from state internally.

## What Was Built

The CLI `cancel` and `redirect` commands call `orchestrator.cancel_agent(agent_id)` and `orchestrator.cancel_agent(agent_id, new_instructions="...")` respectively. The Orchestrator's implementation had an incompatible signature: `cancel_agent(agent_id, corrected_spec: TaskSpec)` — a required positional argument the CLI never supplied, causing TypeError on every cancel/redirect invocation.

The fix changes the Orchestrator to:
1. Accept `new_instructions: str | None = None` instead of `corrected_spec: TaskSpec`
2. Internally look up the agent's current task from state via `asyncio.to_thread(self._state.read_state)`
3. Reconstruct the TaskSpec from the stored task record, substituting `new_instructions` when provided
4. Return early as a safe no-op if the agent_id is not found in state

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add failing integration tests (RED) | 44f226c | packages/conductor-core/tests/test_orchestrator.py |
| 2 | Fix cancel_agent signature (GREEN) | e219d99 | packages/conductor-core/src/conductor/orchestrator/orchestrator.py, packages/conductor-core/tests/test_orchestrator.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated old TestComm05CancelReassign tests to new API shape**
- **Found during:** Task 2 (full suite regression check)
- **Issue:** Three old tests in `TestComm05CancelReassign` passed `corrected_spec: TaskSpec` as the second positional argument. With the new signature that position is `new_instructions: str | None`, causing 1 test failure (the spec object was treated as a truthy `new_instructions` value, and state lookup returned no task for unknown agent-id → early return → no re-spawn → assertion failed).
- **Fix:** Updated all three `TestComm05CancelReassign` tests: added `read_state` mock returning a proper `ConductorState` with agent+task, changed call sites to new API (`cancel_agent(agent_id)` and `cancel_agent(agent_id, new_instructions=...)`), updated `test_cancel_agent_unknown_id_is_idempotent` to `test_cancel_agent_unknown_id_is_noop` reflecting the correct new behavior.
- **Files modified:** packages/conductor-core/tests/test_orchestrator.py
- **Commit:** e219d99

## Verification Results

All plan verification steps pass:

```
uv run pytest -k "cancel_agent" -q  →  6 passed (3 old + 3 new integration tests)
uv run pytest tests/test_cli.py -q  →  11 passed (no regression in CLI dispatch tests)
uv run pytest tests/ -q             →  290 passed
inspect.signature(Orchestrator.cancel_agent) → (self, agent_id: 'str', new_instructions: 'str | None' = None) -> 'None'
```

## Self-Check: PASSED

Files exist:
- packages/conductor-core/src/conductor/orchestrator/orchestrator.py — FOUND
- packages/conductor-core/tests/test_orchestrator.py — FOUND

Commits exist:
- 44f226c — FOUND (test: add failing integration tests)
- e219d99 — FOUND (feat: fix cancel_agent signature)
