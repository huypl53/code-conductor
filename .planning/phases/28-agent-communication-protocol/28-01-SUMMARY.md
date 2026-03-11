---
phase: 28-agent-communication-protocol
plan: "01"
subsystem: orchestrator
tags: [agent-protocol, structured-output, status-routing, deviation-rules]
dependency_graph:
  requires: [phase-27-execution-routing-pipeline]
  provides: [AgentReport, parse_agent_report, STATUS_BLOCK_INSTRUCTIONS, DEVIATION_RULES, status-routing]
  affects: [orchestrator._run_agent_loop, agent-system-prompt]
tech_stack:
  added: []
  patterns: [structured-agent-output, best-effort-parsing, status-based-routing]
key_files:
  created:
    - packages/conductor-core/tests/test_agent_report.py
  modified:
    - packages/conductor-core/src/conductor/orchestrator/models.py
    - packages/conductor-core/src/conductor/orchestrator/monitor.py
    - packages/conductor-core/src/conductor/orchestrator/identity.py
    - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    - packages/conductor-core/tests/test_orchestrator.py
decisions:
  - "parse_agent_report uses best-effort regex extraction — returns None on any failure (no crash)"
  - "STATUS_BLOCK_INSTRUCTIONS and DEVIATION_RULES are prompt-only constants — no code enforcement"
  - "BLOCKED routing uses continue inside the revision loop so it counts as a revision iteration"
  - "Real ResultMessage objects required in tests (not MagicMock) because StreamMonitor uses isinstance check"
  - "Target files must exist in tests that check single-pass review or file-existence gate overrides approved=False"
metrics:
  duration_minutes: 7
  tasks_completed: 2
  files_modified: 5
  files_created: 1
  tests_added: 30
  completed_date: "2026-03-11"
---

# Phase 28 Plan 01: Agent Communication Protocol Summary

**One-liner:** Structured agent status protocol with JSON status blocks (DONE/BLOCKED/NEEDS_CONTEXT), best-effort parsing in monitor, and status-based routing in the orchestrator revision loop.

## What Was Built

### Task 1: AgentReport model, parse function, and system prompt updates

Added a structured communication protocol between agents and the orchestrator:

- `AgentReportStatus(StrEnum)` in `models.py` with four values: `DONE`, `DONE_WITH_CONCERNS`, `BLOCKED`, `NEEDS_CONTEXT`
- `AgentReport(BaseModel)` in `models.py` with `status`, `summary`, `files_changed`, `concerns` fields
- `parse_agent_report(text: str) -> AgentReport | None` in `monitor.py` — extracts fenced `\`\`\`json` blocks using regex, validates against `AgentReport`, returns `None` on any failure (best-effort, never crashes)
- `STATUS_BLOCK_INSTRUCTIONS` constant in `identity.py` — JSON schema instructions for agents
- `DEVIATION_RULES` constant in `identity.py` — four rules (fix silently for typos/imports/broken tests; STOP with BLOCKED for architectural changes)
- `build_system_prompt()` updated to append both constants to every agent prompt

### Task 2: Status-based routing in orchestrator

Added routing logic inside `_run_agent_loop` after each stream iteration:

- `DONE`: falls through to `review_output` unchanged
- `DONE_WITH_CONCERNS`: logs concerns at WARNING, falls through to `review_output`
- `BLOCKED` (auto mode): sends "Proceed with your best judgment" message, `continue` re-enters loop
- `BLOCKED` (interactive mode): pushes `HumanQuery` to `human_out`, awaits answer from `human_in`, sends answer to agent, `continue` re-enters loop
- `NEEDS_CONTEXT`: sends material file guidance message, `continue` re-enters loop
- Freeform (no parseable report): falls through to `review_output` unchanged (backward compat)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test mocks needed real ResultMessage instances**

- **Found during:** Task 2 implementation
- **Issue:** `StreamMonitor.process()` uses `isinstance(message, ResultMessage)` — `MagicMock()` fails this check, making `monitor.result_text` always None. Routing logic never triggered in tests.
- **Fix:** Added `_make_real_result_message()` helper and `_make_mock_acp_client_with_real_result()` factory using proper `ResultMessage` constructor calls
- **Files modified:** `tests/test_orchestrator.py`

**2. [Rule 1 - Bug] File existence gate caused multiple review calls in tests**

- **Found during:** Task 2 test design
- **Issue:** Tests with `target_file="src/a.py"` and non-existent file caused the file existence gate to override `approved=True` to `False`, forcing the revision loop to run all `max_revisions+1` iterations
- **Fix:** Tests that verify single-pass behavior create the target file in `tmp_path` before running

## Tests Added

- `tests/test_agent_report.py`: 24 tests covering `AgentReportStatus` enum, `AgentReport` model, `parse_agent_report` (all code paths), and system prompt content
- `tests/test_orchestrator.py` (new class `TestAgentReportRouting`): 6 tests covering DONE, freeform, DONE_WITH_CONCERNS, BLOCKED (auto), BLOCKED (interactive), and NEEDS_CONTEXT routing paths

**Total tests:** 514 (up from 508). All pass.

## Self-Check: PASSED

- models.py: `AgentReport` class found (2 occurrences)
- monitor.py: `parse_agent_report` function found
- identity.py: `STATUS_BLOCK_INSTRUCTIONS` found (2 occurrences)
- orchestrator.py: `parse_agent_report` import and usage found
- test_agent_report.py: file exists
- Commits: 814d1d5 and fc7e862 both verified in git log
- Full test suite: 514 passed, 0 failed
