---
phase: 40-borderless
plan: 01
subsystem: tui
tags: [css, borderless, visual-design]
dependency_graph:
  requires: []
  provides: [VIS-01, VIS-02]
  affects: [transcript-widgets, command-input]
tech_stack:
  added: []
  patterns: [subtle-accent-lines, borderless-layout]
key_files:
  created:
    - packages/conductor-core/tests/test_tui_borderless.py
  modified:
    - packages/conductor-core/src/conductor/tui/widgets/transcript.py
    - packages/conductor-core/src/conductor/tui/widgets/command_input.py
decisions:
  - "solid border-left at 40% opacity replaces thick for subtle accent lines"
  - "border-top removed entirely (no border: none replacement) for cleanest approach"
metrics:
  duration: 1min
  completed: "2026-03-11T16:38:16Z"
---

# Phase 40 Plan 01: Borderless Design Summary

CSS-only borderless design: removed CommandInput border-top separator, replaced thick cell border-left markers with solid accent lines at 40% opacity for content-first aesthetic.

## What Was Built

Three targeted CSS edits across two source files:

1. **transcript.py UserCell**: `border-left: thick $primary` changed to `border-left: solid $primary 40%`
2. **transcript.py AssistantCell**: `border-left: thick $accent` changed to `border-left: solid $accent 40%`
3. **command_input.py CommandInput**: `border-top: solid $primary 30%` line removed entirely

## Files Modified

| File | Change |
|------|--------|
| `tests/test_tui_borderless.py` | New: 5 CSS regression tests for VIS-01 and VIS-02 |
| `widgets/transcript.py` | 2 lines: thick -> solid at 40% opacity |
| `widgets/command_input.py` | 1 line removed: border-top declaration |

## Unchanged (Guard Tests Confirm)

- **AgentMonitorPane**: `border-left: solid $primary 20%` retained (column separator)
- **FileApprovalModal, CommandApprovalModal, EscalationModal**: `border: solid $primary` retained (modal overlay chrome)

## Test Results

- 5/5 borderless tests passing (test_tui_borderless.py)
- 652/652 full suite passing (no regressions)

## Commits

| Hash | Message |
|------|---------|
| 733c725 | test(40-01): add failing tests for borderless design VIS-01 and VIS-02 |
| a688c5c | feat(40-01): implement borderless design for conductor TUI |

## Deviations from Plan

None - plan executed exactly as written.
