# Stack Research

**Domain:** Textual TUI UX polish — v2.1 milestone (Conductor)
**Researched:** 2026-03-11
**Confidence:** HIGH

---

## Existing Stack (Validated in v2.0 — Do Not Re-research)

| Technology | Version | Role |
|------------|---------|------|
| `textual` | `8.1.1` | TUI framework — App, Widget, CSS, workers |
| `textual-autocomplete` | (installed) | Slash command popup in CommandInput |
| `claude-agent-sdk` | `>=0.1.48` | SDK streaming, ClaudeSDKClient |
| `pydantic v2` | `>=2.10` | Data models |
| `asyncio` | stdlib | Event loop, workers |

Current TUI: `ConductorApp(App)` with `CSS_PATH`, two-column layout, `@work` workers, `TranscriptPane`, `CommandInput`, `StatusFooter`, `AgentMonitorPane`, shimmer animations via `set_interval`.

---

## New Stack for v2.1 — Zero New Dependencies

All five v2.1 features are addressed by APIs already present in Textual 8.1.1. No new packages are needed.

### Feature 1: Alt-Screen Mode (Full Terminal Takeover)

**Status:** Already the default. No code change needed.

Textual's `LinuxDriver` emits `\x1b[?1049h` (alt-screen on) at startup and `\x1b[?1049l` (alt-screen off) at exit. Running `App.run()` without `inline=True` uses the `LinuxDriver` and therefore already operates in full alt-screen mode.

The v2.0 ConductorApp is launched via:
```python
app = ConductorApp(...)
app.run()
```

This is already correct. If the app is currently appearing inline (under the prompt), the launch call site has `inline=True` set — remove it.

**What NOT to do:** Do not write custom escape sequences. Do not wrap in a subprocess. Textual owns the terminal lifecycle.

---

### Feature 2: Auto-Focus Input on TUI Start

**API:** `App.AUTO_FOCUS` class variable (CSS selector string)

```python
class ConductorApp(App):
    AUTO_FOCUS = "CommandInput Input"   # focuses the Input inside CommandInput on mount
```

`App.AUTO_FOCUS` defaults to `"*"` (focuses the first focusable widget). Setting it to a specific CSS selector targets the exact widget. Screen activation calls `_update_auto_focus()` automatically — no `on_mount` focus call needed.

Alternatively, in `on_mount` (already present in ConductorApp):
```python
async def on_mount(self) -> None:
    ...
    self.query_one("CommandInput Input", Input).focus()
```

The `AUTO_FOCUS` class variable is cleaner and handles focus restoration after modal screens. The existing `on_stream_done` already calls `.focus()` to restore after streaming — the `AUTO_FOCUS` approach covers initial mount.

**What NOT to do:** Do not call `focus()` in `compose()` — widgets are not yet mounted. Do not `set_timer` a delayed focus call.

---

### Feature 3: Borderless / Minimal Chrome Design

**API:** Textual CSS — `border: none;` and `padding: 0;`

Valid Textual border values include `none`, `hidden`, `blank`. Setting `border: none` removes the border box entirely, collapsing the widget to its content edge.

Current `CommandInput` CSS already does `border: none` on the inner `Input`. Extend this pattern to container widgets:

```css
/* conductor.tcss additions for borderless design */
Screen {
    background: $surface;
}

#app-body {
    /* Remove default container borders */
    border: none;
}

TranscriptPane {
    border: none;
    padding: 0;
}

AgentMonitorPane {
    border: none;
    padding: 0 1;
}

CommandInput {
    height: 3;
    padding: 0 1;
    background: $panel;
    border-top: solid $primary 30%;  /* keep the single separator line */
    border-right: none;
    border-bottom: none;
    border-left: none;
}

StatusFooter {
    border: none;
    padding: 0 1;
}
```

Textual CSS color variables (`$surface`, `$panel`, `$primary`, `$accent`) auto-adapt to the active theme. Use them rather than hard-coded hex values.

For cell-level separators, prefer `margin-bottom: 1` on `UserCell` / `AssistantCell` (already in DEFAULT_CSS) over border lines — this matches the Codex CLI aesthetic of content-first with whitespace separation.

**What NOT to do:** Do not use `border: hidden` when you mean `border: none` — `hidden` renders a transparent border that still consumes space. Use `none` to collapse to zero width.

---

### Feature 4: Smooth Animations and Transitions

**API:** `Widget.animate()` and `App.animate()` (both same signature)

```python
Widget.animate(
    attribute: str,           # CSS property name, e.g. "opacity", "offset"
    value: float,             # target value
    duration: float,          # seconds
    easing: str,              # easing function name (see below)
    on_complete: Callable,    # optional callback when done
)
```

**Animatable CSS properties:**
- `opacity` — fade in/out (0.0 to 1.0)
- `offset` — positional slide (x/y offset)
- Any numeric reactive attribute

**Available easing functions** (verified from `textual._easing.EASING`):
- `linear`, `in_out_cubic` (default), `out_cubic`, `in_cubic`
- `in_out_sine`, `out_sine`, `in_sine`
- `in_out_quad`, `out_quad`, `in_quad`
- `in_out_expo`, `out_expo`, `in_expo`
- `in_out_back`, `out_back` (slight overshoot — good for "pop in")
- `in_out_bounce`, `out_bounce`
- `in_out_elastic`, `out_elastic`

**Pattern: Fade in new transcript cells**

```python
class AssistantCell(Widget):
    async def on_mount(self) -> None:
        self.styles.opacity = 0.0
        self.animate("opacity", 1.0, duration=0.25, easing="out_cubic")
```

**Pattern: Slide in from below**

```python
async def on_mount(self) -> None:
    self.styles.offset = (0, 2)   # start 2 lines below
    self.animate("offset", (0, 0), duration=0.2, easing="out_cubic")
```

**Existing shimmer pattern** (keep as-is — already working):
- `set_interval(1/15, _tick)` + sine wave phase → `styles.background = Color(...)`
- No changes needed; this pattern correctly handles the streaming shimmer

**What NOT to do:** Do not use `asyncio.sleep()` loops for animation timing — Textual's `animate()` runs on the compositor thread and integrates with the screen refresh cycle. Do not create `set_interval` timers for one-shot transitions — use `animate()` for those.

---

### Feature 5: Ctrl-G External Editor Integration

**API:** `App.suspend()` (sync context manager) + `@work(thread=True)`

The pattern: suspend Textual → launch editor as a subprocess → read the temp file → resume Textual → populate input.

`App.suspend()` is a synchronous context manager (`@contextmanager`, not `@asynccontextmanager`). It must be called from a thread worker, not from an async coroutine. Use `@work(thread=True)` on the handler.

```python
# In CommandInput or ConductorApp:
from textual.binding import Binding

BINDINGS = [
    Binding("ctrl+g", "open_editor", "Open in editor", show=False),
]

@work(thread=True, exit_on_error=False)
def action_open_editor(self) -> None:
    """Launch external editor for multiline input composition."""
    import os
    import subprocess
    import tempfile
    from textual.app import SuspendNotSupported

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"
    initial_text = ""

    # Read current input value (safe to read from thread — it's a string)
    try:
        from textual.widgets import Input
        current = self.app.query_one("CommandInput Input", Input).value
        initial_text = current
    except Exception:
        pass

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix="conductor_",
        delete=False,
    ) as f:
        f.write(initial_text)
        tmp_path = f.name

    try:
        try:
            with self.app.suspend():
                subprocess.run([editor, tmp_path], check=False)
        except SuspendNotSupported:
            # Fallback: run without suspension (editor will fight the TUI)
            subprocess.run([editor, tmp_path], check=False)

        with open(tmp_path) as f:
            content = f.read().strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if content:
        # Post message back to the app — safe cross-thread communication
        from conductor.tui.messages import UserSubmitted
        self.app.call_from_thread(
            self.app.post_message, UserSubmitted(content)
        )
```

**Key constraints:**
- `App.suspend()` is **synchronous** — must be called from `@work(thread=True)`, not from `async def action_open_editor`.
- `SuspendNotSupported` is raised in non-Unix environments (e.g., headless CI, Textual Web). Catch it.
- Use `self.app.call_from_thread()` to post messages back from the thread — do not call widget methods directly from a thread worker.
- Honor `$VISUAL` before `$EDITOR` before hardcoded fallback (POSIX convention).

**Where to bind:** `CommandInput` widget is the right owner (it handles input submission). Add `BINDINGS` and `action_open_editor` to `CommandInput`.

---

## Summary: What Changes Per Feature

| Feature | Change Type | Where | API Used |
|---------|------------|-------|----------|
| Alt-screen mode | Verify launch call has no `inline=True` | CLI entrypoint | `App.run()` default |
| Auto-focus input | Add `AUTO_FOCUS = "CommandInput Input"` | `ConductorApp` | `App.AUTO_FOCUS` |
| Borderless design | CSS-only changes | `conductor.tcss` + widget `DEFAULT_CSS` | `border: none`, `padding: 0` |
| Smooth animations | Add `animate()` to cell `on_mount` | `TranscriptPane` widgets | `Widget.animate()` |
| Ctrl-G editor | Add binding + thread worker | `CommandInput` | `Binding`, `@work(thread=True)`, `App.suspend()` |

---

## Installation

No new dependencies. All APIs are in `textual==8.1.1` (installed).

```bash
# Verify — no uv add needed
uv run python -c "import textual; print(textual.__version__)"
# Expected: 8.1.1
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `App.AUTO_FOCUS = "CommandInput Input"` | Call `widget.focus()` in `on_mount` | Use `on_mount` focus only for conditional focus logic (e.g., skip focus during session replay) — the `AUTO_FOCUS` class var handles the default case cleanly |
| `App.suspend()` + `@work(thread=True)` | `asyncio.create_subprocess_exec` + `asyncio.wait` | Use async subprocess only if the editor can run without terminal takeover (e.g., a non-interactive formatter). Interactive editors (vim, nano) require full terminal access via `suspend()`. |
| `Widget.animate("opacity", ...)` | `set_interval` + manual opacity steps | `set_interval` is correct for looping animations (shimmer). `animate()` is correct for one-shot transitions with easing. Do not mix them. |
| `border: none` in CSS | `border: hidden` | `hidden` renders a zero-width border that still consumes layout space. `none` removes it entirely. Use `none`. |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Any animation library (e.g., `textual-animations`, custom CSS transitions) | Textual 8.x has a built-in `animate()` with 30 easing functions; adding another animation layer creates conflicts and increases maintenance surface | `Widget.animate()` + `set_interval` (already in use) |
| Custom terminal escape sequences for alt-screen (`\x1b[?1049h`) | Textual already manages the alt-screen lifecycle via `LinuxDriver`. Manual escape codes would fight Textual's driver and corrupt state on exit | `App.run()` (no `inline=True`) |
| `click.edit()` or `subprocess.run` without `App.suspend()` | Launching an editor without suspending Textual leaves the Textual event loop reading keyboard input concurrently with vim — corrupts both processes | `App.suspend()` as context manager around `subprocess.run` |
| `asyncio.create_subprocess_exec` for interactive editor | Async subprocess does not hand terminal control to the child process — interactive editors (vim) need a real TTY | `subprocess.run` inside `@work(thread=True)` + `App.suspend()` |
| New TUI library (blessed, urwid, etc.) | Already committed to Textual; mixing TUI frameworks is not viable | Textual (existing) |
| `tempfile.mkstemp` without `delete=False` on `NamedTemporaryFile` | On Linux, the file must remain on disk while vim opens it — `delete=False` keeps it until explicit `os.unlink()` | `NamedTemporaryFile(delete=False)` + manual cleanup |

---

## Stack Patterns by Feature Variant

**If the terminal does not support suspend (CI, tmux edge cases):**
- Catch `SuspendNotSupported` and fall back to running the editor without suspension
- Log a warning — the TUI may display artifacts but the edit will still complete
- Do not disable Ctrl-G binding based on environment detection at startup

**If user has no `$VISUAL`/`$EDITOR` set:**
- Fall back to `vim` — universally available on Linux/macOS
- Do not present a picker UI — that adds significant scope for marginal benefit

**If animation causes visual noise (fast terminal, low frame rate):**
- `animate()` has a `level` parameter: `"full"`, `"basic"`, `"none"`
- Default `"full"` runs on all terminals. Set `level="basic"` to skip on slow terminals
- The shimmer timer (`set_interval`) is independent of `animate()` — they do not conflict

---

## Version Compatibility

| Package | Version | Compatible With | Notes |
|---------|---------|-----------------|-------|
| `textual` | `8.1.1` | Python 3.13, all features above | `App.suspend()`, `Widget.animate()`, `App.AUTO_FOCUS`, `@work(thread=True)` all verified in installed version |
| `textual` | `8.1.1` | `call_from_thread` | Confirmed available in `App` for cross-thread message posting |

---

## Sources

- `textual==8.1.1` installed at `.venv` — all APIs verified by `inspect` on the live package
- `App.run()` signature — `inline: bool = False` default confirmed; `LinuxDriver` emits `\x1b[?1049h` at `start_application_mode()`
- `App.AUTO_FOCUS` — class variable docstring confirms CSS selector semantics and auto-invocation on screen activation
- `App.suspend()` — full source read: synchronous `@contextmanager`, raises `SuspendNotSupported`, Textual docs example uses `os.system("emacs -nw")`
- `Widget.animate()` — signature confirmed: `attribute`, `value`, `duration`, `easing`, `on_complete`; `opacity` and `offset` confirmed as animatable CSS properties
- `textual._easing.EASING` — complete easing key list verified: 33 named easing functions
- `VALID_BORDER` from `textual.css.constants` — `none`, `hidden`, `blank` all valid; `none` collapses to zero width
- `@work(thread=True)` — `Worker._thread_worker` flag confirmed in `Worker` source; runs via `_run_threaded()`
- `Binding("ctrl+g", ...)` — instantiated successfully; key string `"ctrl+g"` accepted

---
*Stack research for: Conductor v2.1 — UX Polish (alt-screen, borderless, animations, external editor)*
*Researched: 2026-03-11*
