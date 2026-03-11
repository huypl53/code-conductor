---
phase: 42-ctrl-g-external-editor
plan: 01
subsystem: tui
tags: [editor, keybinding, suspend, terminal]
dependency_graph:
  requires: []
  provides: [ctrl-g-editor, editor-content-ready-message]
  affects: [command-input, conductor-app]
tech_stack:
  added: []
  patterns: ["@work(thread=True) for sync suspend", "call_from_thread for thread-safe message posting"]
key_files:
  created:
    - packages/conductor-core/tests/test_tui_external_editor.py
  modified:
    - packages/conductor-core/src/conductor/tui/messages.py
    - packages/conductor-core/src/conductor/tui/app.py
    - packages/conductor-core/src/conductor/tui/widgets/command_input.py
decisions:
  - "Post EditorContentReady to CommandInput widget directly (not app) -- Textual messages bubble UP, so app.post_message would not reach child widget handlers"
metrics:
  duration: 3min
  completed: 2026-03-11
---

# Phase 42 Plan 01: Ctrl-G External Editor Summary

Ctrl-G keybinding suspends TUI via @work(thread=True) sync action, opens $VISUAL/$EDITOR (vim fallback) with temp file pre-populated from CommandInput, reads edited content back into Input widget via EditorContentReady message.

## What Was Done

### Task 1: Write failing tests (RED)
Created 6 tests covering: binding registration, message class, replay-mode guard, SuspendNotSupported guard, handler value fill, full editor flow with mock subprocess. All 6 failed as expected.

**Commit:** 3ba06e9

### Task 2: Implement and pass all tests (GREEN)
- Added `EditorContentReady(text)` message to `messages.py`
- Added `BINDINGS` with `ctrl+g -> open_editor` to `ConductorApp`
- Added `action_open_editor` as sync def with `@work(thread=True, exit_on_error=False)`:
  - Guard 1: `cmd_input.disabled` returns early (replay mode)
  - Guard 2: `SuspendNotSupported` shows warning notification
  - Guard 3: `FileNotFoundError/OSError` shows "Editor not found" notification
  - Happy path: write to temp file, suspend TUI, run editor, read back, post `EditorContentReady`
  - Editor selection: `$VISUAL > $EDITOR > vim`
  - Temp file cleanup in `finally` block
- Added `on_editor_content_ready` handler to `CommandInput`: sets `inp.value`, `inp.cursor_position`, calls `inp.focus()`

**Commit:** e6f48e2

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Message posting target corrected**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** Plan specified `self.app.post_message(EditorContentReady(...))` but Textual messages bubble UP from children to parents. Posting to app means CommandInput's `on_editor_content_ready` handler never fires.
- **Fix:** Changed to `cmd_widget.post_message(EditorContentReady(...))` -- posts directly to CommandInput widget where the handler lives.
- **Files modified:** app.py, test_tui_external_editor.py
- **Commit:** e6f48e2

## Verification

- 6/6 phase tests pass
- 663/663 full suite tests pass (no regressions)
- All 5 structural grep checks pass (binding, sync def, thread decorator, message class, handler)

## Self-Check: PASSED
