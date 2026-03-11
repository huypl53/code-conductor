---
phase: 26-models-scheduler-infrastructure
plan: 01
subsystem: orchestrator
tags: [models, scheduler, infrastructure, config]
dependency_graph:
  requires: []
  provides: [OrchestratorConfig, ModelProfile, AgentRole, compute_waves]
  affects: [orchestrator.py, __init__.py]
tech_stack:
  added: [StrEnum]
  patterns: [pydantic-basemodel, classmethod-presets, scratch-sorter-pattern]
key_files:
  created:
    - packages/conductor-core/tests/test_orchestrator_models.py (extended with OrchestratorConfig, AgentRole, ModelProfile tests)
    - packages/conductor-core/tests/test_scheduler.py (extended with TestComputeWaves)
  modified:
    - packages/conductor-core/src/conductor/orchestrator/models.py
    - packages/conductor-core/src/conductor/orchestrator/scheduler.py
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/src/conductor/orchestrator/__init__.py
decisions:
  - "compute_waves() uses a scratch TopologicalSorter built from self._graph to avoid consuming the active sorter"
  - "Explicit max_revisions/max_agents params override config when non-default, preserving backward compat"
  - "AgentRole uses StrEnum so values are plain strings and JSON-serializable"
metrics:
  duration: "~15 minutes"
  completed_date: "2026-03-11"
  tasks_completed: 2
  files_changed: 6
---

# Phase 26 Plan 01: Models & Scheduler Infrastructure Summary

**One-liner:** Pydantic OrchestratorConfig/ModelProfile/AgentRole models plus compute_waves() scheduler method wired into the Orchestrator constructor.

## What Was Built

### Task 1: OrchestratorConfig, ModelProfile, AgentRole, compute_waves()

Added three new constructs to `models.py`:

- `AgentRole` (StrEnum): decomposer, reviewer, executor, verifier — plain string values, JSON-serializable
- `OrchestratorConfig` (BaseModel): max_review_iterations=2, max_decomposition_retries=3, max_agents=10
- `ModelProfile` (BaseModel): name + role_models dict with `get_model()` fallback chain and three class-method presets: `quality()`, `balanced()`, `budget()`

Added `compute_waves()` to `DependencyScheduler` in `scheduler.py`:
- Stores original graph in `self._graph` during `__init__`
- Creates a fresh `TopologicalSorter` from `self._graph` on each call — never touches `self._sorter`
- Returns `list[list[str]]` grouping task IDs by execution wave

Updated `__init__.py` to export `OrchestratorConfig`, `ModelProfile`, `AgentRole`.

### Task 2: Wire OrchestratorConfig into Orchestrator

Updated `orchestrator.py`:
- Added `config: OrchestratorConfig | None = None` parameter (after `build_command`)
- Stores as `self._config = config or OrchestratorConfig()`
- Derives `_max_revisions` and `_max_agents` from config when constructor params are at their defaults (2 and 10 respectively)
- Explicit non-default values for `max_revisions`/`max_agents` still override config — backward compatible

## Tests

- 22 new tests for OrchestratorConfig, AgentRole, ModelProfile in `test_orchestrator_models.py`
- 6 new tests for `compute_waves()` in `test_scheduler.py`
- 6 new tests for OrchestratorConfig wiring in `test_orchestrator.py`
- All 477 tests pass (up from 471 before this phase)

## Commits

- `6e30ddf`: feat(26-01): add OrchestratorConfig, ModelProfile, AgentRole models and compute_waves()
- `3e18aa9`: feat(26-01): wire OrchestratorConfig into Orchestrator constructor

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/orchestrator/models.py` — FOUND, contains `class OrchestratorConfig`
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/orchestrator/scheduler.py` — FOUND, contains `def compute_waves`
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — FOUND, contains `OrchestratorConfig`
- Commit `6e30ddf` — FOUND
- Commit `3e18aa9` — FOUND
- All 477 tests pass
