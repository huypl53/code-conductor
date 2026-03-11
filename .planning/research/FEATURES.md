# Feature Research

**Domain:** Textual TUI UX Polish — v2.1 features: auto-focus, alt-screen, borderless chrome, smooth animations, external editor integration
**Researched:** 2026-03-11
**Confidence:** HIGH (Textual official docs, direct codebase review, Textual GitHub discussions, Codex CLI source analysis)

---

## Context: This Is a Subsequent Milestone

This research focuses exclusively on **what's needed for v2.1's UX polish pass**. All v2.0 Textual TUI features are already built and passing 641 tests:

**Already built in v2.0 (no changes needed unless noted):**
- `ConductorApp` (Textual `App` subclass, CSS-driven two-column layout)
- `TranscriptPane` with `UserCell` / `AssistantCell`, shimmer animation, session replay
- `CommandInput` with `SlashAutocomplete` (textual-autocomplete)
- `AgentMonitorPane` with state file watcher
- `StatusFooter` reactive bar (model, tokens, session ID)
- Modal overlays for escalation (`EscalationModal`)
- `@work` SDK streaming integration

**v2.1 adds five focused UX improvements on top of this foundation:**
1. Auto-focus input on TUI start
2. Full alt-screen mode with clean entry/exit
3. Borderless/minimal chrome design — content flows naturally
4. Smooth animations and transitions
5. Ctrl-G to open input in external editor (vim) for multiline composition

**Reference UX:** OpenAI Codex CLI — the target is to achieve equivalent terminal-native feel.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features a polished terminal app must have. Missing these makes the TUI feel amateur or broken compared to reference-class tools like Codex CLI or lazygit.

| Feature | Why Expected | Complexity | Textual Mechanism | Existing Dependency |
|---------|--------------|------------|-------------------|---------------------|
| Auto-focus input on startup | Every terminal chat tool (Codex CLI, aider, OpenCode) activates the input immediately — users start typing before looking at the screen. Without auto-focus, first keystroke is lost or user must click/tab to activate input. | LOW | `App.AUTO_FOCUS = "Input"` class variable (CSS selector); targets the `Input` widget inside `CommandInput`. Textual focuses the first widget matching the selector when the app starts. Falls back to explicit `widget.focus()` call in `on_mount()` if the selector approach is insufficient. | `CommandInput` already exists; its inner `Input` widget is the target. `on_stream_done` already calls `cmd.query_one(Input).focus()` — auto-focus is the same pattern applied at startup. |
| Full alt-screen with clean entry/exit | Alt-screen mode means the TUI takes over the entire terminal, and on exit the previous terminal state is restored cleanly (no residual cursor artifacts, no cleared scrollback pollution). Without this, exiting leaves garbage in the shell. | LOW | Textual enters alt-screen (application mode) automatically on `App.run()`. The exit behavior is controlled by `action_quit()` — already implemented in `ConductorApp`. The primary work is verifying clean entry (no startup flash) and clean exit (cursor restored, no artifacts on `Ctrl+Q`). Signal handling for `SIGINT` needs verification. | `action_quit()` already cancels background tasks, disconnects SDK, and calls `self.exit()`. The Textual framework handles terminal state restoration. May need to verify SIGINT behavior. |
| Ctrl-G to open external editor (vim) | Power users composing multi-line prompts (architecture specs, complex task descriptions) need a real editor. This is the standard Unix pattern (used by git commit, readline `edit-and-execute-command`). Without it, multi-line input is painful single-line composition. | MEDIUM | `App.suspend()` context manager (Textual v0.48.0+). Pattern: (1) write `CommandInput` content to tempfile, (2) `with self.suspend(): subprocess.call([editor, tempfile])`, (3) read tempfile back, populate `Input.value`. Respects `$VISUAL` / `$EDITOR` env var with vim fallback. Works on Unix/macOS only — document Windows limitation. | `CommandInput` and its inner `Input` widget provide the current value. `on_mount` and key binding infrastructure already in place via `BINDINGS`. New `action_open_editor()` method on `ConductorApp`. |

### Differentiators (Competitive Advantage)

Features that elevate the Conductor TUI above Codex CLI's UX bar.

| Feature | Value Proposition | Complexity | Textual Mechanism | Existing Dependency |
|---------|-------------------|------------|-------------------|---------------------|
| Borderless/minimal chrome design | Remove visual clutter (panel borders, excess padding) so content flows naturally. Codex CLI has minimal chrome. Heavy borders make the TUI feel like a form rather than a conversation. | LOW | Textual CSS: `border: none;` or `border: blank;` on widgets that currently use `border-top: solid $primary 30%` (CommandInput) and `border-left: thick $primary/accent` (cells). CSS variable overrides in `conductor.tcss`. No Python logic changes — purely CSS. | `conductor.tcss` is the single CSS file to modify. All widget `DEFAULT_CSS` in Python files can be overridden by the external `.tcss` file. |
| Smooth animations and transitions | Subtle motion when cells appear, when the transcript scrolls to a new message, and when the shimmer starts/stops. Makes the TUI feel alive rather than static. Codex CLI has smooth cell entry. | MEDIUM | Textual `widget.animate()` method: animate `opacity` from 0.0 to 1.0 on new cells (`AssistantCell`, `UserCell`) as they mount. Easing: `in_out_cubic` (Textual default — "pleasing organic motion"). Duration: 150-200ms. Shimmer already implemented with `Timer` and `Color` interpolation — preserve and tune. Auto-scroll uses Textual's built-in smooth scroll on `VerticalScroll`. | `TranscriptPane.add_user_message()` and `add_assistant_streaming()` are the mount points. Add `animate()` call immediately after `mount()`. Shimmer Timer already exists in `AssistantCell` — may only need timing tuning. |
| Responsive layout adjustments | Narrow terminal (< 100 cols) hides the agent monitor panel. Wide terminal shows both columns. Makes the TUI usable on any terminal width without horizontal scrollbar. | LOW | Textual CSS `@media` width queries. `AgentMonitorPane` gets `display: none` below a threshold. Alternatively use `App.on_resize()` handler to toggle visibility programmatically. | `#app-body` horizontal layout already in `conductor.tcss`. `AgentMonitorPane` is a discrete widget that can be shown/hidden. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Inline mode (runs beneath prompt) | "I want the TUI to appear under my shell prompt without taking over the screen" | Textual inline mode (`App.run(inline=True)`) explicitly does not enter alt-screen. It conflicts with the command palette (known Textual bug #4385). It has limited widget support and no Windows support. It undermines the whole-screen polish we're building. | Full alt-screen is the right choice for Conductor. Clean entry/exit handles the "I want my terminal back" concern. |
| Animated loading screen / splash | "Show a Conductor logo on startup" | Startup latency is already noticeable (SDK connection). Adding a splash screen delays the user from typing. Feels like bloat in a professional CLI tool. | Auto-focus so the user can start typing immediately. Fast `on_mount` with lazy SDK connection on first message (already implemented). |
| Per-widget animation configuration | "Let users toggle animations on/off per component" | Creates a settings system just for animations. Adds complexity that doesn't serve the core use case. | Single animation toggle: `CONDUCTOR_NO_ANIMATIONS=1` env var check. If set, skip all `animate()` calls. Simple, respects user preferences. |
| Full vim emulation inside Input | "I want vim keybindings in the input bar" | Textual's `Input` widget doesn't support vim modal editing. Implementing it requires replacing the widget or building a state machine for normal/insert/visual modes. High complexity, niche audience. | Ctrl-G opens actual vim for heavy composition. For quick edits, standard readline-style keys (Ctrl-A/E, Ctrl-K/U) already work in Textual `Input`. |
| Mouse-based resize of panels | "Let me drag the split between transcript and agent monitor" | Textual's CSS layout doesn't support runtime drag-resize without major custom widget work. The resize event fires but there's no built-in splitter widget. | Responsive breakpoints via CSS `@media` (show/hide agent monitor at width thresholds). Keyboard shortcut to toggle agent monitor panel. |
| Persistent command history (up-arrow) | "I want up-arrow to recall previous commands like a shell" | Textual's `Input` widget doesn't persist history across sessions by default. Implementing readline-style history requires a custom input widget or external library. Significant scope expansion for v2.1. | Defer to v2.2 or later. The `/resume` command already handles session continuity at the conversation level. |

---

## Feature Dependencies

```
[ConductorApp — existing v2.0 foundation]
    └──enables──> [Auto-focus input] (LOW effort, class var + on_mount)
    └──enables──> [Clean alt-screen exit] (LOW effort, verify SIGINT path)
    └──enables──> [Borderless CSS] (LOW effort, CSS-only changes in conductor.tcss)
    └──enables──> [Ctrl-G external editor] (MEDIUM effort, new action + App.suspend())
    └──enables──> [Smooth cell animations] (MEDIUM effort, animate() calls in add_*_message)

[Auto-focus input]
    └──requires──> [CommandInput widget] (already built — inner Input is the focus target)
    └──enhances──> [Clean alt-screen] (user can type immediately on entry)
    └──conflicts──> [Session replay on resume] — replay locks input; auto-focus must not fire until replay completes
                    (already handled: on_stream_done re-focuses after replay unlocks input)

[Ctrl-G external editor]
    └──requires──> [App.suspend() — Textual v0.48.0+] (verify installed version supports it)
    └──requires──> [CommandInput.Input] (source of pre-populated text, target for edited result)
    └──requires──> [tempfile stdlib] (Python stdlib — no new deps)
    └──requires──> [$VISUAL / $EDITOR env var or vim fallback] (runtime config)
    └──conflicts──> [Windows] — App.suspend() is Unix-only; document limitation
    └──enhances──> [Borderless design] — editor opens outside TUI cleanly, returns to TUI cleanly

[Borderless CSS changes]
    └──requires──> [conductor.tcss modifications]
    └──requires──> [DEFAULT_CSS review in all widget files] (CommandInput, UserCell, AssistantCell)
    └──enhances──> [Smooth animations] — borderless + fade-in creates cohesive "content appears" feel
    └──no conflicts]

[Smooth cell animations]
    └──requires──> [TranscriptPane.add_user_message() / add_assistant_streaming()] (mount points — already exist)
    └──requires──> [Textual animate() API] (built-in — already available)
    └──enhances──> [Borderless design] — animation reinforces minimal aesthetic (content flows in vs snapping in)
    └──no new deps]

[Clean alt-screen entry/exit]
    └──requires──> [action_quit() verification] (already implemented — verify SIGINT path)
    └──no new deps]
```

### Dependency Notes

- **Auto-focus and session replay interact:** `CommandInput.disabled = True` is set during replay. Auto-focus must use `AUTO_FOCUS` class var (fires on app start, before replay lock) AND `widget.focus()` in the replay completion path (already present in `_replay_session()`). The two paths work together without conflict.
- **App.suspend() version requirement:** Textual added `suspend()` in v0.48.0. Verify the pinned Textual version in `pyproject.toml` is >= 0.48.0 before implementing Ctrl-G. If not, update Textual first.
- **Borderless CSS is purely additive:** No Python logic changes. All widget `DEFAULT_CSS` defined in Python can be overridden by `conductor.tcss` without touching widget files. Lower risk.
- **Ctrl-G is Unix-only by design:** `App.suspend()` sends `SIGTSTP` on Unix. Windows support is a non-operation in Textual. Document this clearly; don't try to implement a Windows alternative in v2.1.
- **Smooth animations need env var escape hatch:** Some users run Conductor in CI or over slow SSH where animations are distracting or cause rendering artifacts. Respect `NO_ANIMATIONS=1` or `CONDUCTOR_NO_ANIMATIONS=1` by wrapping all `animate()` calls in a check.

---

## MVP Definition

### Launch With (v2.1 core — all five features)

All five features are small enough that they collectively form the v2.1 milestone. No feature is optional; all five together constitute the "native and polished" standard.

- [ ] **Auto-focus input on startup** — `AUTO_FOCUS = "Input"` on `ConductorApp` plus verify `on_mount` focus path; ensures typing works immediately without Tab or click
- [ ] **Clean alt-screen entry/exit** — verify `SIGINT` handler calls `action_quit()` cleanly; test that exiting leaves no terminal artifacts; test startup does not flash
- [ ] **Borderless/minimal chrome design** — update `conductor.tcss` and widget `DEFAULT_CSS` to remove heavy borders from `CommandInput`, `UserCell`, `AssistantCell`; use `blank` or `none` border styles; reduce padding where appropriate
- [ ] **Smooth cell animations** — `widget.animate("opacity", 1.0, duration=0.15, easing="in_out_cubic")` on `UserCell` and `AssistantCell` mount; tune existing shimmer timing; respect `CONDUCTOR_NO_ANIMATIONS` env var
- [ ] **Ctrl-G external editor** — `BINDINGS` entry for `ctrl+g`; `action_open_editor()` that writes `Input.value` to tempfile, `with self.suspend(): subprocess.call([editor, tempfile])`, reads result back into `Input.value`; respects `$VISUAL`/`$EDITOR`; Unix-only with clear error on Windows

### Add After Core Is Working (v2.1 polish)

Polish items to add if all five features are stable and time permits in v2.1.

- [ ] **Responsive layout breakpoints** — hide `AgentMonitorPane` below ~100-column terminal width via CSS `@media` or `on_resize()` handler
- [ ] **Animation env var toggle** — `CONDUCTOR_NO_ANIMATIONS=1` disables all `animate()` calls for CI/SSH use

### Future Consideration (v2.2+)

- [ ] **Command history (up-arrow)** — readline-style history across sessions; requires custom `Input` subclass or external history lib
- [ ] **`/theme` live switching** — swap Textual CSS variables at runtime; modal theme picker (deferred from v2.0)
- [ ] **Session picker as Textual overlay** — upgrade the plain-text session list to a `ModalScreen` with `ListView`

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Auto-focus input on startup | HIGH | LOW | P1 |
| Clean alt-screen entry/exit | HIGH | LOW | P1 |
| Borderless/minimal chrome design | HIGH | LOW | P1 |
| Smooth cell animations | MEDIUM | MEDIUM | P1 |
| Ctrl-G external editor | HIGH | MEDIUM | P1 |
| Responsive layout breakpoints | MEDIUM | LOW | P2 |
| Animation env var toggle | LOW | LOW | P2 |
| Command history (up-arrow) | MEDIUM | HIGH | P3 |
| `/theme` live switching | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Required for v2.1 to deliver its stated "native and polished" goal
- P2: Polish pass — low effort, high return; add if time permits in v2.1
- P3: Defer to v2.2; worth doing but not blocking UX polish milestone

---

## Codex CLI Reference Patterns Mapped to Textual

| Codex CLI UX Pattern | v2.1 Approach | Confidence | Notes |
|----------------------|----------------|------------|-------|
| Input active immediately on launch | `AUTO_FOCUS = "Input"` on `ConductorApp` | HIGH | Textual AUTO_FOCUS class var is officially documented; CSS selector `"Input"` targets first `Input` widget |
| Alt-screen with clean exit (no artifacts) | Textual `App.run()` enters alt-screen automatically; verify `SIGINT` → `action_quit()` path | HIGH | Textual handles terminal state restoration; primary risk is SIGINT not routing through `action_quit()` |
| Minimal chrome (no heavy panel borders) | `border: none` / `border: blank` in `conductor.tcss` | HIGH | Textual CSS border styles include `none` and `blank`; `DEFAULT_CSS` in Python files is overridden by external `.tcss` |
| Smooth cell fade-in on message appear | `widget.animate("opacity", 1.0, duration=0.15)` after `mount()` | HIGH | Textual `animate()` supports `opacity`; `in_out_cubic` easing is the documented default for "pleasing organic motion" |
| External editor for multi-line composition | `with self.suspend(): subprocess.call([editor, tempfile])` | HIGH | `App.suspend()` officially documented since v0.48.0; GitHub discussion #165 confirms the tempfile pattern; vim launched in subprocess with SIGTSTP |

---

## Implementation Notes Per Feature

### Auto-Focus Input

The `ConductorApp` class currently does NOT have an `AUTO_FOCUS` class variable. Textual's default behavior focuses the first focusable widget — in the current layout, that is inside `TranscriptPane` (a `VerticalScroll`), not `CommandInput`. The fix is one line:

```python
class ConductorApp(App):
    AUTO_FOCUS = "Input"  # CSS selector: targets first Input widget (inside CommandInput)
```

This must be tested against the session replay path, where `CommandInput.disabled = True` is set in `on_mount`. A disabled widget cannot receive focus. Textual should skip disabled widgets when resolving `AUTO_FOCUS`, but verify empirically. The `_replay_session()` worker already calls `cmd.query_one(Input).focus()` on completion — this covers the resume path.

### Clean Alt-Screen Entry/Exit

Textual enters alt-screen on `App.run()` and exits on `self.exit()`. The risk is `SIGINT` (Ctrl+C). If `SIGINT` bypasses `action_quit()`, the terminal may be left in a bad state. Verify with:

```python
import signal

async def on_mount(self) -> None:
    # Ensure Ctrl+C routes through clean quit
    import signal
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, lambda: self.call_later(self.action_quit))
```

Alternatively, Textual may already handle this. Test empirically: run the app, press Ctrl+C, verify prompt is clean.

### Borderless Design

Current heavy borders to remove or reduce:
- `CommandInput DEFAULT_CSS`: `border-top: solid $primary 30%` — replace with `border-top: blank` or a subtle `border-top: solid $surface-lighten-1`
- `UserCell DEFAULT_CSS`: `border-left: thick $primary` — reduce to `border-left: wide $primary 50%` or a thin accent line
- `AssistantCell DEFAULT_CSS`: `border-left: thick $accent` — same treatment
- Input widget inside `CommandInput`: already `border: none` — keep

The goal is to distinguish cells by background color and left accent line (thin), not by thick box borders. This is exactly the Codex CLI aesthetic: color blocks with minimal framing, no box borders.

### Smooth Animations

Cell fade-in implementation:

```python
async def add_user_message(self, text: str) -> UserCell:
    cell = UserCell(text)
    cell.styles.opacity = 0.0  # start invisible
    await self.mount(cell)
    cell.animate("opacity", 1.0, duration=0.15, easing="in_out_cubic")
    # ... existing scroll_end logic
```

Env var check pattern:

```python
import os
_ANIMATIONS = os.environ.get("CONDUCTOR_NO_ANIMATIONS", "") not in ("1", "true", "yes")

if _ANIMATIONS:
    cell.animate("opacity", 1.0, duration=0.15)
```

The existing shimmer in `AssistantCell` uses a `Timer` + manual `Color` interpolation. This is correct and should be preserved — it's a different kind of animation (pulse while streaming) from the cell-entry fade (one-shot on mount).

### Ctrl-G External Editor

Full implementation pattern:

```python
BINDINGS = [
    Binding("ctrl+g", "open_editor", "Open in editor", show=False),
    # ... existing bindings
]

def action_open_editor(self) -> None:
    """Open current input content in $VISUAL/$EDITOR (vim fallback) for multiline editing."""
    import os
    import subprocess
    import tempfile
    from conductor.tui.widgets.command_input import CommandInput
    from textual.widgets import Input

    if sys.platform == "win32":
        self.notify("External editor not supported on Windows", severity="warning")
        return

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"

    cmd_input = self.query_one(CommandInput)
    current_text = cmd_input.query_one(Input).value

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="conductor_"
    ) as f:
        f.write(current_text)
        tmppath = f.name

    try:
        with self.suspend():
            subprocess.call([editor, tmppath])
        edited = Path(tmppath).read_text().rstrip("\n")
        cmd_input.query_one(Input).value = edited
        cmd_input.query_one(Input).cursor_position = len(edited)
    finally:
        Path(tmppath).unlink(missing_ok=True)
```

Note: `action_open_editor` must be a synchronous method (not async) because `App.suspend()` is a context manager, not a coroutine. If it needs to be async, use `asyncio.get_event_loop().run_in_executor()` inside the suspend block instead of `subprocess.call()`.

---

## Sources

- [Textual App guide — App.suspend() and inline mode](https://textual.textualize.io/guide/app/) — HIGH confidence; official documentation; confirms `suspend()` context manager for external processes
- [Textual App API — AUTO_FOCUS, set_focus, suspend](https://textual.textualize.io/api/app/) — HIGH confidence; `AUTO_FOCUS = '*'` classvar documented; `set_focus()` signature confirmed
- [Textual Input guide — focus management](https://textual.textualize.io/guide/input/) — HIGH confidence; confirms default focus goes to first focusable widget; `can_focus` attribute
- [Textual Animation guide — animate(), easing functions](https://textual.textualize.io/guide/animation/) — HIGH confidence; `opacity` and `offset` are animatable; `in_out_cubic` default easing; duration in seconds
- [Textual Border styles — none, blank, hidden](https://textual.textualize.io/styles/border/) — HIGH confidence; full border style list; `none` removes border space; `blank` maintains space invisibly
- [Textual GitHub Discussion #165 — Running shell apps / vim from Textual](https://github.com/Textualize/textual/discussions/165) — HIGH confidence; confirms `App.suspend()` pattern; tempfile approach; pre-suspend manual driver approach for older versions
- [Textual GitHub Issue #4385 — inline mode + command palette conflict](https://github.com/Textualize/textual/issues/4385) — HIGH confidence; confirms inline mode is NOT right for Conductor
- [Textual Input auto-focus discussion #4143](https://github.com/Textualize/textual/discussions/4143) — MEDIUM confidence; community confirms AUTO_FOCUS class variable behavior; `""` to disable
- Existing Conductor source: `packages/conductor-core/src/conductor/tui/app.py` — HIGH confidence; direct code review; confirms existing `action_quit()`, `on_mount()`, BINDINGS absence, focus calls in stream_done and replay paths
- Existing Conductor source: `packages/conductor-core/src/conductor/tui/widgets/command_input.py` — HIGH confidence; confirms `CommandInput` structure, inner `Input` widget, current border CSS
- Existing Conductor source: `packages/conductor-core/src/conductor/tui/widgets/transcript.py` — HIGH confidence; confirms shimmer animation implementation, `add_user_message` / `add_assistant_streaming` as mount points
- Existing Conductor source: `packages/conductor-core/src/conductor/tui/conductor.tcss` — HIGH confidence; confirms current CSS is minimal and extensible

---
*Feature research for: Conductor v2.1 UX Polish (alt-screen, borderless, animations, external editor)*
*Researched: 2026-03-11*
