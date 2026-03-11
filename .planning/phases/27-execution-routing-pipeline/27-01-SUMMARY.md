---
phase: 27-execution-routing-pipeline
plan: 01
subsystem: orchestrator
tags: [wave-execution, model-routing, lean-prompts, acp-client, tdd]
dependency_graph:
  requires: [phase-26-models-scheduler-infrastructure]
  provides: [wave-based-run, model-routing, lean-system-prompts]
  affects: [orchestrator, acp-client, identity]
tech_stack:
  added: []
  patterns: [asyncio.gather per wave, AgentRole enum lookup, optional kwargs forwarding]
key_files:
  created: []
  modified:
    - packages/conductor-core/src/conductor/acp/client.py
    - packages/conductor-core/src/conductor/orchestrator/identity.py
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/tests/test_orchestrator.py
    - packages/conductor-core/tests/test_identity.py
    - packages/conductor-core/tests/test_orchestrator_models.py
decisions:
  - ACPClient uses options_kwargs dict to conditionally include model only when not None — backward compatible
  - run() uses compute_waves() which reads a scratch TopologicalSorter, not the active one (Phase 26 decision honored)
  - resume() left unchanged with FIRST_COMPLETED pattern per constraints
  - AgentRole lookup uses __members__ check before enum construction to avoid ValueError
metrics:
  duration_minutes: 10
  completed_date: "2026-03-11"
  tasks_completed: 2
  files_modified: 6
---

# Phase 27 Plan 01: Execution & Routing Pipeline Summary

Wave-based spawn loop, model routing through ACPClient, and lean identity prompts replacing file-content-embedding with path-only system prompts.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | ACPClient model parameter and lean system prompts | 82f2430 | client.py, identity.py, test_identity.py, test_orchestrator_models.py |
| 2 | Wave-based spawn loop, model routing, and tests | afbdbde (impl), 77337da (tests) | orchestrator.py, test_orchestrator.py |

## What Was Built

**ACPClient model param (ROUTE-01 foundation):**
- Added `model: str | None = None` to `ACPClient.__init__()` after `max_turns`
- Stored as `self._model`; passed to `ClaudeAgentOptions` only when not None (backward compat)
- Uses `options_kwargs` dict pattern to conditionally include `model=` key

**Lean system prompts (LEAN-01):**
- Rewrote `build_system_prompt()` to emit file paths only — no task description content
- Structure: name/role, task_id, target_file, material file paths, memory path, boundary rule
- Task description stays out of system prompt; already sent as first user message via `client.send(f"Task {task_spec.id}: {task_spec.description}")`
- Prompt stays well under 500 tokens even with large task descriptions

**Wave-based spawn loop (WAVE-01):**
- `run()` now calls `scheduler.compute_waves()` and executes each wave via `asyncio.gather(*wave_tasks.values(), return_exceptions=True)`
- `_active_tasks` populated before gather, cleaned up after
- Failures logged per task; no exception propagation stops other tasks in the wave
- `resume()` left unchanged with FIRST_COMPLETED pattern (per constraints)

**Model routing (ROUTE-01 wiring):**
- `Orchestrator.__init__()` accepts `model_profile: ModelProfile | None = None`
- `_run_agent_loop` resolves `AgentRole` from `task_spec.role` string using `__members__` check
- Falls back to `AgentRole.executor` for unknown roles
- `model_profile.get_model(agent_role)` result passed to `ACPClient(model=model)`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test_identity.py and test_orchestrator_models.py for lean prompt**
- **Found during:** Task 1
- **Issue:** Existing tests asserted `task_description` text was IN the system prompt; lean prompt intentionally omits it
- **Fix:** Updated tests to assert task_description NOT in prompt, and that "Read these files" section omitted when no material files
- **Files modified:** tests/test_identity.py, tests/test_orchestrator_models.py
- **Commit:** 82f2430

## Self-Check

Files exist:
- [x] packages/conductor-core/src/conductor/acp/client.py
- [x] packages/conductor-core/src/conductor/orchestrator/identity.py
- [x] packages/conductor-core/src/conductor/orchestrator/orchestrator.py
- [x] packages/conductor-core/tests/test_orchestrator.py

Commits exist:
- [x] 82f2430 — Task 1 implementation
- [x] 77337da — Task 2 RED tests
- [x] afbdbde — Task 2 GREEN implementation

Test results: 484 passed, 0 failed

## Self-Check: PASSED
