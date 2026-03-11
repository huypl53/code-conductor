# Architecture Research

**Domain:** Textual TUI UX Polish — v2.1 feature integration into existing ConductorApp
**Researched:** 2026-03-11
**Confidence:** HIGH

---

## Standard Architecture

### System Overview

The existing v2.0 TUI is a flat-compose App with four widgets sharing the same Screen. V2.1 adds behaviour at specific integration seams without restructuring the component tree.

```
┌──────────────────────────────────────────────────────────────────────┐
│                  ConductorApp(App)                                    │
│                                                                       │
│  CLASS-LEVEL additions (v2.1):                                        │
│    AUTO_FOCUS = "Input"           ← auto-focus fix                   │
│    TITLE = "Conductor"                                                │
│    CSS = "Screen { border: none; padding: 0; }"  ← borderless        │
│    BINDINGS = [Binding("ctrl+g", "open_editor")]  ← editor hotkey    │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  Screen (full alt-screen, no border, no padding)                │  │
│  │  ┌────────────────────────────────┐  ┌──────────────────────┐   │  │
│  │  │  TranscriptPane                │  │  AgentMonitorPane    │   │  │
│  │  │  (VerticalScroll)              │  │  width: 30           │   │  │
│  │  │  - UserCell                    │  │  border-left:        │   │  │
│  │  │  - AssistantCell               │  │    solid $primary    │   │  │
│  │  │    + shimmer animation         │  │    20%               │   │  │
│  │  │      (set_interval, existing)  │  └──────────────────────┘   │  │
│  │  └────────────────────────────────┘                             │  │
│  │  ┌─────────────────────────────────────────────────────────┐   │  │
│  │  │  CommandInput                                            │   │  │
│  │  │  - Input (focused on mount via AUTO_FOCUS)               │   │  │
│  │  │  - SlashAutocomplete                                     │   │  │
│  │  │  - Ctrl-G triggers action_open_editor() on App          │   │  │
│  │  └─────────────────────────────────────────────────────────┘   │  │
│  │  ┌─────────────────────────────────────────────────────────┐   │  │
│  │  │  StatusFooter (dock: bottom)                             │   │  │
│  │  └─────────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  action_open_editor():                                                │
│    suspend() context manager → subprocess vim tempfile → resume      │
│    → post_message(EditorContentReady(text))                           │
│    → CommandInput fills Input.value with tempfile content             │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities for v2.1

| Component | v2.1 Change | How |
|-----------|-------------|-----|
| `ConductorApp` | Add `AUTO_FOCUS`, `BINDINGS`, CSS override | Class-level additions only |
| `conductor.tcss` | Borderless Screen, remove `$surface` background artifacts | Edit CSS file |
| `CommandInput` | Remove `border-top` or soften it for borderless feel; ensure Input is focusable | Edit `DEFAULT_CSS` |
| `AssistantCell` | No change — shimmer via `set_interval` works; `styles.animate()` is optional upgrade | Optional refactor |
| `ConductorApp.action_open_editor` | New method — `suspend()` + vim + `EditorContentReady` | New method on App |
| `EditorContentReady` | New message type in `messages.py` | New `Message` subclass |
| `CommandInput.on_editor_content_ready` | Fill `Input.value` with editor text; optionally auto-submit | New handler |

---

## Recommended Project Structure

All v2.1 changes land in existing files. No new modules needed.

```
conductor/tui/
├── app.py                  # MODIFIED: AUTO_FOCUS, BINDINGS, action_open_editor()
├── conductor.tcss          # MODIFIED: borderless Screen, remove stray borders
├── messages.py             # MODIFIED: add EditorContentReady message
└── widgets/
    ├── command_input.py    # MODIFIED: DEFAULT_CSS tweak, on_editor_content_ready()
    └── transcript.py       # UNCHANGED (shimmer stays as-is for now)
```

### Structure Rationale

- **No new files:** All four features touch existing seams. Adding new modules would split context unnecessarily.
- **`action_open_editor` on App, not CommandInput:** Actions in Textual bubble up the widget tree. Binding Ctrl-G at the App level means it fires regardless of which widget has focus. The App is the correct owner of external process lifecycle (`suspend()`).
- **`EditorContentReady` in messages.py:** Keeps the event bus explicit. CommandInput receives the filled text via message rather than a direct method call — consistent with how `StreamDone` and `TokensUpdated` already work.

---

## Architectural Patterns

### Pattern 1: AUTO_FOCUS for Input on Mount

**What:** Set `AUTO_FOCUS = "Input"` on `ConductorApp`. Textual evaluates this CSS selector against the widget tree when the default Screen activates and focuses the first match.

**When to use:** Any time you want a specific widget to receive keyboard focus at startup without calling `set_focus()` in `on_mount`.

**Trade-offs:** `AUTO_FOCUS` is evaluated on Screen activation, not App mount — meaning it also fires when a modal is dismissed and the main screen becomes active again. That is the correct behaviour here: Ctrl-G editor and escalation modals should both return focus to the Input naturally.

**Implementation — where it goes:**
```python
# conductor/tui/app.py
class ConductorApp(App):
    AUTO_FOCUS = "Input"  # CSS selector — matches any Input widget
    CSS_PATH = Path(__file__).parent / "conductor.tcss"
```

Note: the existing `on_stream_done` and `_replay_session` handlers both manually call `cmd.query_one(Input).focus()` as a belt-and-suspenders restore. With `AUTO_FOCUS` in place those calls become redundant but harmless — leave them for the cases where the main screen was never deactivated (no modal was pushed).

**Confidence:** HIGH — `AUTO_FOCUS` is a documented App/Screen class variable. Default is `"*"` (first focusable widget). Setting it to `"Input"` pins it to the Input widget class.

---

### Pattern 2: Alt-Screen Mode (Default Textual Behaviour)

**What:** Textual's default `App.run()` already uses full alt-screen mode. The terminal is taken over completely on start and restored on exit. No flag is needed.

**When to use:** This is implicit — calling `ConductorApp().run()` without `inline=True` runs in alt-screen mode.

**The actual problem:** The current `Screen` in `conductor.tcss` may have `background: $surface` which produces a coloured background that differs from the user's terminal. Removing or softening the Screen background colour creates a "native" alt-screen feel.

**Implementation — no App.run() change needed:**
```python
# No change to CLI entry point.
# ConductorApp(...).run()  ← already alt-screen by default
```

```css
/* conductor.tcss — remove background to use terminal's native background */
Screen {
    layers: base overlay;
    /* Remove: background: $surface; */
}
```

**Confidence:** HIGH — `inline=True` is the flag for inline mode. Without it, alt-screen is the default. Verified in official Textual app guide.

---

### Pattern 3: Borderless Design via CSS

**What:** Remove all `border-*` declarations from the main layout widgets. Use spacing (padding/margin) and background tint contrast to create visual separation instead of lines.

**When to use:** When the goal is a "content-first" design that feels native to the terminal rather than a window-within-a-terminal.

**Trade-offs:** Modals (`FileApprovalModal`, `CommandApprovalModal`, `EscalationModal`) retain their `border: solid $primary` — that separation is intentional for an overlay. Only the main screen layout becomes borderless.

**Specificity rule:** `DEFAULT_CSS` has the lowest specificity in Textual. The external CSS file (`conductor.tcss`) overrides `DEFAULT_CSS`. The App-level `CSS` class variable overrides both. Use `conductor.tcss` for layout-level borderless rules so individual widget `DEFAULT_CSS` handles widget-internal styles.

**Implementation:**
```css
/* conductor.tcss */
Screen {
    layers: base overlay;
    /* No border, no background override — uses terminal default */
}

#app-body {
    width: 1fr;
    height: 1fr;
    layout: horizontal;
    /* No border */
}
```

```css
/* CommandInput DEFAULT_CSS — remove the border-top separator */
CommandInput {
    height: 3;
    padding: 0 1;
    background: $panel;
    /* Remove: border-top: solid $primary 30%; */
}
```

```css
/* AgentMonitorPane DEFAULT_CSS — keep left separator for column boundary */
AgentMonitorPane {
    width: 30;
    height: 1fr;
    background: $panel;
    border-left: solid $primary 20%;  /* keep — this creates column separation */
    padding: 1 1;
}
```

**Confidence:** MEDIUM — CSS specificity rules verified from official Textual docs. The specific visual outcome depends on terminal theme and needs manual review.

---

### Pattern 4: External Editor via App.suspend()

**What:** `App.suspend()` is a synchronous context manager that temporarily surrenders the terminal to an external process. Inside the `with self.suspend():` block, Textual stops reading input and rendering output. The external process has full terminal control. When the block exits, Textual resumes.

**When to use:** Any time the TUI needs to hand off to a full-screen terminal program (vim, nano, fzf, git commit editor).

**Trade-offs:**
- `suspend()` is not available on Windows or in Textual Web — only Unix-like terminals.
- The action must be synchronous (`def`, not `async def`). `subprocess.run()` is blocking and runs in the `with suspend():` block directly — do not use `asyncio.create_subprocess_exec` here.
- After suspension ends, focus returns to whatever Textual last had focused. `AUTO_FOCUS` kicks in if the Screen reactivates. For the editor case, manually restoring Input focus after writing to `Input.value` is the safe approach.

**Implementation — where each piece lives:**

```python
# conductor/tui/messages.py — new message
class EditorContentReady(Message):
    """Text returned from an external editor session."""
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()
```

```python
# conductor/tui/app.py — new binding and action
import subprocess
import tempfile
import os

class ConductorApp(App):
    AUTO_FOCUS = "Input"
    BINDINGS = [
        Binding("ctrl+g", "open_editor", "Open in editor", show=False),
    ]

    def action_open_editor(self) -> None:
        """Open current input text in $EDITOR (default: vim) for multiline composition."""
        from conductor.tui.widgets.command_input import CommandInput
        from conductor.tui.messages import EditorContentReady

        try:
            cmd_input = self.query_one(CommandInput)
            current_text = cmd_input.query_one(Input).value
        except Exception:
            current_text = ""

        editor = os.environ.get("EDITOR", "vim")

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            prefix="conductor_",
            delete=False,
        ) as f:
            f.write(current_text)
            tmp_path = f.name

        try:
            with self.suspend():
                subprocess.run([editor, tmp_path], check=False)
            with open(tmp_path) as f:
                text = f.read().strip()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if text:
            self.post_message(EditorContentReady(text))
```

```python
# conductor/tui/widgets/command_input.py — receive editor content
from conductor.tui.messages import EditorContentReady

class CommandInput(Widget):

    def on_editor_content_ready(self, event: EditorContentReady) -> None:
        """Fill the Input with text returned from the external editor."""
        inp = self.query_one(Input)
        inp.value = event.text
        inp.cursor_position = len(event.text)
        inp.focus()
        event.stop()
```

**Why the action lives on App, not CommandInput:** `suspend()` is an App method. Placing the action on `ConductorApp` avoids passing an App reference into the widget. The BINDING on `ConductorApp` fires regardless of current focus — even if a modal is somehow active — because App bindings have the broadest scope.

**Why `EditorContentReady` is posted as a message, not a direct method call:** `action_open_editor` runs on the app. Calling `cmd_input.query_one(Input).value = text` directly from the action would work (actions run on the event loop), but posting a message keeps the widget API clean and consistent with how other cross-widget updates work in this codebase (`StreamDone`, `TokensUpdated`).

**Confidence:** HIGH for `suspend()` pattern — verified in official Textual docs and GitHub issue #1093 (resolved in PR #4064). MEDIUM for the `EDITOR` env var approach — standard Unix convention, not Textual-specific.

---

### Pattern 5: Animation — set_interval vs Widget.animate()

**What:** The existing shimmer in `AssistantCell` uses `set_interval` at 15 fps, manually computing a sine-wave alpha and writing to `self.styles.tint` each tick. This is a correct and working pattern. `Widget.animate()` is an alternative that delegates interpolation to Textual's animator.

**When to use `set_interval` (existing approach):** Non-linear, cyclical animations (ping-pong, sine wave) where you want full control over the easing curve. The current shimmer is a good fit — it loops continuously while streaming.

**When to use `Widget.animate()` / `styles.animate()`:** One-shot transitions with a natural end state: fade-in on mount, fade-out on finalize, slide entrance. `styles.animate("opacity", value=0.0, duration=0.3, easing="out_cubic")` for cell exit animations.

**v2.1 recommendation:** Keep the existing shimmer as-is. Add `styles.animate()` only for new one-shot transitions: fade-in when an `AssistantCell` mounts, fade-out or brief flash when it finalizes. This adds polish without changing the working shimmer logic.

**Possible addition — cell mount fade-in:**
```python
# conductor/tui/widgets/transcript.py
class AssistantCell(Widget):

    def on_mount(self) -> None:
        """Fade in from transparent on mount for a smooth entrance."""
        self.styles.opacity = 0.0
        self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")
```

**Animatable style properties (verified):** `opacity`, `offset`. `tint` animates because `Color` satisfies the `Animatable` protocol in Textual (it supports linear interpolation). The existing shimmer directly sets `styles.tint` on each tick — `styles.animate("tint", ...)` would also work for a single-cycle transition.

**Confidence:** HIGH for `styles.animate("opacity", ...)` — documented in official animation guide. MEDIUM for `styles.animate("tint", ...)` — Color implements the Animatable protocol per search findings, not explicitly documented with examples.

---

## Data Flow

### Ctrl-G Editor Flow

```
User presses Ctrl+G
    ↓
ConductorApp.action_open_editor() (sync action, runs on event loop)
    ↓ reads CommandInput > Input.value as starting text
    ↓ writes to tempfile
    ↓ with self.suspend():
    │     Textual stops rendering and input capture
    │     subprocess.run(["vim", tmp_path])  ← blocking, terminal is vim's
    │     vim exits
    │ Textual resumes rendering and input capture
    ↓ reads tempfile content
    ↓ os.unlink(tmp_path)
    ↓ self.post_message(EditorContentReady(text))
    ↓
CommandInput.on_editor_content_ready(event)
    ↓ inp.value = event.text
    ↓ inp.cursor_position = len(event.text)
    ↓ inp.focus()
    ↓ event.stop()
```

### Auto-Focus Flow (startup and post-modal)

```
ConductorApp.run() starts
    ↓ Textual activates default Screen
    ↓ Screen evaluates AUTO_FOCUS = "Input"
    ↓ first Input widget (inside CommandInput) receives focus
    ↓ user can type immediately

[Modal pushed]
    ↓ ModalScreen renders over main Screen
    ↓ Modal's own AUTO_FOCUS or explicit focus targets modal Input

[Modal dismissed]
    ↓ main Screen reactivates
    ↓ AUTO_FOCUS re-evaluated → Input focused again
    (belt-and-suspenders: existing explicit focus() calls in on_stream_done
     and _replay_session also fire, which is harmless)
```

### Borderless Design — CSS Cascade

```
Textual CSS specificity order (lowest to highest):
    Widget DEFAULT_CSS
    ↓
    App CSS_PATH (conductor.tcss)       ← primary layout rules live here
    ↓
    App CSS class variable              ← for minimal overrides if needed
    ↓
    inline styles (self.styles.*)       ← shimmer tint, animate() calls

Borderless:
    conductor.tcss: Screen { layers: base overlay; }  ← no background override
    conductor.tcss: #app-body { ... }                 ← no border
    CommandInput DEFAULT_CSS: remove border-top
    UserCell DEFAULT_CSS: keep border-left (content separator, not chrome)
    AssistantCell DEFAULT_CSS: keep border-left (content separator)
    Modal DEFAULT_CSS: keep border: solid $primary (overlay identity)
```

---

## Integration Points: New vs Existing

### Unchanged Components

| Component | Why Unchanged |
|-----------|---------------|
| `TranscriptPane` | No v2.1 changes needed; optional fade-in on `AssistantCell.on_mount` is additive |
| `AgentMonitorPane` | No change — border-left is correct as column separator |
| `StatusFooter` | No change — `dock: bottom` and height: 1 stay |
| `modals.py` | No change — modal borders are intentional chrome |
| `messages.py` | Add one new message type only (`EditorContentReady`) |
| `_stream_response`, `_replay_session` | No change to streaming or replay logic |

### Modified Components

| Component | Modification | Scope |
|-----------|-------------|-------|
| `app.py` | Add `AUTO_FOCUS = "Input"`, `BINDINGS = [Binding("ctrl+g", ...)]`, `action_open_editor()` method | ~30 lines added |
| `conductor.tcss` | Remove `background: $surface` from Screen; remove `border-top` from CommandInput override if desired | ~5 lines changed |
| `command_input.py` | Remove `border-top: solid $primary 30%` from `DEFAULT_CSS`; add `on_editor_content_ready()` handler | ~10 lines changed |
| `messages.py` | Add `EditorContentReady(Message)` | ~6 lines added |

### New Message Types

| Message | Posted By | Handled By |
|---------|-----------|------------|
| `EditorContentReady(text)` | `ConductorApp.action_open_editor` | `CommandInput.on_editor_content_ready` |

---

## Build Order

Build order respects dependencies: each phase is independently testable and does not require the next phase to function.

### Phase 1: Auto-Focus (no dependencies)

**What to change:** Add `AUTO_FOCUS = "Input"` to `ConductorApp`.

**Test:** Open TUI, verify Input is focused immediately without pressing Tab. Verify after Ctrl-C restart. Verify after escalation modal is dismissed.

**Risk:** LOW. Single class variable. Textual's default `"*"` already focuses the first focusable widget; this just pins it to `Input` specifically.

---

### Phase 2: Borderless Design (depends on Phase 1 for clean baseline)

**What to change:** Edit `conductor.tcss` and `CommandInput.DEFAULT_CSS`.

**Test:** Open TUI, verify no stray border lines between widgets. Verify modal overlays still have visible borders. Verify layout does not collapse (widths still correct via `1fr`).

**Risk:** LOW-MEDIUM. CSS changes are visual only. The main risk is accidentally removing a border that provides layout structure (e.g., the AgentMonitorPane left border). Keep the pane's `border-left` as a column separator.

---

### Phase 3: External Editor (depends on Phase 1; independent of Phase 2)

**What to change:** Add `Binding` and `action_open_editor` to `ConductorApp`; add `EditorContentReady` to `messages.py`; add `on_editor_content_ready` to `CommandInput`.

**Test:** Press Ctrl-G → vim opens → type text → `:wq` → TUI resumes → Input contains typed text. Test with `EDITOR=nano`. Test cancel (`vim :q!`) → Input unchanged. Test with pre-existing Input text → vim opens with that text as starting content.

**Risk:** MEDIUM. `suspend()` is Unix-only (not Windows, not Textual Web). The subprocess.run call is blocking — this is intentional, correct behaviour inside `with suspend():`. Risk is terminal emulator compatibility (some terminals have edge cases with suspend/resume and certain programs like fzf — vim is widely tested and should be fine).

---

### Phase 4: Smooth Animations (depends on nothing; fully additive)

**What to change:** Optionally add `on_mount` fade-in to `AssistantCell`.

**Test:** Send a message → verify AssistantCell fades in over ~250ms. Finalize streaming → no jarring snap. Performance: rapidly send multiple messages, verify no animation backlog causes lag.

**Risk:** LOW. `styles.animate("opacity", ...)` is a well-documented Textual API. If it causes any visual artifact, removing the `on_mount` override is a one-line revert.

---

## Anti-Patterns

### Anti-Pattern 1: Using App.run(inline=True) for Alt-Screen

**What people do:** Set `inline=True` on `App.run()` thinking it enables "full screen" mode.

**Why it's wrong:** `inline=True` does the opposite — it runs the app as an inline widget below the terminal prompt, not in alt-screen mode. The default (no `inline`) is already full alt-screen.

**Do this instead:** Call `ConductorApp(...).run()` without `inline=True`. Alt-screen is the default.

---

### Anti-Pattern 2: async action_open_editor

**What people do:** Make `action_open_editor` an `async def` and use `asyncio.create_subprocess_exec` to launch the editor.

**Why it's wrong:** `asyncio.create_subprocess_exec` does not suspend the Textual rendering loop or give the editor terminal control. The editor and Textual fight over the terminal simultaneously, producing garbled output.

**Do this instead:** Make the action `def` (synchronous). Use `with self.suspend():` and `subprocess.run()` (blocking). Textual's suspend mechanism correctly hands off terminal control.

---

### Anti-Pattern 3: Binding Ctrl-G on CommandInput

**What people do:** Add the `BINDINGS = [Binding("ctrl+g", ...)]` to `CommandInput` instead of `ConductorApp`.

**Why it's wrong:** `suspend()` is an App method. More importantly, Input widgets capture key events for text entry — the binding may not fire when the Input widget is focused and in text-entry mode. App-level bindings have higher priority and fire regardless of focus.

**Do this instead:** Put the binding on `ConductorApp`. The action references `CommandInput` via `self.query_one(CommandInput)`.

---

### Anti-Pattern 4: Removing Cell Border-Left for Borderless Design

**What people do:** Remove `border-left` from `UserCell` and `AssistantCell` when pursuing a borderless design.

**Why it's wrong:** The cell `border-left` is a content indicator (user vs assistant role), not chrome. Removing it makes the transcript visually ambiguous — messages blend together.

**Do this instead:** Remove borders from the layout containers (`Screen`, `#app-body`, `CommandInput`). Keep the cell border-left as a semantic marker. The distinction is: chrome borders (decorative, around containers) vs content borders (meaningful, indicating message role).

---

### Anti-Pattern 5: Direct Input.value Assignment Instead of Message

**What people do:** In `action_open_editor`, directly set `self.query_one(CommandInput).query_one(Input).value = text` after `suspend()` returns.

**Why it's wrong:** This works, but tightly couples the App to the widget's internal structure. It also bypasses the message bus that the rest of the codebase uses consistently.

**Do this instead:** Post `EditorContentReady(text)` and handle it in `CommandInput.on_editor_content_ready`. This is consistent with how `StreamDone`, `TokensUpdated`, and `AgentStateUpdated` are handled — workers and actions post messages, widgets handle them.

---

## Scaling Considerations

These features are UX-only; scaling considerations are about UX correctness under edge conditions.

| Concern | Approach |
|---------|----------|
| Ctrl-G during active streaming | `action_open_editor` fires regardless. The stream continues in the background while vim is open. On return, the user's editor content is in the Input; they can submit when ready. No race condition — streaming posts messages via the bus; suspend pauses rendering but not the asyncio loop tasks. Note: streaming may complete while in vim — normal behaviour. |
| Ctrl-G during replay session (input locked) | `CommandInput.disabled = True` during replay. Binding fires on App regardless, but the resulting `EditorContentReady` will set `Input.value` — the Input being disabled prevents submission. Consider guarding `action_open_editor` with `if self.query_one(CommandInput).disabled: return`. |
| Large tempfile from editor | No limit enforced. If user pastes a massive document into vim, it will be posted as the input. The SDK handles large inputs — not a TUI concern. |
| `EDITOR` not set or editor not found | `subprocess.run` returns non-zero or raises `FileNotFoundError`. Wrap in try/except; if editor fails, post nothing (Input unchanged). Log the error. |
| Animation performance with many cells | Each `AssistantCell` has its own 15 fps shimmer timer while streaming. Only one cell streams at a time (`@work(exclusive=True)`). Fade-in animation on mount is a one-shot 250ms tween — no sustained timer after completion. No scaling concern. |

---

## Sources

- [Textual App Basics — inline vs application mode](https://textual.textualize.io/guide/app/) — alt-screen is default, `inline=True` for inline — HIGH confidence (official docs)
- [Textual App API — AUTO_FOCUS, suspend(), run()](https://textual.textualize.io/api/app/) — class variable descriptions and defaults — HIGH confidence (official docs)
- [Textual Animation Guide — styles.animate(), easing, opacity](https://textual.textualize.io/guide/animation/) — animatable properties and method signature — HIGH confidence (official docs)
- [Textual GitHub Issue #1093 — Launching subprocesses like Vim](https://github.com/Textualize/textual/issues/1093) — `suspend()` + `subprocess.run` pattern, resolved in PR #4064 — HIGH confidence (maintainer response)
- [Textual GitHub Discussion #4143 — Input and AUTO_FOCUS](https://github.com/Textualize/textual/discussions/4143) — AUTO_FOCUS = "Input" pins focus to Input widget — MEDIUM confidence (community-verified)
- [Textual CSS Guide — specificity and DEFAULT_CSS](https://textual.textualize.io/guide/CSS/) — CSS_PATH overrides DEFAULT_CSS, CSS class var overrides both — HIGH confidence (official docs)
- Existing codebase: `app.py`, `conductor.tcss`, `command_input.py`, `transcript.py`, `modals.py`, `messages.py` — direct code inspection — HIGH confidence (primary source)

---

*Architecture research for: Conductor v2.1 — UX Polish feature integration*
*Researched: 2026-03-11*
