---
phase: 33
plan: 01
subsystem: tui-streaming
tags: [textual, streaming, widgets, reactive, tdd]
dependency_graph:
  requires: []
  provides: [streaming-assistant-cell, reactive-status-footer, streaming-started-message]
  affects: [conductor-tui-app, sdk-streaming-worker]
tech_stack:
  added: []
  patterns: [MarkdownStream, reactive-attributes, LoadingIndicator-thinking-state]
key_files:
  created:
    - packages/conductor-core/tests/test_tui_streaming.py
  modified:
    - packages/conductor-core/src/conductor/tui/messages.py
    - packages/conductor-core/src/conductor/tui/widgets/transcript.py
    - packages/conductor-core/src/conductor/tui/widgets/status_footer.py
decisions:
  - "MarkdownStream.write() confirmed as correct API (not append()); resolves STATE.md concern"
  - "StatusFooter uses on_tokens_updated handler + reactive attributes (consistent with existing message bus)"
  - "post_message to footer directly since Textual messages bubble UP not DOWN"
metrics:
  duration_seconds: 182
  completed: "2026-03-11T14:04:17Z"
  tests_added: 5
  tests_total: 599
  files_changed: 4
requirements: [TRNS-02, STAT-01]
---

# Phase 33 Plan 01: Streaming Widget Lifecycle Summary

AssistantCell upgraded with thinking/streaming/finalized lifecycle using Textual MarkdownStream; StatusFooter wired with reactive model/mode/tokens/session display and TokensUpdated handler.

## What Was Done

### Task 1: Upgrade AssistantCell with streaming lifecycle, add StreamingStarted message, upgrade StatusFooter with reactives

**Commit:** `7300935` (feat) + `e0853ac` (test RED)

**Changes:**

1. **messages.py** -- Added `StreamingStarted` message class (no fields, signals streaming cell creation).

2. **transcript.py** -- Rewrote `AssistantCell` with dual-mode support:
   - Static mode: `AssistantCell("text")` renders immediately (backward compatible with Phase 32)
   - Streaming mode: `AssistantCell()` starts with `LoadingIndicator`, transitions via `start_streaming()` to `Markdown` with `MarkdownStream`, accepts tokens via `append_token()`, finalizes via `finalize()`
   - Added `TranscriptPane.add_assistant_streaming()` returning the cell reference

3. **status_footer.py** -- Replaced static placeholder with reactive attributes:
   - `model_name`, `mode`, `token_count`, `session_id` as `reactive` class attributes
   - `watch_*` methods trigger `_refresh_display()` which updates `#status-left` label
   - `on_tokens_updated` handler sums `input_tokens + output_tokens` from usage dict

4. **test_tui_streaming.py** -- 5 headless tests covering all streaming behaviors:
   - `test_thinking_indicator_appears` -- LoadingIndicator visible in streaming mode
   - `test_token_chunk_routes_to_cell` -- append_token feeds into Markdown via MarkdownStream
   - `test_stream_done_finalizes` -- finalize() sets _is_streaming=False, _stream=None
   - `test_status_footer_token_update` -- TokensUpdated message updates reactive + display
   - `test_status_footer_session_id` -- session_id reactive updates left label

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion used non-existent Markdown._markdown_content**
- **Found during:** Task 1 GREEN phase
- **Issue:** Test checked `md._markdown_content` which doesn't exist; correct attribute is `md._markdown`
- **Fix:** Changed assertion to use `md._markdown` after `finalize()` to ensure stream content is flushed
- **Files modified:** tests/test_tui_streaming.py

**2. [Rule 1 - Bug] Test assertion used non-existent Static.renderable**
- **Found during:** Task 1 GREEN phase
- **Issue:** `Static` widget has no `renderable` attribute; content is in `_Static__content` (name-mangled)
- **Fix:** Changed assertions to use `str(left_label._Static__content)`
- **Files modified:** tests/test_tui_streaming.py

**3. [Rule 1 - Bug] app.post_message() doesn't route to child widget handlers**
- **Found during:** Task 1 GREEN phase
- **Issue:** Textual messages bubble UP, not DOWN -- `app.post_message(TokensUpdated(...))` never reaches StatusFooter's `on_tokens_updated`
- **Fix:** Test posts directly to footer widget: `footer.post_message(TokensUpdated(...))`
- **Files modified:** tests/test_tui_streaming.py

## Verification

```
tests/test_tui_streaming.py: 5 passed (0.37s)
Full suite: 599 passed (5.15s)
```

## Decisions Made

1. **MarkdownStream.write() is correct API** -- Resolved STATE.md blocker/concern. The method is `write()`, not `append()`. Verified in Textual 8.1.1 source and confirmed by passing tests.

2. **StatusFooter uses reactive + message handler hybrid** -- `reactive` attributes auto-repaint on change; `on_tokens_updated` handler sets the reactive from the message bus. This is consistent with the existing message bus architecture.

3. **Direct post_message to footer in tests** -- Since Textual routes messages upward (bubbling), tests post `TokensUpdated` directly to the footer widget rather than to the app.
