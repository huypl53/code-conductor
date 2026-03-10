---
phase: 07-agent-runtime
plan: 03
subsystem: orchestrator
tags: [orchestrator, session-persistence, resume, mode-wiring, spec-review, auto-mode, tdd]
dependency_graph:
  requires:
    - phase: 07-01
      provides: AgentRecord.session_id/memory_file/started_at, build_system_prompt memory section
    - phase: 07-02
      provides: ACPClient.resume parameter, SessionRegistry class
  provides:
    - Orchestrator mode/queue wiring with EscalationRouter
    - .memory/ directory creation before agent spawn
    - session_id persistence to AgentRecord before first send
    - Orchestrator.resume() for IN_PROGRESS task recovery after restart
    - pre_run_review() single-exchange spec analysis via query()
    - run_auto() entry point chaining pre_run_review -> run
  affects: [08-cli, phase-8]
tech-stack:
  added: []
  patterns: [tdd-red-green, single-exchange-query, crash-safe-session-persistence]
key-files:
  created: []
  modified:
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/tests/test_orchestrator.py
key-decisions:
  - "Orchestrator.__init__ loads SessionRegistry from .conductor/sessions.json at startup — crash-safe, empty registry returned on missing file"
  - "session_id persisted via get_server_info() inside try/except BLE001 — missing/unavailable method is a warning, not a fatal error"
  - "_make_add_agent_fn now sets memory_file=.memory/<agent_id>.md and started_at — full AgentRecord completeness at spawn time"
  - "pre_run_review() uses query() (single-exchange, no PermissionHandler) — never blocks on human input in auto mode"
  - "SpecReview Pydantic model with is_clear/issues/confirmed_description — structured output enforced via JSON schema"
  - "run_auto() is the CLI entry point — chains pre_run_review then run, gives auto mode its upfront review gate"
  - "All existing TestOrchestrator tests updated to use tmp_path — required by .memory/ mkdir in run()"
patterns-established:
  - "Pre-send persistence: session_id persisted BEFORE first client.send() for crash safety"
  - "Single-exchange review: query() with ClaudeAgentOptions(output_format=json_schema) for structured AI responses without full session"
  - "Resume recovery: Orchestrator.resume() reads IN_PROGRESS state + SessionRegistry, passes session_id to _run_agent_loop"
requirements-completed: [RUNT-03, RUNT-04, RUNT-05]
duration: 12min
completed: "2026-03-10"
---

# Phase 7 Plan 3: Orchestrator Runtime Wiring Summary

**Orchestrator extended with mode/queue params, EscalationRouter wiring, .memory/ dir creation, session_id persistence before first send, resume() for crash recovery, SpecReview model, and run_auto() entry point for --auto CLI mode.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-10T17:51:48Z
- **Completed:** 2026-03-10T18:03:04Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Orchestrator now accepts `mode`, `human_out`, `human_in` params and wires to `EscalationRouter` — interactive mode is fully plumbed
- `.memory/` directory created before agents spawn — all sub-agents find their memory files on first write
- session_id retrieved via `get_server_info()` and persisted to `AgentRecord` + `SessionRegistry` BEFORE first `send()` — crash-safe restart recovery
- `resume()` method reads state, finds `IN_PROGRESS` tasks, looks up session IDs, re-spawns with `resume=session_id` (or fresh session if none stored)
- `pre_run_review()` runs single-exchange spec analysis without human interaction — surfaces ambiguities via `SpecReview` structured output
- `run_auto()` chains `pre_run_review` then `run` — provides the `--auto` CLI entry point (Phase 8)

## Task Commits

1. **Test RED - Task 1 (mode/memory/session/resume):** `432ab3c` (test)
2. **Task 1: Mode wiring, .memory/, session persistence, resume:** `eaa1dca` (feat)
3. **Test RED - Task 2 (pre_run_review/run_auto):** `03cf206` (test)
4. **Task 2: pre_run_review and run_auto:** `3852b64` (feat)

## Files Created/Modified

- `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — Added mode/queue params, EscalationRouter, SessionRegistry, .memory/ dir creation, session_id persistence, _make_save_session_fn, resume(), SpecReview model, SPEC_REVIEW_PROMPT_TEMPLATE, pre_run_review(), run_auto()
- `packages/conductor-core/tests/test_orchestrator.py` — Added 16 new tests across 6 classes; updated all existing `run()`-calling tests to use `tmp_path` fixture

## Decisions Made

- `Orchestrator.__init__` loads `SessionRegistry` from `.conductor/sessions.json` via `SessionRegistry.load()` — crash-safe empty registry returned on missing file, mirrors `StateManager` pattern
- `get_server_info()` wrapped in `try/except Exception` (BLE001 suppressed in context) — SDK version availability uncertainty documented in research, not fatal
- `_make_add_agent_fn` now sets `memory_file=f".memory/{agent_id}.md"` and `started_at=datetime.now(UTC)` — completes the AgentRecord at spawn, matching Plan 01 model design
- `pre_run_review()` uses `query()` directly (not `ACPClient`/`ClaudeSDKClient`) — single-exchange query is the correct SDK primitive for no-session structured output
- `SpecReview` defined in `orchestrator.py` (not `models.py`) — only used by this class, no reason to share
- `run_auto()` is thin — two awaits — intentionally minimal so CLI can easily call it

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated all existing `run()`-calling tests to use `tmp_path`**
- **Found during:** Task 1 GREEN — `.memory/` mkdir fails on non-existent `/repo` path
- **Issue:** `run()` now calls `Path(repo_path) / ".memory" / mkdir()` but all existing tests used `repo_path="/repo"` which doesn't exist
- **Fix:** Updated 8 test methods in `TestOrchestrator`, `TestOrch04CompleteGate`, `TestOrch05RevisionSend`, `TestOrch05MaxRevisions`, `TestOrch05SessionOpenForRevision` to accept `tmp_path` fixture and pass `str(tmp_path)` as `repo_path`
- **Files modified:** `tests/test_orchestrator.py`
- **Verification:** Full suite 246 tests pass after fix

**2. [Rule 1 - Bug] ResultMessage requires `session_id` positional argument**
- **Found during:** Task 2 GREEN — `ResultMessage.__init__()` missing required `session_id` arg
- **Issue:** SDK version in project requires `session_id` in `ResultMessage` constructor; test helper didn't pass it
- **Fix:** Added `session_id="test-session-id"` to `_make_spec_review_result()` helper
- **Files modified:** `tests/test_orchestrator.py`

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for correctness. No scope creep.

## Issues Encountered

- `isinstance(message, ResultMessage)` check in `pre_run_review()` requires real `ResultMessage` instances (not MagicMock). Solved by creating `_make_spec_review_result()` helper that returns real SDK objects — consistent with existing `test_decomposer.py` pattern.

## Next Phase Readiness

- Orchestrator fully wired for runtime: mode, memory, session persistence, restart recovery, and upfront spec review
- `run_auto()` is the Phase 8 CLI entry point — takes a feature description, reviews it, runs autonomously
- `resume()` ready for CLI `--resume` flag in Phase 8
- Phase 8 (CLI) can wire `asyncio.Queue` pairs to terminal I/O for interactive mode

## Self-Check: PASSED
