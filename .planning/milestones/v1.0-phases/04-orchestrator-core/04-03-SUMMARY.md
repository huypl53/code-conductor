---
phase: 04-orchestrator-core
plan: "03"
subsystem: orchestrator
tags: [claude-agent-sdk, structured-output, asyncio, semaphore, task-decomposition, agent-spawning, tdd]

# Dependency graph
requires:
  - phase: 04-orchestrator-core plan 01
    provides: TaskSpec, TaskPlan, AgentIdentity, build_system_prompt, DecompositionError, OrchestratorError
  - phase: 04-orchestrator-core plan 02
    provides: DependencyScheduler, validate_file_ownership, FileConflictError
  - phase: 03-acp-communication-layer
    provides: ACPClient async context manager for sub-agent sessions
  - phase: 02-shared-state-infrastructure
    provides: StateManager, ConductorState, Task, AgentRecord, TaskStatus, AgentStatus
provides:
  - TaskDecomposer: SDK query() with output_format JSON schema for structured TaskPlan decomposition
  - Orchestrator: full decompose -> validate -> schedule -> spawn loop with concurrency control
  - DECOMPOSE_PROMPT_TEMPLATE with role anchoring and XML boundary injection guards
  - 14 new tests covering all ORCH-01/02 behaviors (6 decomposer + 8 orchestrator)
affects:
  - 05-cli (CLI entry point that drives Orchestrator.run())
  - 08-packaging (Orchestrator is the top-level public API)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SDK structured output: query() with output_format json_schema + TaskPlan.model_json_schema()"
    - "Prompt injection mitigation: XML boundary tags <feature_description> around user input"
    - "Role anchoring: 'software architect and project coordinator. You do not write code.'"
    - "asyncio.Semaphore(min(plan.max_agents, config.max_agents)) for concurrent session cap"
    - "asyncio.to_thread(state.mutate, fn) for async-safe file-locked state writes"
    - "DependencyScheduler get_ready()/done() driving asyncio task creation in spawn loop"
    - "asyncio.wait(FIRST_COMPLETED) for wave-based parallel spawning with dependency order"

key-files:
  created:
    - packages/conductor-core/src/conductor/orchestrator/decomposer.py
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/tests/test_decomposer.py
    - packages/conductor-core/tests/test_orchestrator.py
  modified:
    - packages/conductor-core/src/conductor/orchestrator/__init__.py

key-decisions:
  - "DECOMPOSE_PROMPT_TEMPLATE uses XML boundary <feature_description> tags to mitigate prompt injection from untrusted feature descriptions"
  - "Role anchoring text 'You do not write code' placed at prompt start, not middle — anchors LLM behavior for long decomposition sessions"
  - "Orchestrator.run() uses asyncio.wait(FIRST_COMPLETED) not gather() — enables wave-based scheduling where ready tasks unblock immediately as deps complete"
  - "asyncio.to_thread() wraps all StateManager.mutate() calls — StateManager uses filelock (blocking I/O), must not block event loop"
  - "AgentRecord written to state before ACPClient.__aenter__ — ensures state reflects in-flight agents even if session crashes before cleanup"

patterns-established:
  - "Pattern: TDD RED-GREEN with structural patch.object for Orchestrator._spawn_agent in dependency/concurrency tests"
  - "Pattern: asyncio.Semaphore(effective_max) cap computed with min(plan.max_agents, config.max_agents) — plan can only lower the cap, never raise it"
  - "Pattern: static factory methods _make_add_tasks_fn / _make_add_agent_fn / _make_complete_task_fn return Callable[[ConductorState], None] for StateManager.mutate"

requirements-completed: [ORCH-01, ORCH-02]

# Metrics
duration: 4min
completed: 2026-03-10
---

# Phase 4 Plan 03: Orchestrator Core Summary

**TaskDecomposer with SDK structured output (role-anchored, XML-bounded prompt) and Orchestrator running the full decompose-validate-schedule-spawn loop with asyncio.Semaphore concurrency control and state tracking**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-10T16:22:03Z
- **Completed:** 2026-03-10T16:26:04Z
- **Tasks:** 2 (TDD: each has RED + GREEN commits)
- **Files modified:** 5

## Accomplishments

- TaskDecomposer wraps SDK query() with TaskPlan.model_json_schema() as output_format, DECOMPOSE_PROMPT_TEMPLATE guards against prompt injection and provides role anchoring
- Orchestrator.run() delivers the full loop: decompose -> validate_file_ownership -> write Tasks to state -> DependencyScheduler waves -> asyncio.Semaphore-capped _spawn_agent calls
- _spawn_agent writes AgentRecord to state before opening ACPClient session, then marks task COMPLETED after session closes
- 133 tests pass total (119 pre-existing + 14 new), ruff clean, pyright 0 errors

## Task Commits

Each task was committed atomically (TDD):

1. **RED: Failing tests for TaskDecomposer** - `2a154cd` (test)
2. **GREEN: TaskDecomposer implementation** - `92c2f01` (feat)
3. **RED: Failing tests for Orchestrator** - `bf4fb4d` (test)
4. **GREEN: Orchestrator implementation + __init__.py exports** - `70a5aa2` (feat)

## Files Created/Modified

- `packages/conductor-core/src/conductor/orchestrator/decomposer.py` - TaskDecomposer with DECOMPOSE_PROMPT_TEMPLATE, SDK query() structured output, all DecompositionError guards
- `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` - Orchestrator with decompose-validate-schedule-spawn loop, _spawn_agent, state write helpers
- `packages/conductor-core/src/conductor/orchestrator/__init__.py` - Added TaskDecomposer and Orchestrator to public API exports
- `packages/conductor-core/tests/test_decomposer.py` - 6 ORCH-01 tests: valid plan, retry error, no result, None output, XML boundary, role anchoring
- `packages/conductor-core/tests/test_orchestrator.py` - 8 ORCH-02 tests: spawn count, conflict, dep order, cap, agent record timing, identity prompt, min max, completion status

## Decisions Made

- DECOMPOSE_PROMPT_TEMPLATE uses `<feature_description>` XML tags around user input to prevent prompt injection
- Role anchoring "You do not write code" is at prompt start to maintain LLM behavior across long decomposition
- `asyncio.wait(FIRST_COMPLETED)` drives the spawn loop — ready tasks unblock as dependencies complete (wave-based)
- `asyncio.to_thread()` wraps all `StateManager.mutate()` — filelock is blocking I/O, must not block event loop
- AgentRecord written to state BEFORE `ACPClient.__aenter__` — state remains consistent even if session crashes

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Ruff E501 (line > 88 chars) in DecompositionError message string — fixed inline before Task 1 commit. One-line split into two string literals.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Orchestrator is the complete core loop, ready for CLI integration (Phase 5/8)
- TaskDecomposer and Orchestrator are exported from `conductor.orchestrator` public API
- All 133 tests pass; codebase is clean

---
*Phase: 04-orchestrator-core*
*Completed: 2026-03-10*
