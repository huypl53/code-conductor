---
phase: 36-approval-modals
plan: 02
subsystem: tui
tags: [modals, escalation, queue-bridge, textual, wiring]
dependency_graph:
  requires: [FileApprovalModal, CommandApprovalModal, EscalationModal, EscalationRequest]
  provides: [_watch_escalations, human_out_queue, human_in_queue]
  affects: [conductor.tui.app, conductor.cli.delegation]
tech_stack:
  added: []
  patterns: [push_screen_wait in @work coroutine, asyncio.Queue bridge]
key_files:
  created: []
  modified:
    - packages/conductor-core/src/conductor/tui/app.py
    - packages/conductor-core/src/conductor/cli/delegation.py
    - packages/conductor-core/tests/test_tui_approval.py
key_decisions:
  - "Escalation listener in DelegationManager only starts for non-TUI (input_fn) paths; TUI uses ConductorApp._watch_escalations"
  - "All escalation types routed through EscalationModal for now; FileApprovalModal/CommandApprovalModal available for future context-based routing"
  - "Focus restored to CommandInput after modal dismissal via explicit focus() call"
metrics:
  duration: 145s
  completed: "2026-03-11T14:55:10Z"
  tests_added: 2
  tests_total: 622
---

# Phase 36 Plan 02: Wire Escalation Queue to Modal Overlays Summary

Wired asyncio.Queue bridge from DelegationManager to ConductorApp via _watch_escalations @work coroutine that shows EscalationModal for incoming HumanQuery objects and relays replies back through human_in.

## What Was Done

### Task 1: Expose delegation queues and add _watch_escalations worker

**delegation.py changes:**
- Added `human_out_queue` and `human_in_queue` read-only properties to DelegationManager
- Guarded `_escalation_task` creation in `handle_delegate()` to only fire when `self._input_fn is not None` (non-TUI path), matching the existing guard in `resume_delegation()`

**app.py changes:**
- Added `self._delegation_manager` attribute in `__init__`
- Stored delegation_manager reference in `_ensure_sdk_connected()` before SDK connect
- Added `_start_escalation_watcher()` helper that checks for queue availability
- Added `_watch_escalations()` as `@work(exclusive=False, exit_on_error=False)` coroutine that:
  - Drains `human_out` queue for HumanQuery objects
  - Extracts `agent_id` from HumanQuery.context
  - Shows EscalationModal via `push_screen_wait()`
  - Puts user reply into `human_in` queue
  - Restores focus to CommandInput after modal dismissal

Commit: `137a070` -- feat(36-02): wire escalation queue to modal overlays in ConductorApp

### Task 2: Integration tests for escalation-to-modal flow

Added 2 integration tests using real ConductorApp with asyncio.Queue:
- `test_escalation_queue_shows_modal`: Puts HumanQuery on human_out, verifies EscalationModal appears on screen stack, submits reply, asserts reply reaches human_in
- `test_modal_dismisses_and_input_refocuses`: Verifies CommandInput's inner Input widget has focus after modal dismissal

Commit: `8b8e190` -- test(36-02): add integration tests for escalation queue-to-modal flow

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `pytest tests/test_tui_approval.py -x -v` -- 11/11 passed (9 unit + 2 integration)
- `pytest --tb=short -q` -- 622 passed (full suite green)
- `grep "_watch_escalations" app.py` -- worker exists
- `grep "human_out_queue" delegation.py` -- property exists

## Self-Check: PASSED
