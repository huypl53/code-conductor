---
phase: 07-agent-runtime
plan: 02
subsystem: acp-client, orchestrator
tags: [session-resume, session-registry, persistence, acp, tdd]
dependency_graph:
  requires: [07-01]
  provides: [RUNT-03]
  affects: [orchestrator]
tech_stack:
  added: []
  patterns: [atomic-write, filelock, tdd-red-green]
key_files:
  created:
    - packages/conductor-core/src/conductor/orchestrator/session_registry.py
    - packages/conductor-core/tests/test_session_registry.py
  modified:
    - packages/conductor-core/src/conductor/acp/client.py
    - packages/conductor-core/tests/test_acp_client.py
decisions:
  - "ACPClient resume parameter positioned after system_prompt to preserve existing keyword-only API order"
  - "SessionRegistry.load() silently returns empty registry on missing/invalid JSON — crash-safe startup"
  - "filelock lock file placed at path.with_suffix('.json.lock') — mirrors StateManager pattern for consistency"
metrics:
  duration: 2m 12s
  completed_date: "2026-03-10"
  tasks_completed: 2
  files_created: 2
  files_modified: 2
---

# Phase 7 Plan 2: Session Resume and SessionRegistry Summary

ACPClient extended with resume parameter pass-through to ClaudeAgentOptions, plus new SessionRegistry class for persistent agent-to-session ID mapping using atomic JSON writes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add resume parameter to ACPClient | 2490f71 | client.py, test_acp_client.py |
| 2 | Create SessionRegistry for agent-to-session mapping | 575e72d | session_registry.py, test_session_registry.py |

## What Was Built

### Task 1: ACPClient resume parameter (TDD)

Added `resume: str | None = None` parameter to `ACPClient.__init__()` positioned after `system_prompt`. The value is passed directly through to `ClaudeAgentOptions(resume=resume)`. Three tests verify:
- `resume="sess-abc"` propagates to `ClaudeAgentOptions.resume`
- Default construction sets `resume=None`
- Explicit `resume=None` passes through correctly

### Task 2: SessionRegistry (TDD)

New class at `conductor/orchestrator/session_registry.py` implementing:
- `register(agent_id, session_id)` — stores mapping, overwrites on repeat
- `get(agent_id)` — returns session_id or None
- `remove(agent_id)` — no-op on unknown agent
- `save(path)` — atomic write using filelock + tempfile + os.replace (same pattern as StateManager)
- `SessionRegistry.load(path)` — returns empty registry on missing/corrupt file (crash-safe)

13 tests cover all CRUD operations, persistence edge cases, and full round-trip verification.

## Verification Results

```
29 passed in 0.40s  (test_acp_client.py + test_session_registry.py)
235 passed in 1.10s (full test suite — zero regressions)
ruff check: All checks passed!
```

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

Files exist:
- packages/conductor-core/src/conductor/acp/client.py: FOUND (resume parameter added)
- packages/conductor-core/src/conductor/orchestrator/session_registry.py: FOUND (SessionRegistry class)
- packages/conductor-core/tests/test_session_registry.py: FOUND (13 tests)

Commits:
- d3c03b2: FOUND (failing tests for ACPClient resume)
- 2490f71: FOUND (ACPClient resume implementation)
- 4459daa: FOUND (failing tests for SessionRegistry)
- 575e72d: FOUND (SessionRegistry implementation)
