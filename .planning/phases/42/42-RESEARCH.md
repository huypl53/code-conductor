# Phase 42: Ctrl-G External Editor - Research

**Researched:** 2026-03-11
**Domain:** Textual TUI — `App.suspend()` + external editor subprocess + cross-widget message routing
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FOCUS-02 | User can press Ctrl-G to open current input in external editor (vim/$EDITOR) | `App.suspend()` + `@work(thread=True)` + `Binding("ctrl+g", ...)` — all verified in Textual 8.1.1 |
| FOCUS-03 | After editor closes, edited content replaces input widget text | `EditorContentReady` message + `CommandInput.on_editor_content_ready` handler sets `Input.value` and cursor position |
</phase_requirements>

---

## Summary

Phase 42 adds a single, focused feature: pressing Ctrl-G in the TUI suspends the Textual event loop, opens `$VISUAL` / `$EDITOR` (vim fallback) with the current input pre-populated in a temp file, and on editor close restores the terminal and fills `CommandInput` with the edited content — including multiline text.

The entire implementation lives in four existing files: `app.py` (binding + action), `messages.py` (new `EditorContentReady` message), and `command_input.py` (handler). No new files or dependencies are needed. The critical constraint is that `App.suspend()` is a synchronous context manager — the action method must be `def` (not `async def`) and launched via `@work(thread=True)`.

The five success criteria map directly to known, well-tested Textual patterns. The hardest part is not the happy path — it is the three guard conditions: replay-mode input locking, non-Unix fallback, and reading the temp file inside the `with self.suspend():` block before Textual recaptures stdin.

**Primary recommendation:** Place the Ctrl-G binding and `action_open_editor` on `ConductorApp` (not `CommandInput`), use `@work(thread=True)` with `App.suspend()` + `subprocess.run`, route result via `EditorContentReady` message.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `textual` | `8.1.1` | `App.suspend()`, `Binding`, `@work(thread=True)` | Already installed; `suspend()` is the only safe way to hand terminal to an external process |
| `subprocess` | stdlib | `subprocess.run([editor, tmppath])` inside suspend block | Blocking call required — async subprocess cannot hand terminal control to vim |
| `tempfile` | stdlib | `NamedTemporaryFile(delete=False)` for editor file | `delete=False` keeps file on disk for vim to open; manual cleanup via `os.unlink` |
| `os` | stdlib | `os.environ.get("VISUAL")`, `os.environ.get("EDITOR")`, `os.unlink()` | POSIX env var convention for editor selection |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `textual.app.SuspendNotSupported` | 8.1.1 | Exception raised on non-Unix systems | Catch to show graceful status message instead of crashing |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `@work(thread=True)` + `App.suspend()` | `async def` + `asyncio.create_subprocess_exec` | Async subprocess does NOT give terminal control to vim — TUI and vim fight over stdin; terminal corruption guaranteed. Use `@work(thread=True)`. |
| `subprocess.run` (blocking) | `subprocess.Popen` + polling | `Popen` is unnecessary complexity for an interactive editor; `subprocess.run` blocks inside the `with suspend():` block which is exactly correct. |
| `EditorContentReady` message | Direct `Input.value = text` in action | Direct assignment from the thread worker bypasses the message bus; inconsistent with how all other cross-widget updates work in this codebase (`StreamDone`, `TokensUpdated`). Use the message. |

**Installation:** No new dependencies. All APIs are in the installed stack.

```bash
# Verify — no uv add needed
uv run python -c "import textual; print(textual.__version__)"
# Expected: 8.1.1
```

---

## Architecture Patterns

### Recommended Project Structure

All changes land in existing files. No new modules needed.

```
conductor/tui/
├── app.py              # MODIFIED: add BINDINGS entry, action_open_editor() method
├── messages.py         # MODIFIED: add EditorContentReady message class
└── widgets/
    └── command_input.py  # MODIFIED: add on_editor_content_ready() handler
```

### Pattern 1: Thread Worker + App.suspend() for External Processes

**What:** `App.suspend()` is a synchronous context manager that surrenders terminal control to a child process. It must be called from a synchronous thread worker (`@work(thread=True)`), not from an async coroutine.

**When to use:** Any time the TUI needs to launch a full-screen terminal application (vim, nano, fzf, git commit editor).

**The canonical flow:**

```python
# Source: Textual official docs + GitHub Discussion #165
# In ConductorApp (app.py)

from textual import work
from textual.app import SuspendNotSupported
from textual.binding import Binding

BINDINGS = [
    Binding("ctrl+g", "open_editor", "Open in editor", show=False),
    # ... existing bindings
]

@work(thread=True, exit_on_error=False)
def action_open_editor(self) -> None:
    """Open current input content in $VISUAL/$EDITOR (vim fallback)."""
    import os
    import subprocess
    import tempfile
    import sys
    from textual.widgets import Input
    from conductor.tui.widgets.command_input import CommandInput
    from conductor.tui.messages import EditorContentReady

    # Guard 1: replay mode — input is locked
    try:
        cmd_input = self.query_one(CommandInput)
        if cmd_input.disabled:
            return
        current_text = cmd_input.query_one(Input).value
    except Exception:
        current_text = ""

    # Guard 2: non-Unix environments
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix="conductor_",
        delete=False,
    ) as f:
        f.write(current_text)
        tmp_path = f.name

    edited_text = current_text  # default: unchanged on cancel

    try:
        try:
            with self.app.suspend():
                subprocess.run([editor, tmp_path], check=False)
                # CRITICAL: read file INSIDE suspend block before Textual recaptures stdin
                with open(tmp_path) as fh:
                    edited_text = fh.read()
        except SuspendNotSupported:
            self.app.call_from_thread(
                self.app.notify,
                "External editor not supported in this environment",
                severity="warning",
            )
            return
        except FileNotFoundError:
            self.app.call_from_thread(
                self.app.notify,
                f"Editor not found: {editor}",
                severity="warning",
            )
            return
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    # Route result back via message bus (safe cross-thread communication)
    stripped = edited_text.rstrip("\n")
    if stripped != current_text:
        self.app.call_from_thread(
            self.app.post_message, EditorContentReady(stripped)
        )
```

**Key constraints:**
- `action_open_editor` must be `def` (synchronous), not `async def`
- `@work(thread=True)` is REQUIRED — `App.suspend()` is a sync context manager, not a coroutine
- Read temp file INSIDE `with self.app.suspend():` block — after the block exits Textual recaptures stdin and any file I/O race is irrelevant, but reading inside is the documented safe pattern
- Use `self.app.call_from_thread()` for all interactions with Textual from the thread worker

### Pattern 2: EditorContentReady Message

**What:** New message type in `messages.py`. Posted by the App-level thread worker, handled by `CommandInput`.

```python
# Source: messages.py pattern — consistent with TokenChunk, StreamDone, UserSubmitted

class EditorContentReady(Message):
    """Text returned from an external editor session; fills CommandInput."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()
```

### Pattern 3: CommandInput Handler

**What:** `on_editor_content_ready` sets `Input.value`, positions cursor at end, and focuses the input.

```python
# Source: CommandInput.on_input_submitted pattern + Phase 38 focus restoration pattern
# In CommandInput (command_input.py)

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

### Data Flow

```
User presses Ctrl+G
    |
    v
ConductorApp.action_open_editor() dispatched by Textual
    |
    v [Textual spawns thread via @work(thread=True)]
Thread worker:
    | -- Guard: cmd_input.disabled? --> return (replay mode, no crash)
    | -- Guard: SuspendNotSupported? --> notify(), return (CI/Windows)
    | -- Guard: FileNotFoundError? --> notify("editor not found"), return
    |
    v
Write Input.value to tempfile (conductor_*.md)
    |
    v
with self.app.suspend():
    |  Textual stops rendering + input capture
    |  subprocess.run([editor, tmp_path])  <-- blocking, vim owns terminal
    |  editor exits
    |  read tmp_path content  <-- INSIDE suspend block
    v
Textual resumes rendering + input capture
    |
    v
os.unlink(tmp_path)
    |
    v
self.app.call_from_thread(self.app.post_message, EditorContentReady(text))
    |
    v
CommandInput.on_editor_content_ready(event)
    |
    v
inp.value = event.text
inp.cursor_position = len(event.text)
inp.focus()
event.stop()
    |
    v
User sees edited content in input, cursor at end, ready to submit
```

### Anti-Patterns to Avoid

- **`async def action_open_editor`:** `App.suspend()` is synchronous. An async action using `asyncio.create_subprocess_exec` gives vim a broken terminal — TUI and editor fight over stdin.
- **`subprocess.run` without `App.suspend()`:** Textual holds the terminal in raw mode; vim receives broken input. Always use the context manager.
- **Binding Ctrl-G on `CommandInput` instead of `ConductorApp`:** App-level bindings have the highest priority in Textual's key routing. `Input` widgets in text-entry mode can consume keys before they reach widget-level bindings. App binding fires reliably regardless of which widget has focus.
- **Reading temp file AFTER `suspend()` block exits:** Textual recaptures the terminal when the `with` block exits. While reading the file after is functionally correct (it's a temp file on disk, not a TTY), the documented pattern reads inside the block.
- **Direct `Input.value = text` from the thread worker:** Widget state must be modified on Textual's main thread. Use `call_from_thread` + message routing.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Suspend/restore terminal | Custom `termios` save/restore | `App.suspend()` | `suspend()` handles sigstop, driver state, screen redraw, cursor visibility restore — dozens of edge cases |
| Editor selection | Custom editor picker UI | `$VISUAL`/`$EDITOR`/vim fallback | POSIX convention; power users already have their preference set; adding a picker is wasted scope |
| Cross-thread widget update | Direct `widget.value = x` from thread | `call_from_thread` + message | Textual's widget state is not thread-safe; direct writes from a thread worker cause rendering corruption |
| Non-Unix detection | `sys.platform == "win32"` check | Catch `SuspendNotSupported` | `SuspendNotSupported` is the correct Textual API signal; platform checks miss Textual Web and headless CI |

**Key insight:** The complexity in this feature is not the happy path (write file, open vim, read file) — it is the guard conditions and cleanup. `App.suspend()` already handles all the terminal lifecycle complexity. The implementation should be thin around that API.

---

## Common Pitfalls

### Pitfall 1: async action leaves terminal broken

**What goes wrong:** `async def action_open_editor` with `asyncio.create_subprocess_exec` does not give the editor terminal control. Vim opens but keystrokes are split between Textual's event loop and vim's stdin handler. Terminal is left in raw mode on exit.

**Why it happens:** `asyncio.create_subprocess_exec` spawns the child but the asyncio event loop continues running — Textual keeps reading stdin concurrently with vim.

**How to avoid:** Use `def action_open_editor` (synchronous) + `@work(thread=True)`. The thread blocks on `subprocess.run` inside `with self.app.suspend()`.

**Warning signs:** Vim opens but typing produces garbled output; TUI has artifacts after vim exits; `stty -a` shows `raw` mode after test.

---

### Pitfall 2: Reading temp file outside suspend block causes a race

**What goes wrong:** If the temp file is read after `with self.app.suspend():` exits, Textual has already recaptured the terminal. In practice this is usually harmless (file is still on disk), but on high-load systems the timer for temp file cleanup could race.

**Why it happens:** The documented Textual pattern (GitHub Discussion #165) reads the file inside the `with` block explicitly.

**How to avoid:** Always read `tmp_path` inside the `with self.app.suspend():` block, immediately after `subprocess.run` returns.

---

### Pitfall 3: Ctrl-G fires during session replay — crash or wrong behaviour

**What goes wrong:** During `_replay_session()`, `CommandInput.disabled = True`. If `action_open_editor` runs, it reads `cmd_input.disabled` as `True` — without a guard, the editor opens, the user edits, and `EditorContentReady` is posted. `CommandInput.on_editor_content_ready` sets `inp.value` on a disabled widget — `inp.focus()` silently fails, content may be lost.

**Why it happens:** App-level bindings fire regardless of widget disabled state.

**How to avoid:** Add an explicit `if cmd_input.disabled: return` guard as the first operation in `action_open_editor`.

---

### Pitfall 4: SuspendNotSupported crashes in CI or Textual Web

**What goes wrong:** In headless CI and Textual Web, `App.suspend()` raises `SuspendNotSupported`. Without a handler, the thread worker crashes and `exit_on_error=False` silently swallows it — user sees nothing happen when pressing Ctrl-G.

**Why it happens:** `suspend()` uses `SIGTSTP` which is only available on Unix with a real TTY.

**How to avoid:** Wrap `with self.app.suspend():` in `try/except SuspendNotSupported` and use `self.app.call_from_thread(self.app.notify, "...", severity="warning")` to surface feedback.

---

### Pitfall 5: Ctrl-G binding intercepted by SlashAutocomplete

**What goes wrong:** `SlashAutocomplete` is a `textual_autocomplete.AutoComplete` widget that wraps the `Input` widget in `CommandInput`. If `SlashAutocomplete` has a key handler that consumes unrecognized keys before bubbling, Ctrl-G may never reach the App-level binding.

**Why it happens:** Textual key routing: focused widget → parent widgets → screen → app. If any handler returns before bubbling, higher levels never see the key.

**How to avoid:** Place Ctrl-G as an App-level binding (highest priority). Test with `textual console` key event log — if the binding doesn't fire, add an explicit `on_key` in `CommandInput` to forward `ctrl+g` before autocomplete processes it.

**Warning signs:** Ctrl-G produces no effect when the input is focused with a `/` prefix typed (when autocomplete dropdown is visible).

---

### Pitfall 6: Terminal state after vim crash or SIGKILL

**What goes wrong:** If vim is killed (`kill -9`) while the editor is open, the `with self.app.suspend():` block exits without vim having restored terminal state. Textual resumes but the terminal may be in partial raw mode.

**Why it happens:** `app.suspend()` uses a `try/finally` to restore terminal settings, but SIGKILL bypasses process cleanup. The `subprocess.run` call returns immediately when the child is killed.

**How to avoid:** Wrap the entire `with self.app.suspend():` block in its own `try/except Exception`. After exit, Textual's own `refresh()` call (triggered automatically on suspend exit) re-asserts its terminal state. This is sufficient for vim crashes — the documented mitigation is the `try/except` wrapper, not manual terminal restoration.

---

## Code Examples

### Full action_open_editor with all guards

```python
# Source: Textual official docs + GitHub Discussion #165 + PITFALLS.md
# Placement: ConductorApp class in app.py

@work(thread=True, exit_on_error=False)
def action_open_editor(self) -> None:
    """Open current input content in $VISUAL/$EDITOR (vim fallback)."""
    import os
    import subprocess
    import tempfile
    from textual.app import SuspendNotSupported
    from textual.widgets import Input
    from conductor.tui.widgets.command_input import CommandInput
    from conductor.tui.messages import EditorContentReady

    # Guard: replay mode — input is locked, do nothing
    try:
        cmd_input = self.query_one(CommandInput)
        if cmd_input.disabled:
            return
        current_text = cmd_input.query_one(Input).value
    except Exception:
        current_text = ""

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".md",
        prefix="conductor_",
        delete=False,
    ) as f:
        f.write(current_text)
        tmp_path = f.name

    edited_text = current_text  # unchanged if editor cancelled or failed

    try:
        try:
            with self.app.suspend():
                subprocess.run([editor, tmp_path], check=False)
                with open(tmp_path) as fh:
                    edited_text = fh.read()
        except SuspendNotSupported:
            self.app.call_from_thread(
                self.app.notify,
                "External editor not supported in this environment",
                severity="warning",
            )
            return
        except (FileNotFoundError, OSError):
            self.app.call_from_thread(
                self.app.notify,
                f"Editor not found: {editor}",
                severity="warning",
            )
            return
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    stripped = edited_text.rstrip("\n")
    if stripped != current_text or stripped:
        self.app.call_from_thread(
            self.app.post_message, EditorContentReady(stripped)
        )
```

### EditorContentReady message

```python
# Source: messages.py pattern — matches existing Message subclasses

class EditorContentReady(Message):
    """Text returned from an external editor session; fills CommandInput."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()
```

### CommandInput handler

```python
# Source: consistent with on_input_submitted pattern + Phase 38 focus restoration

def on_editor_content_ready(self, event: EditorContentReady) -> None:
    """Fill the Input with text returned from the external editor."""
    from conductor.tui.messages import EditorContentReady
    inp = self.query_one(Input)
    inp.value = event.text
    inp.cursor_position = len(event.text)
    inp.focus()
    event.stop()
```

### Binding declaration (in ConductorApp.BINDINGS)

```python
# Source: STACK.md verified pattern — Binding("ctrl+g", ...) accepted by Textual 8.1.1

BINDINGS = [
    Binding("ctrl+g", "open_editor", "Open in editor", show=False),
]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual `termios` save/restore + `subprocess.call` | `App.suspend()` context manager | Textual v0.48.0 (PR #4064) | Eliminates all manual terminal state management; handles driver cleanup, screen restore, cursor visibility |
| `async def action + asyncio.create_subprocess_exec` | `def action + @work(thread=True) + subprocess.run` | Textual suspend() design | Only correct approach for interactive editors; async subprocess cannot hand terminal ownership |

**Deprecated/outdated:**
- Manual `termios` approach: was the only option before `App.suspend()`; do not use
- `click.edit()`: does not integrate with Textual's terminal lifecycle; use `App.suspend()` directly

---

## Open Questions

1. **Does SlashAutocomplete intercept Ctrl-G when the dropdown is visible?**
   - What we know: `textual_autocomplete.AutoComplete` wraps the `Input` and may handle key events
   - What's unclear: whether AutoComplete calls `event.stop()` on unrecognized keys
   - Recommendation: Verify empirically in Wave 0 by pressing Ctrl-G with a `/` typed in the input; if it doesn't fire, add `on_key` in `CommandInput` to forward the key

2. **Does `Input.value = multiline_text` work correctly with newlines?**
   - What we know: Textual's `Input` widget is a single-line widget; `\n` in the value is not rendered as newlines
   - What's unclear: whether the multiline content from the editor should be submitted immediately (like a "send and forget"), or stored verbatim in the input line
   - Recommendation: Store verbatim in `Input.value` per FOCUS-03; if there are newlines, the value will contain them and submit on Enter will pass the full multiline text to `UserSubmitted`. This matches the success criterion: "temp file content replaces CommandInput text exactly — including multiline."

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio 0.23 + pytest-textual-snapshot 0.4 |
| Config file | `packages/conductor-core/pyproject.toml` — `asyncio_mode = "auto"` |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_tui_external_editor.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOCUS-02 | Ctrl-G binding exists and is registered on ConductorApp | unit | `pytest tests/test_tui_external_editor.py::test_ctrl_g_binding_registered -x` | ❌ Wave 0 |
| FOCUS-02 | action_open_editor does nothing when input is disabled (replay mode) | unit | `pytest tests/test_tui_external_editor.py::test_ctrl_g_noop_during_replay -x` | ❌ Wave 0 |
| FOCUS-02 | SuspendNotSupported results in notify() not crash | unit | `pytest tests/test_tui_external_editor.py::test_ctrl_g_graceful_no_suspend -x` | ❌ Wave 0 |
| FOCUS-03 | EditorContentReady message exists and carries text | unit | `pytest tests/test_tui_external_editor.py::test_editor_content_ready_message -x` | ❌ Wave 0 |
| FOCUS-03 | on_editor_content_ready sets Input.value and focuses | unit | `pytest tests/test_tui_external_editor.py::test_on_editor_content_ready_fills_input -x` | ❌ Wave 0 |
| FOCUS-02/03 | Full flow: write tempfile, read back, populate input | integration | `pytest tests/test_tui_external_editor.py::test_editor_flow_with_mock_subprocess -x` | ❌ Wave 0 |

**Note:** `App.suspend()` cannot be tested with a real editor in pytest-asyncio — mock `subprocess.run` and patch `App.suspend()` as a no-op context manager. The integration test stubs both and verifies the data flow end-to-end.

### Sampling Rate

- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_tui_external_editor.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_tui_external_editor.py` — covers FOCUS-02, FOCUS-03 (6 tests listed above)
- [ ] No new fixtures needed — follows existing `App + run_test()` inline pattern from `test_tui_session_polish.py`

**IMPORTANT pattern constraint (from Phase 38 SUMMARY):** Keep `run_test()` inline in each test function — never in fixtures. This is required due to Textual contextvars/pytest-asyncio incompatibility (GitHub #4998).

---

## Sources

### Primary (HIGH confidence)

- Textual 8.1.1 installed at `.venv` — `App.suspend()`, `SuspendNotSupported`, `@work(thread=True)`, `Binding("ctrl+g", ...)`, `call_from_thread` all verified by direct inspection
- `packages/conductor-core/src/conductor/tui/app.py` — direct code review; current BINDINGS structure, `@work` usage, `action_quit`, disabled state management
- `packages/conductor-core/src/conductor/tui/widgets/command_input.py` — direct code review; `CommandInput` structure, `on_input_submitted` pattern for handler style
- `packages/conductor-core/src/conductor/tui/messages.py` — direct code review; all existing Message subclasses, constructor pattern
- `.planning/research/STACK.md` — verified `App.suspend()` pattern, `@work(thread=True)` constraint, `VISUAL`/`EDITOR`/vim fallback
- `.planning/research/ARCHITECTURE.md` — data flow diagram, component ownership rationale, anti-patterns
- `.planning/research/PITFALLS.md` — Pitfall 3 (suspend race), Pitfall 4 (terminal state after crash), Pitfall 9 (key routing conflict)
- `.planning/phases/38/38-01-SUMMARY.md` — confirmed Phase 38 precedent: `set_interval` over `animate()` for dot-path attributes; `run_test()` inline rule

### Secondary (MEDIUM confidence)

- [Textual GitHub Discussion #165 — Running shell apps / vim from Textual](https://github.com/Textualize/textual/discussions/165) — confirms `App.suspend()` + tempfile + `subprocess.run` pattern
- [Textual GitHub Issue #1093 — Launching subprocesses like Vim](https://github.com/Textualize/textual/issues/1093) — suspend race condition documented; fixed in PR #4064

### Tertiary (LOW confidence)

- None — all critical claims verified from primary sources above

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all APIs verified in installed Textual 8.1.1 and existing codebase
- Architecture: HIGH — pattern consistent with existing `StreamDone`/`TokensUpdated` cross-widget message bus; `App.suspend()` is the only documented approach
- Pitfalls: HIGH — drawn from project history (Phase 38 bug log) + Textual official issue tracker

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (Textual 8.x API is stable; `suspend()` has been stable since v0.48.0)
