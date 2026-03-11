---
phase: 34-rich-output
plan: 01
subsystem: tui-widgets
tags: [syntax-highlighting, markdown, diff-coloring, textual]
dependency_graph:
  requires: [33-02]
  provides: [rich-markdown-widget, diff-aware-fences]
  affects: [transcript-streaming]
tech_stack:
  added: []
  patterns: [subclass-override-BLOCKS, conditional-theme-selection]
key_files:
  created:
    - packages/conductor-core/src/conductor/tui/widgets/rich_markdown.py
    - packages/conductor-core/tests/test_tui_rich_output.py
  modified:
    - packages/conductor-core/src/conductor/tui/widgets/transcript.py
decisions:
  - "bold green / bold red raw colors for diff spans (not CSS variables) -- matches existing HighlightTheme patterns and passes test assertions"
  - "DiffHighlightTheme applied only for diff/udiff fences, default HighlightTheme for all others"
metrics:
  duration: 94s
  completed: "2026-03-11T14:21:11Z"
  tests_added: 3
  tests_total: 604
---

# Phase 34 Plan 01: Rich Markdown Output Summary

Diff-aware syntax highlighting via DiffHighlightTheme subclass with Token.Generic.Inserted/Deleted mappings, registered through DiffAwareFence in RichMarkdown BLOCKS override, wired into AssistantCell streaming.

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Create RichMarkdown widget and test file (TDD) | e555d0b (RED), 606eb2b (GREEN) | rich_markdown.py, test_tui_rich_output.py |
| 2 | Wire RichMarkdown into AssistantCell streaming | 18ef73b | transcript.py |

## Requirements Verified

| Req ID | Description | Test | Status |
|--------|-------------|------|--------|
| TRNS-03 | Code blocks render with syntax highlighting | test_code_fence_has_spans | PASS |
| TRNS-04 | Markdown renders headings, bold, lists, blockquotes | test_markdown_elements | PASS |
| TRNS-05 | Diff fences render with green/red colored spans | test_diff_fence_colors | PASS |

## Implementation Details

- **DiffHighlightTheme**: Extends Textual's HighlightTheme.STYLES with `Token.Generic.Inserted: "bold green"` and `Token.Generic.Deleted: "bold red"`
- **DiffAwareFence**: Conditionally selects DiffHighlightTheme for diff/udiff fences, default HighlightTheme for all others
- **RichMarkdown**: Overrides Markdown.BLOCKS to register DiffAwareFence for fence and code_block tokens
- **AssistantCell.start_streaming()**: Changed from `Markdown("")` to `RichMarkdown("")` via lazy import

## Deviations from Plan

None -- plan executed exactly as written.

## Test Results

```
604 passed in 5.67s
```

3 new tests added, zero regressions on existing 601 tests.
