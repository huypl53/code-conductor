# Phase 41: Smooth Cell Animations - Research

**Researched:** 2026-03-11
**Domain:** Textual TUI widget animation — opacity fade-in on mount, env-var escape hatch
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VIS-03 | New UserCell or AssistantCell fades from invisible to visible over ~0.25s on mount | `Widget.animate("opacity", 1.0, duration=0.25, easing="out_cubic")` in `on_mount`; set `self.styles.opacity = 0.0` before animate |
| VIS-04 | `CONDUCTOR_NO_ANIMATIONS=1` disables all fade-in; env var read at startup, respected throughout session | Module-level `_ANIMATIONS` bool from `os.environ.get("CONDUCTOR_NO_ANIMATIONS")` in `transcript.py`; guard every `animate()` call |
</phase_requirements>

---

## Summary

Phase 41 adds a single visual behaviour: new `UserCell` and `AssistantCell` instances fade in over ~0.25s using Textual's built-in `Widget.animate("opacity", ...)` API. The shimmer animation (already implemented in Phase 38 via `set_interval` + sine wave) is completely unrelated and must not be touched.

The key insight from Phase 38's bug history is that `animate("styles.tint", ...)` fails at runtime — but `animate("opacity", ...)` works correctly because `opacity` is a top-level animatable CSS property that Textual resolves without dot-path lookup. This phase uses `opacity` only, so the Phase 38 pitfall does not apply.

The env-var escape hatch (`CONDUCTOR_NO_ANIMATIONS=1`) is a module-level constant read once at import time. All `animate()` calls for fade-in are guarded by this flag. CI and SSH users set the var and get instant cell appearance with no runtime overhead.

**Primary recommendation:** Add `on_mount` fade-in to `UserCell` and `AssistantCell` in `transcript.py`; add module-level `_ANIMATIONS` guard; no changes to any other file.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `textual` | `8.1.1` | `Widget.animate()` for opacity transitions | Already installed; `opacity` is a first-class animatable property |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `os` | stdlib | `os.environ.get("CONDUCTOR_NO_ANIMATIONS")` | Env-var read at module import time |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Widget.animate("opacity", ...)` | `set_interval` + manual opacity steps | `set_interval` is correct for looping animations (shimmer). `animate()` is correct for one-shot transitions. Do not use `set_interval` here. |
| Module-level `_ANIMATIONS` constant | Per-call `os.environ.get(...)` | Module-level read is cheaper and ensures consistency throughout a session even if the env var is modified at runtime. |

**Installation:**
```bash
# No new dependencies — textual 8.1.1 already installed
uv run python -c "import textual; print(textual.__version__)"
```

---

## Architecture Patterns

### Files Changed

Only one file needs changes: `packages/conductor-core/src/conductor/tui/widgets/transcript.py`

```
conductor/tui/widgets/
└── transcript.py    # ADD: module-level _ANIMATIONS flag + on_mount fade-in in UserCell and AssistantCell
```

No changes needed to: `app.py`, `conductor.tcss`, `command_input.py`, or any other file.

### Pattern 1: Module-Level Animations Flag

**What:** Read `CONDUCTOR_NO_ANIMATIONS` once at module import time; store as a module-level bool.
**When to use:** Any time a cell is about to call `animate()`.

```python
# Source: FEATURES.md implementation notes + STACK.md env-var check pattern
import os

_ANIMATIONS = os.environ.get("CONDUCTOR_NO_ANIMATIONS", "") not in ("1", "true", "yes")
```

Place this immediately after the existing `_SHIMMER_OFF` / `_SHIMMER_INTERVAL` module constants (lines 12-15 of `transcript.py`). The flag is read once at startup; flipping the env var mid-session has no effect (by design, per VIS-04).

### Pattern 2: Fade-In via `on_mount`

**What:** Each cell sets `styles.opacity = 0.0` synchronously at construction, then fires a one-shot `animate("opacity", 1.0, ...)` in `on_mount`.
**When to use:** Both `UserCell` and `AssistantCell`.

```python
# Source: STACK.md Feature 4 — verified against textual 8.1.1 installed package
class UserCell(Widget):
    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.animate("opacity", 1.0, duration=0.25, easing="out_cubic")
```

```python
class AssistantCell(Widget):
    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.animate("opacity", 1.0, duration=0.25, easing="out_cubic")
```

**Critical:** Set `styles.opacity = 0.0` before calling `animate()` — without this the widget is visible for one frame before the animation begins. Both lines must be inside the `if _ANIMATIONS:` guard.

### Pattern 3: No-Animations Fast Path

When `CONDUCTOR_NO_ANIMATIONS=1`, the `if _ANIMATIONS:` block is skipped entirely. The cell mounts at full opacity instantly. No timer, no callback, no overhead.

### Anti-Patterns to Avoid

- **`animate("styles.tint", ...)`:** Fails at runtime with `AttributeError` (Phase 38 confirmed bug). Only `opacity` and `offset` are top-level animatable properties.
- **`set_interval` for fade-in:** Only appropriate for looping animations (the shimmer). Use `animate()` for one-shot transitions.
- **Opacity set in `__init__` instead of `on_mount`:** The widget is not yet mounted in `__init__`; setting `styles.opacity` there has no effect and may raise an error.
- **Touching the welcome cell in `TranscriptPane.on_mount`:** The welcome cell is mounted synchronously via `self.mount(AssistantCell(...))` inside `on_mount`. This will also fade in (correct behaviour) — no special casing needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| One-shot opacity transition with easing | Custom `set_interval` timer counting frames | `Widget.animate("opacity", 1.0, duration=0.25)` | Textual's animator runs on the compositor thread, integrates with screen refresh, and has 33 easing functions built in |
| Env-var respecting animation toggle | Settings file / reactive var / config object | Module-level `_ANIMATIONS = os.environ.get(...) not in (...)` | Env var read once at startup; zero overhead; standard CI/SSH pattern |

**Key insight:** Textual's `animate()` is purpose-built for one-shot CSS transitions. Using anything else adds complexity for no benefit.

---

## Common Pitfalls

### Pitfall 1: `animate("styles.tint")` vs `animate("opacity")`

**What goes wrong:** `Widget.animate("styles.tint", ...)` raises `AttributeError` at runtime. Textual's animator calls `getattr(self, attribute)` and cannot resolve dot-path strings. Confirmed in Phase 38.

**Why it happens:** Textual animator resolves only top-level attribute names, not dot-path like `"styles.tint"`.

**How to avoid:** This phase uses `animate("opacity", ...)` only. `opacity` is a first-class CSS property directly accessible as an attribute. Do not write `animate("styles.opacity")`.

**Warning signs:** Animation `on_complete` fires but widget opacity never visibly changes; `AttributeError` in Textual's internal animation callback.

### Pitfall 2: Widget Not Visible for One Frame Before Fade

**What goes wrong:** If `self.animate("opacity", 1.0, ...)` is called without first setting `self.styles.opacity = 0.0`, the widget renders at full opacity for one compositor frame before the animation starts. The result is a brief flash of the widget at full opacity.

**Why it happens:** `animate()` begins from the current attribute value. Without an explicit starting value of `0.0`, Textual starts the animation from the widget's current opacity (default: `1.0`), which means no visual change for one frame.

**How to avoid:** Always set `self.styles.opacity = 0.0` immediately before calling `animate("opacity", 1.0, ...)`. Both must be inside the `if _ANIMATIONS:` guard.

### Pitfall 3: Welcome Cell Gets Double-Treated

**What goes wrong:** The welcome cell in `TranscriptPane.on_mount` is `AssistantCell("Welcome to Conductor...")`. Since `AssistantCell.on_mount` will now fire the fade-in, the welcome cell also fades in. This is correct and expected behaviour — no special casing needed.

**Why it happens:** Not a pitfall — it is the desired behaviour. Document it so the planner does not add a skip condition.

**How to avoid:** Do not add `if self._text is not None: return` or similar guards to prevent the welcome cell from fading. The fade-in applies to all cells.

### Pitfall 4: Session Replay Cells Fade In Individually

**What goes wrong:** During session replay, each replayed `UserCell` and `AssistantCell` mounts sequentially. Each one triggers its own fade-in. On long sessions, the replay creates a wave of fading cells. This may look unpolished.

**Why it happens:** `add_user_message()` and `add_assistant_message()` are the replay mount paths — they call `self.mount(cell)` which triggers `on_mount` on each cell.

**How to avoid:** This is an acceptable trade-off for Phase 41's scope. If it looks bad, the option is to check `TranscriptPane._resume_mode` inside `on_mount` and skip animation when `True`. But this is deferred — the phase requirements do not mention it and the current shimmer already fires on replay cells (also acceptable).

---

## Code Examples

Verified patterns from official sources:

### Complete `on_mount` Fade-In for UserCell

```python
# Source: STACK.md Feature 4 pattern, verified against textual 8.1.1
class UserCell(Widget):
    DEFAULT_CSS = """
    UserCell {
        background: $primary 10%;
        border-left: solid $primary 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    UserCell .cell-label {
        color: $primary;
        text-style: bold;
    }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static("You", classes="cell-label")
        yield Static(self._text)

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.animate("opacity", 1.0, duration=0.25, easing="out_cubic")
```

### Complete `on_mount` Fade-In for AssistantCell

```python
# Source: STACK.md Feature 4 pattern, verified against textual 8.1.1
class AssistantCell(Widget):
    # ... existing __init__, compose, start_streaming, etc. unchanged ...

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.animate("opacity", 1.0, duration=0.25, easing="out_cubic")
```

### Module-Level Animations Guard

```python
# Source: FEATURES.md implementation notes
import os

# Shimmer constants (existing)
_SHIMMER_ON = Color(150, 150, 255, 0.12)
_SHIMMER_OFF = Color(0, 0, 0, 0.0)
_SHIMMER_INTERVAL = 1.0 / 15
_SHIMMER_PERIOD = 1.4

# NEW: Animations flag — read once at startup
_ANIMATIONS = os.environ.get("CONDUCTOR_NO_ANIMATIONS", "") not in ("1", "true", "yes")
```

### Test Pattern for Fade-In Verification

```python
# Source: existing test_tui_session_polish.py pattern (run_test() inline per #4998)
async def test_user_cell_fade_in_enabled():
    """UserCell mounts with opacity 0 and animates to 1 when CONDUCTOR_NO_ANIMATIONS unset."""
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import UserCell

    class FadeApp(App):
        def compose(self) -> ComposeResult:
            yield UserCell("test message")

    app = FadeApp()
    async with app.run_test() as pilot:
        cell = app.query_one(UserCell)
        # Immediately after mount, animation in progress — opacity may be between 0 and 1
        # After animation completes (>0.25s), opacity should be 1.0
        await pilot.pause(0.4)
        assert cell.styles.opacity == 1.0


async def test_user_cell_no_animation_when_env_var_set(monkeypatch):
    """UserCell mounts at full opacity when CONDUCTOR_NO_ANIMATIONS=1."""
    monkeypatch.setenv("CONDUCTOR_NO_ANIMATIONS", "1")
    # NOTE: module-level _ANIMATIONS is already set — must reload module or patch _ANIMATIONS directly
    import conductor.tui.widgets.transcript as t_mod
    original = t_mod._ANIMATIONS
    t_mod._ANIMATIONS = False
    try:
        from textual.app import App, ComposeResult
        from conductor.tui.widgets.transcript import UserCell

        class NoAnimApp(App):
            def compose(self) -> ComposeResult:
                yield UserCell("test message")

        app = NoAnimApp()
        async with app.run_test() as pilot:
            cell = app.query_one(UserCell)
            await pilot.pause()
            assert cell.styles.opacity == 1.0
    finally:
        t_mod._ANIMATIONS = original
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cells appear instantly (snap-in) | Cells fade in over 0.25s | Phase 41 | Softer, more polished UX |
| No animation escape hatch | `CONDUCTOR_NO_ANIMATIONS=1` disables fade-in | Phase 41 | CI/SSH users get clean instant rendering |

**Shimmer unchanged:**
- `set_interval` + sine wave on `styles.tint` — Phase 38 implementation is correct, no modifications.
- `animate("styles.tint", ...)` was confirmed broken in Phase 38 and must never be used.

---

## Open Questions

1. **Should replay cells skip fade-in?**
   - What we know: Each replayed cell triggers `on_mount` → fade-in. On long sessions this is a wave of fading cells.
   - What's unclear: Whether this looks acceptable or distracting in practice.
   - Recommendation: Implement without replay guard first. If it looks bad, add `if self.parent and hasattr(self.parent, '_resume_mode') and self.parent._resume_mode: return` inside `on_mount`. Defer this decision to the implementation phase.

2. **Duration tuning: 0.25s vs 0.15s**
   - What we know: Phase requirements say "~0.25s". STACK.md and FEATURES.md examples use 0.15s. The milestone research notes mention 0.15s as well.
   - What's unclear: Which feels better in practice.
   - Recommendation: Implement at 0.25s per the phase requirements (VIS-03). Duration is a one-line change if tuning is needed.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing, all TUI tests use it) |
| Config file | `packages/conductor-core/pyproject.toml` (asyncio_mode = "auto" inferred from existing tests) |
| Quick run command | `cd /home/huypham/code/digest/claude-auto && uv run pytest packages/conductor-core/tests/test_tui_session_polish.py -x -q` |
| Full suite command | `cd /home/huypham/code/digest/claude-auto && uv run pytest packages/conductor-core/tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VIS-03 | UserCell fades from opacity 0 to 1 over ~0.25s on mount | unit | `uv run pytest packages/conductor-core/tests/test_tui_animations.py::test_user_cell_fade_in -x` | Wave 0 |
| VIS-03 | AssistantCell fades from opacity 0 to 1 over ~0.25s on mount | unit | `uv run pytest packages/conductor-core/tests/test_tui_animations.py::test_assistant_cell_fade_in -x` | Wave 0 |
| VIS-03 | Fade-in uses opacity animation — shimmer (tint) unchanged | unit | `uv run pytest packages/conductor-core/tests/test_tui_animations.py::test_shimmer_unchanged_after_fade_in -x` | Wave 0 |
| VIS-04 | `CONDUCTOR_NO_ANIMATIONS=1` → cells appear at full opacity instantly | unit | `uv run pytest packages/conductor-core/tests/test_tui_animations.py::test_no_animations_env_var -x` | Wave 0 |
| VIS-04 | Env var read at startup, respected throughout session | unit | `uv run pytest packages/conductor-core/tests/test_tui_animations.py::test_animations_flag_module_level -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest packages/conductor-core/tests/test_tui_animations.py -x -q`
- **Per wave merge:** `uv run pytest packages/conductor-core/tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `packages/conductor-core/tests/test_tui_animations.py` — covers VIS-03 and VIS-04 (does not exist yet)

*(All other infrastructure is in place: pytest, pytest-asyncio, conftest patterns from `test_tui_session_polish.py`)*

---

## Sources

### Primary (HIGH confidence)

- `.planning/research/STACK.md` — Feature 4: `Widget.animate("opacity", ...)` API, easing functions, opacity as animatable property, shimmer `set_interval` pattern
- `.planning/research/PITFALLS.md` — Pitfall 1: `animate("styles.tint")` AttributeError (Phase 38 confirmed); correct shimmer stop order
- `.planning/research/FEATURES.md` — Smooth animations section: `_ANIMATIONS` env-var guard pattern, mount-point identification (`add_user_message`, `add_assistant_streaming`)
- `packages/conductor-core/src/conductor/tui/widgets/transcript.py` — direct code review: existing `UserCell`, `AssistantCell`, `TranscriptPane` implementations; shimmer timer lifecycle

### Secondary (MEDIUM confidence)

- `packages/conductor-core/tests/test_tui_session_polish.py` — test infrastructure patterns: inline `run_test()`, `pilot.pause()`, module patching approach for `_ANIMATIONS` flag
- `packages/conductor-core/src/conductor/tui/app.py` — confirms `AUTO_FOCUS = "CommandInput Input"` already set; session replay flow; no animation-related logic needed in `app.py`

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `Widget.animate("opacity", ...)` directly verified in STACK.md against installed textual 8.1.1 package
- Architecture: HIGH — single file change (`transcript.py`), well-understood mount lifecycle, existing shimmer confirms the `on_mount` pattern
- Pitfalls: HIGH — Phase 38 production bug (dot-path animate failure) is documented project history; opacity pitfall is a direct derivation of that finding

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (textual 8.1.1 is pinned; no version churn expected)
