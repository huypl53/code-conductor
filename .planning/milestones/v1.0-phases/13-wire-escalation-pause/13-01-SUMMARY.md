---
phase: 13-wire-escalation-pause
plan: 01
subsystem: orchestrator, cli, dashboard-backend
tags: [escalation, permission-handler, pause, acp-client, tdd]
dependency_graph:
  requires: [phase-06-escalation-and-intervention, phase-08-cli-interface, phase-09-dashboard-backend]
  provides: [EscalationRouter-as-PermissionHandler, CLI-pause-command, dashboard-pause-action]
  affects: [orchestrator._run_agent_loop, input_loop._dispatch_command, server.handle_intervention]
tech_stack:
  added: []
  patterns: [TDD-red-green, PermissionHandler-wiring, queue-gate-pattern]
key_files:
  created: []
  modified:
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/src/conductor/cli/input_loop.py
    - packages/conductor-core/src/conductor/dashboard/server.py
    - packages/conductor-core/tests/test_orchestrator.py
    - packages/conductor-core/tests/test_cli.py
    - packages/conductor-core/tests/dashboard/test_server_interventions.py
key_decisions:
  - PermissionHandler timeout set to escalation_router._human_timeout + 30.0 (150s default) so human escalation window is respected before permission timeout fires
  - Dashboard pause branch reads orchestrator._human_out/_human_in directly — avoids adding new parameters to handle_intervention signature
  - CLI pause branch requires both human_out and human_in to be non-None — fails fast with clear error in auto/non-interactive modes
  - _dispatch_command gains human_out/human_in params after console — preserves existing positional call sites which use only 2 positional args
metrics:
  duration_minutes: 12
  completed_date: "2026-03-11"
  tasks_completed: 2
  files_modified: 6
requirements: [COMM-03, COMM-04, COMM-07]
---

# Phase 13 Plan 01: Wire EscalationRouter and Pause Command Summary

EscalationRouter wired as PermissionHandler in ACPClient sessions with 150s timeout, plus CLI and dashboard pause commands dispatching to pause_for_human_decision.

## What Was Built

### Task 1: Wire EscalationRouter as PermissionHandler in _run_agent_loop

Before this plan, `EscalationRouter` was created in the orchestrator but never connected to `ACPClient` sessions. Sub-agent `AskUserQuestion` calls would go unanswered (default-allow fallback) because no `permission_handler` was passed.

The fix is a 3-line change in `_run_agent_loop`:
1. Import `PermissionHandler` from `conductor.acp.permission`
2. Create `handler = PermissionHandler(answer_fn=self._escalation_router.resolve, timeout=self._escalation_router._human_timeout + 30.0)`
3. Pass `permission_handler=handler` to `ACPClient`

The timeout is set to `_human_timeout + 30.0` (150s by default) so the PermissionHandler's outer timeout does not fire before the EscalationRouter's own human-wait timeout completes.

### Task 2: Add pause command to CLI and dashboard backend

**CLI (`input_loop.py`):**
- Added `human_out` and `human_in` parameters to `_dispatch_command` signature (optional, default None)
- Added `pause` branch: validates arg count, checks queues are non-None, calls `orchestrator.pause_for_human_decision(agent_id, question, human_out, human_in)`
- Updated `_input_loop` to forward its `human_out`/`human_in` to `_dispatch_command`
- Updated unknown-command hint to include `pause`

**Dashboard (`server.py`):**
- Added `pause` branch in `handle_intervention` inside the existing try/except
- Reads `orchestrator._human_out`/`_human_in` to check queue availability
- If queues are None (auto mode), silently skips — no crash

## Tests Added

| File | Tests Added | Coverage |
|------|-------------|----------|
| test_orchestrator.py | 3 | PermissionHandler presence, answer_fn=resolve, timeout=150s |
| test_cli.py | 3 | pause success, usage error, no queues |
| test_server_interventions.py | 2 | pause with queues, pause without queues |

Total: 8 new tests. Full suite: 298 passed (was 290 before).

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check

Files created/modified:
- packages/conductor-core/src/conductor/orchestrator/orchestrator.py — modified
- packages/conductor-core/src/conductor/cli/input_loop.py — modified
- packages/conductor-core/src/conductor/dashboard/server.py — modified
- packages/conductor-core/tests/test_orchestrator.py — modified
- packages/conductor-core/tests/test_cli.py — modified
- packages/conductor-core/tests/dashboard/test_server_interventions.py — modified

Commits:
- c26df56: feat(13-01): wire EscalationRouter as PermissionHandler in _run_agent_loop
- 183c0e6: feat(13-01): add pause command to CLI and dashboard backend

## Self-Check: PASSED
