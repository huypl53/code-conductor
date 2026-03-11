---
phase: 41-smooth-cell-animations
plan: 01
subsystem: tui/widgets
tags: [animation, opacity, fade-in, env-var]
dependency_graph:
  requires: [Phase 40 borderless design]
  provides: [cell fade-in animation, animation disable flag]
  affects: [transcript.py]
tech_stack:
  added: []
  patterns: [styles.animate for one-shot opacity transitions, module-level env var guard]
key_files:
  created:
    - packages/conductor-core/tests/test_tui_animations.py
  modified:
    - packages/conductor-core/src/conductor/tui/widgets/transcript.py
decisions:
  - "styles.animate('opacity', ...) instead of Widget.animate('opacity', ...) -- Widget.animate raises 'property has no setter' for CSS properties; styles.animate is the correct API for CSS property animation"
  - "_ANIMATIONS read once at import time via os.environ.get -- no runtime overhead per cell mount"
metrics:
  duration: 8min
  completed: 2026-03-11
---

# Phase 41 Plan 01: Smooth Cell Animations Summary

Cell fade-in via `styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")` on UserCell and AssistantCell mount; `_ANIMATIONS` module-level bool disables when `CONDUCTOR_NO_ANIMATIONS` is set.

## What Was Built

Added opacity fade-in animation to both `UserCell` and `AssistantCell` in `transcript.py`. When a new cell mounts, it starts at opacity 0.0 and smoothly transitions to 1.0 over 0.25 seconds using Textual's `styles.animate()` API with `out_cubic` easing. The animation is guarded by a `_ANIMATIONS` module-level boolean constant that reads `CONDUCTOR_NO_ANIMATIONS` from the environment at import time. When the env var is set to "1", "true", or "yes", all fade-in calls are skipped and cells appear instantly.

### Implementation Details

1. **`_ANIMATIONS` constant** -- Module-level bool, computed once at import. Placed after shimmer constants, before class definitions.
2. **`UserCell.on_mount()`** -- Sets `styles.opacity = 0.0` then calls `styles.animate("opacity", value=1.0, ...)` inside `if _ANIMATIONS:` guard.
3. **`AssistantCell.on_mount()`** -- Identical fade-in logic. Shimmer (tint via `set_interval`) is completely independent and untouched.

### Tests (5 total, all passing)

| Test | Verifies |
|------|----------|
| `test_user_cell_fade_in` | UserCell opacity reaches 1.0 after 0.4s pause |
| `test_assistant_cell_fade_in` | AssistantCell (static mode) opacity reaches 1.0 after 0.4s pause |
| `test_shimmer_unchanged_after_fade_in` | Shimmer tint is active on streaming cell -- opacity animation does not interfere |
| `test_no_animations_env_var` | Patching `_ANIMATIONS=False` means opacity stays 1.0 immediately (no animate call) |
| `test_animations_flag_module_level` | `_ANIMATIONS` exists as a bool on the module |

## Decisions Made

1. **`styles.animate()` over `Widget.animate()`** -- The plan specified `self.animate("opacity", ...)` based on research docs, but at runtime Textual raised `AttributeError: property 'opacity' has no setter`. The `styles.animate("opacity", value=1.0, ...)` API (documented in ARCHITECTURE.md research) works correctly because it animates the CSS property directly through the Styles object rather than trying to set a Python property on the widget.

2. **`import os` at module top** -- Added alongside existing imports rather than inline near the constant, following Python style conventions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Widget.animate raises AttributeError for CSS properties**
- **Found during:** Task 2 (GREEN)
- **Issue:** `self.animate("opacity", 1.0, ...)` raises `AttributeError: property 'opacity' of 'AssistantCell' object has no setter` because Widget.animate tries to use setattr on the widget itself, but opacity is a CSS property accessible only through styles.
- **Fix:** Changed to `self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")` which correctly animates the CSS property.
- **Files modified:** `packages/conductor-core/src/conductor/tui/widgets/transcript.py`
- **Commit:** a57f386

## Commits

| Hash | Message |
|------|---------|
| d2d4d49 | test(41-01): add failing tests for cell fade-in animations |
| a57f386 | feat(41-01): implement cell fade-in animation with env var guard |

## Verification

- All 5 animation tests pass
- All 7 session polish tests pass (no regressions)
- Full test suite green
- VIS-03 satisfied: cells fade from opacity 0 to 1 over 0.25s
- VIS-04 satisfied: CONDUCTOR_NO_ANIMATIONS disables fade-in
