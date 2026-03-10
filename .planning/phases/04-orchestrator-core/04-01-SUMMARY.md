---
phase: 04-orchestrator-core
plan: 01
subsystem: orchestrator
tags: [pydantic, type-contracts, error-hierarchy, agent-identity, system-prompt]

# Dependency graph
requires:
  - phase: 02-shared-state-infrastructure
    provides: Task, ConductorState, StateError hierarchy — extended Task model with new fields
  - phase: 03-acp-communication-layer
    provides: ACPClient, permission model — context for agent spawning patterns
provides:
  - OrchestratorError hierarchy (DecompositionError, CycleError, FileConflictError)
  - TaskSpec and TaskPlan Pydantic v2 models for structured decomposition output
  - AgentIdentity model and build_system_prompt() function
  - Extended Task state model with requires/produces/target_file/material_files fields
affects: [04-02-scheduler-ownership, 04-03-decomposer-orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns: [pydantic-v2-models, error-hierarchy, contracts-first, tdd-red-green]

key-files:
  created:
    - packages/conductor-core/src/conductor/orchestrator/errors.py
    - packages/conductor-core/src/conductor/orchestrator/models.py
    - packages/conductor-core/src/conductor/orchestrator/identity.py
    - packages/conductor-core/tests/test_orchestrator_models.py
  modified:
    - packages/conductor-core/src/conductor/orchestrator/__init__.py
    - packages/conductor-core/src/conductor/state/models.py

key-decisions:
  - "CycleError stores cycle as list[str] via .cycle attribute — enables graph debug output without string parsing"
  - "FileConflictError stores task_a, task_b, files attributes — caller can format error messages as needed"
  - "TaskPlan.model_json_schema() is the output_format contract for SDK structured decomposition — no extra schema work needed"
  - "Task state model extended with all-default new fields (requires, produces, target_file, material_files) — backward compat with existing serialized state guaranteed"
  - "build_system_prompt() includes 'Do not modify files outside your assignment' as explicit constraint — role anchoring for long sessions"

patterns-established:
  - "Contracts-first: define all Pydantic models and error types before implementation phases"
  - "Backward-compat extension: always add new Task fields with defaults so existing state.json remains valid"
  - "TDD red-green: write test file first (ImportError = RED), implement to pass (GREEN)"

requirements-completed: [ORCH-06]

# Metrics
duration: 3min
completed: 2026-03-10
---

# Phase 4 Plan 01: Orchestrator Type Contracts Summary

**Pydantic v2 orchestrator type contracts: OrchestratorError hierarchy, TaskSpec/TaskPlan decomposition models, AgentIdentity with system prompt builder, and backward-compatible Task state extension**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-10T16:10:49Z
- **Completed:** 2026-03-10T16:14:03Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Error hierarchy with OrchestratorError base and three specialized subclasses (DecompositionError, CycleError, FileConflictError) with typed attributes
- TaskSpec and TaskPlan Pydantic v2 models producing valid JSON Schema for SDK `output_format` structured decomposition
- AgentIdentity model and build_system_prompt() producing complete agent identity prompts with role-anchoring constraint
- Task state model extended with requires/produces/target_file/material_files — fully backward-compatible, all 98 tests pass

## Task Commits

Each task was committed atomically:

1. **RED: Failing tests** - `3c72c13` (test)
2. **Task 1: Error hierarchy + TaskSpec/TaskPlan models** - `b7353fd` (feat)
3. **Task 2: AgentIdentity + extended Task model** - `ce7132f` (feat)

## Files Created/Modified

- `packages/conductor-core/src/conductor/orchestrator/errors.py` - OrchestratorError, DecompositionError, CycleError, FileConflictError
- `packages/conductor-core/src/conductor/orchestrator/models.py` - TaskSpec, TaskPlan Pydantic v2 models
- `packages/conductor-core/src/conductor/orchestrator/identity.py` - AgentIdentity model and build_system_prompt()
- `packages/conductor-core/src/conductor/orchestrator/__init__.py` - Re-exports all public types
- `packages/conductor-core/src/conductor/state/models.py` - Task extended with requires, produces, target_file, material_files
- `packages/conductor-core/tests/test_orchestrator_models.py` - 43 tests covering all new types

## Decisions Made

- CycleError stores cycle as `list[str]` via `.cycle` attribute — enables graph debug output without string parsing
- FileConflictError stores `task_a`, `task_b`, `files` attributes — caller can format error messages as needed
- `TaskPlan.model_json_schema()` is the output_format contract for SDK structured decomposition
- Task state model extended with all-default new fields — backward compat with existing serialized state.json guaranteed
- `build_system_prompt()` includes "Do not modify files outside your assignment" as explicit constraint for role anchoring

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Ruff E501 line too long in errors.py docstring (91 > 88 chars) — fixed inline before Task 1 commit.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All type contracts are established for Plans 02 and 03 to implement against
- TaskSpec/TaskPlan ready as `output_format` for SDK decomposer calls
- AgentIdentity/build_system_prompt ready for agent spawning in orchestrator
- Extended Task model ready for scheduler ownership tracking

---
*Phase: 04-orchestrator-core*
*Completed: 2026-03-10*
