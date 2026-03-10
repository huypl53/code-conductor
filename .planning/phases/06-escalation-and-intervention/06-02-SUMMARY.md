---
phase: 06-escalation-and-intervention
plan: 02
subsystem: orchestrator-intervention
tags: [tdd, intervention, cancel, guidance, pause, registries, asyncio]
dependency_graph:
  requires: [06-01]
  provides: [COMM-05, COMM-06, COMM-07]
  affects: [orchestrator.py, test_orchestrator.py]
tech_stack:
  added: []
  patterns:
    - try/finally for active client registry cleanup
    - asyncio.create_task for fire-and-forget intervention spawns
    - asyncio.wait_for for human-in timeout with fallback
    - Drain stream_response() after interrupt before sending (stale message prevention)
key_files:
  created: []
  modified:
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/tests/test_orchestrator.py
decisions:
  - _active_clients cleanup in try/finally inside async-with ACPClient block — ensures cleanup even when inner code raises (SessionError, RuntimeError, etc.)
  - cancel_agent uses asyncio.create_task (fire-and-forget) for new session — caller does not wait for the reassigned agent to complete
  - pause_for_human_decision drains stream_response() after interrupt — prevents stale message corruption from in-flight messages
  - inject_guidance is send-only, no interrupt, no stream drain — mid-stream guidance injection without disrupting agent flow
  - asyncio.wait_for with TimeoutError catch in pause_for_human_decision — prevents deadlock when human does not respond
  - Test fix: asyncio.sleep(0) yield after cancel_agent to allow spawned asyncio.Task to execute before asserting
metrics:
  duration: 4 minutes
  completed: 2026-03-10
  tasks_completed: 1
  files_modified: 2
---

# Phase 06 Plan 02: Intervention Methods on Orchestrator Summary

Intervention methods (cancel/reassign, inject guidance, pause/resume) added to the Orchestrator class with active client/task registries and try/finally cleanup.

## What Was Built

Three new public methods on `Orchestrator` implementing COMM-05/06/07:

**`cancel_agent(agent_id, corrected_spec)`** (COMM-05):
- Pops the agent's `asyncio.Task` from `_active_tasks`, calls `task.cancel()`, awaits cancellation (catching `CancelledError`)
- Spawns a new `_run_agent_loop` via `asyncio.create_task` with the corrected `TaskSpec`
- Idempotent: unknown `agent_id` is a no-op on cancel, still spawns the new task

**`inject_guidance(agent_id, guidance)`** (COMM-06):
- Looks up `agent_id` in `_active_clients`, raises `EscalationError` if not found
- Calls `client.send(guidance)` only — no interrupt, no stream drain
- Guidance is injected into the agent's running context without disrupting its stream

**`pause_for_human_decision(agent_id, question, human_out, human_in, timeout)`** (COMM-07):
- Calls `client.interrupt()` to pause the agent
- Drains `stream_response()` to prevent stale message corruption
- Pushes `HumanQuery(question, context={})` to `human_out`
- Awaits `human_in.get()` with `asyncio.wait_for(timeout=timeout)` — falls back to `"proceed with best judgment"` on `TimeoutError`
- Sends `"Human decision: {decision}. Continue your work with this guidance."` via `client.send()`

**Registry infrastructure:**
- `_active_clients: dict[str, ACPClient]` — registered after `ACPClient.__aenter__`, cleaned up in `finally` block
- `_active_tasks: dict[str, asyncio.Task]` — populated in `run()` spawn loop, removed on completion
- `_semaphore: asyncio.Semaphore | None` — stored on `self` in `run()` for use by `cancel_agent`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] asyncio.sleep(0) yield needed in cancel_agent tests**
- **Found during:** Task 1 GREEN phase
- **Issue:** Tests asserting `spawned_specs` after `await orch.cancel_agent(...)` saw empty list. `asyncio.create_task` schedules the coroutine but doesn't execute it until the event loop yields. The test checked `spawned_specs` before the spawned coroutine ran.
- **Fix:** Added `await asyncio.sleep(0)` after `cancel_agent` calls in `test_cancel_agent_spawns_new_loop_with_corrected_spec` and `test_cancel_agent_unknown_id_is_idempotent` to yield to the event loop.
- **Files modified:** `packages/conductor-core/tests/test_orchestrator.py`
- **Commit:** d40cad5

## Test Results

- 13 existing tests: all passing (no regressions)
- 13 new COMM-05/06/07 tests: all passing
- Full suite: **199 passed, 0 failed**

## Verification Passed

```
cd packages/conductor-core && uv run pytest tests/test_orchestrator.py tests/test_escalation.py -x -v  # 53 passed
cd packages/conductor-core && uv run ruff check src/conductor/orchestrator/orchestrator.py              # All checks passed
cd packages/conductor-core && uv run pyright src/conductor/orchestrator/orchestrator.py                 # 0 errors
cd packages/conductor-core && uv run pytest                                                             # 199 passed
```

## Self-Check: PASSED

Files exist:
- FOUND: packages/conductor-core/src/conductor/orchestrator/orchestrator.py
- FOUND: packages/conductor-core/tests/test_orchestrator.py

Commits exist:
- 077f87b: test(06-02): RED phase — COMM-05/06/07 failing tests
- d40cad5: feat(06-02): GREEN phase — cancel_agent, inject_guidance, pause_for_human_decision
