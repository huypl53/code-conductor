---
phase: 32-static-tui-shell
plan: 01
subsystem: ui
tags: [textual, tui, widgets, python]

# Dependency graph
requires:
  - phase: 31-tui-foundation
    provides: ConductorApp skeleton with event loop, lifecycle, background task tracking
provides:
  - TranscriptPane with UserCell and AssistantCell widgets
  - CommandInput with UserSubmitted message routing
  - AgentMonitorPane placeholder widget
  - StatusFooter docked bottom bar
  - Two-column CSS layout for Conductor TUI
affects: [33-sdk-streaming, 35-delegation-ui, 37-slash-commands]

# Tech tracking
tech-stack:
  added: []
  patterns: [Textual message posting for widget-to-widget communication, DEFAULT_CSS per widget, lazy imports in compose()]

key-files:
  created:
    - packages/conductor-core/src/conductor/tui/widgets/__init__.py
    - packages/conductor-core/src/conductor/tui/widgets/transcript.py
    - packages/conductor-core/src/conductor/tui/widgets/command_input.py
    - packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py
    - packages/conductor-core/src/conductor/tui/widgets/status_footer.py
    - packages/conductor-core/tests/test_tui_shell.py
  modified:
    - packages/conductor-core/src/conductor/tui/app.py
    - packages/conductor-core/src/conductor/tui/conductor.tcss
    - packages/conductor-core/src/conductor/tui/messages.py

key-decisions:
  - "Used on_user_submitted handler name (Textual routes by message class name, not widget namespace)"
  - "Lazy imports inside compose() to avoid circular dependencies and keep tui.app import lightweight"

patterns-established:
  - "Widget DEFAULT_CSS pattern: each widget owns its own CSS via DEFAULT_CSS class variable"
  - "Message routing pattern: widgets post custom Message subclasses, app-level handlers route between widgets"
  - "Headless test pattern: always inline run_test() in each test function, never in fixtures"

requirements-completed: [TRNS-01]

# Metrics
duration: 3min
completed: 2026-03-11
---

# Phase 32: Static TUI Shell Summary

**Two-column Textual TUI layout with TranscriptPane, AgentMonitorPane, CommandInput, and StatusFooter -- typing a message adds a UserCell to the scrollable transcript**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-11T13:42:55Z
- **Completed:** 2026-03-11T13:45:42Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Created four TUI widget modules (TranscriptPane, CommandInput, AgentMonitorPane, StatusFooter) in a new widgets/ package
- Wired ConductorApp.compose() to render the two-column layout replacing the Phase 31 placeholder
- Added UserSubmitted message type and message routing from CommandInput to TranscriptPane
- 9 new headless tests all passing, 594 total tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create widgets package and four layout widgets** - `a7eca48` (feat)
2. **Task 2 RED: Add failing headless tests** - `9c026bf` (test)
3. **Task 2 GREEN: Wire ConductorApp layout** - `35d2236` (feat)

## Files Created/Modified
- `packages/conductor-core/src/conductor/tui/widgets/__init__.py` - Package marker
- `packages/conductor-core/src/conductor/tui/widgets/transcript.py` - TranscriptPane, UserCell, AssistantCell widgets
- `packages/conductor-core/src/conductor/tui/widgets/command_input.py` - CommandInput with UserSubmitted posting on Enter
- `packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py` - AgentMonitorPane placeholder
- `packages/conductor-core/src/conductor/tui/widgets/status_footer.py` - StatusFooter docked bottom bar
- `packages/conductor-core/src/conductor/tui/messages.py` - Added UserSubmitted message class
- `packages/conductor-core/src/conductor/tui/app.py` - Replaced placeholder compose() with four-widget layout + message handler
- `packages/conductor-core/src/conductor/tui/conductor.tcss` - Updated to Phase 32 horizontal layout
- `packages/conductor-core/tests/test_tui_shell.py` - 9 headless tests for layout and message routing

## Decisions Made
- Used `on_user_submitted` handler name instead of `on_command_input_user_submitted` -- Textual routes messages by the Message class name, not by the posting widget's namespace
- Kept all imports inside compose() and handler methods (lazy imports) to avoid circular dependencies and keep the tui.app module import lightweight
- Each widget defines its own DEFAULT_CSS rather than putting everything in conductor.tcss -- follows Textual best practice for encapsulated widget styling

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed message handler name for Textual routing**
- **Found during:** Task 2 GREEN phase
- **Issue:** Plan specified `on_command_input_user_submitted` but Textual routes by message class name (`UserSubmitted`), not widget namespace
- **Fix:** Changed handler to `on_user_submitted` which matches Textual's message routing convention
- **Files modified:** packages/conductor-core/src/conductor/tui/app.py
- **Verification:** test_submit_message_adds_user_cell passes
- **Committed in:** 35d2236

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Handler name correction was necessary for Textual message routing to work. No scope creep.

## Issues Encountered
None beyond the handler name fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All four layout widgets are in place and tested
- TranscriptPane.add_user_message() API ready for Phase 33 SDK streaming integration
- AgentMonitorPane ready for Phase 35 delegation UI wiring
- StatusFooter ready for Phase 33 TokensUpdated message subscription

---
*Phase: 32-static-tui-shell*
*Completed: 2026-03-11*
