# Phase 37: Slash Commands & Dashboard Coexistence - Research

**Researched:** 2026-03-11
**Domain:** Textual TUI autocomplete, uvicorn async coexistence, slash command dispatch
**Confidence:** HIGH

## Summary

Phase 37 delivers two independent features: (1) a slash command autocomplete popup in `CommandInput`, and (2) wiring `self._dashboard_port` in `ConductorApp.on_mount()` to launch the FastAPI/uvicorn dashboard server inside Textual's event loop.

For autocomplete, the best path is the `textual-autocomplete` third-party library (v4.0.6, `textual>=2.0`, maintained by a Textual core contributor). It provides fuzzy matching, keyboard navigation, and a `get_search_string()` override hook that cleanly supports the "/" prefix trigger pattern. An alternative is a hand-rolled `OptionList` overlay — feasible but requires significantly more boilerplate to replicate what textual-autocomplete already ships.

For dashboard coexistence, the architecture decision is already locked: `asyncio.create_task(server.serve())` inside `on_mount()`. The `_dashboard_port` attribute is stored in `__init__` and passed through the CLI, but `on_mount()` never starts the server. This phase simply wires the two lines. The exact `uvicorn.Server(config).serve()` pattern already exists in `commands/run.py` — copy it with `self._track_task()` for GC safety.

**Primary recommendation:** Use `textual-autocomplete` for slash autocomplete; wire `_dashboard_port` in `on_mount()` using the existing `_track_task` + `asyncio.create_task(server.serve())` pattern from `run.py`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| APRV-04 | User can type `/` to open a slash command autocomplete popup with fuzzy matching | textual-autocomplete v4.0.6 handles fuzzy matching + keyboard nav; get_search_string() override enables "/" prefix trigger; existing SLASH_COMMANDS dict in chat.py provides the canonical command list |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual-autocomplete | 4.0.6 | Autocomplete dropdown for Textual Input widgets | Written by Textual core contributor (darrenburns); compatible with textual>=2.0; ships fuzzy matching, keyboard nav, DropdownItem with prefix/suffix columns |
| textual (existing) | >=4.0 | TUI framework | Already in project |
| uvicorn (existing) | >=0.41 | ASGI server for dashboard | Already in project; `Server.serve()` API is the standard for running inside an event loop |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| textual.widgets.OptionList | built-in | Manual dropdown list | Alternative if textual-autocomplete is not added as dependency |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| textual-autocomplete | Hand-rolled OptionList overlay | Hand-rolling requires: `Input.Changed` handler, `add_option`/`clear_options` on every keystroke, CSS absolute positioning above input, Escape/Tab/Enter key binding in widget, focus management. ~80 lines vs ~10 lines with textual-autocomplete. |
| textual-autocomplete | Textual built-in `Input(suggester=...)` | Suggester shows inline ghost text (right-arrow to accept), not a dropdown list. Wrong UX for slash commands. |

**Installation:**
```bash
# Add to pyproject.toml dependencies
"textual-autocomplete>=4.0.6"
```

---

## Architecture Patterns

### Recommended Project Structure

No new files needed. Modifications only:

```
packages/conductor-core/src/conductor/
├── tui/
│   ├── app.py                      # Add _start_dashboard() in on_mount()
│   └── widgets/
│       └── command_input.py        # Add SlashAutocomplete widget; wire into compose()
├── cli/
│   └── chat.py                     # SLASH_COMMANDS dict — source of truth (read-only from TUI)
tests/
└── test_tui_slash_commands.py      # New test file for this phase
```

### Pattern 1: textual-autocomplete Slash Trigger

**What:** Subclass `AutoComplete` so the dropdown only appears when input starts with `/` and the search string is the text after `/`.

**When to use:** Any time you need prefix-gated autocomplete in a Textual Input.

**Example:**
```python
# Source: https://github.com/darrenburns/textual-autocomplete
from textual_autocomplete import AutoComplete, DropdownItem

class SlashAutocomplete(AutoComplete):
    """Autocomplete that activates only when input starts with '/'."""

    def get_candidates(self, state) -> list[DropdownItem]:
        from conductor.cli.chat import SLASH_COMMANDS
        return [
            DropdownItem(cmd, suffix=desc)
            for cmd, desc in SLASH_COMMANDS.items()
        ]

    def get_search_string(self, state) -> str:
        """Search only the text after '/'."""
        value = self.target_input.value
        if not value.startswith("/"):
            return "\x00"  # no-match sentinel — hides all candidates
        return value[1:]   # text after the slash

    def apply_completion(self, value: str, state) -> None:
        """Replace input value with the selected command."""
        self.target_input.value = value
        self.target_input.cursor_position = len(value)
```

**Integration in CommandInput.compose():**
```python
def compose(self) -> ComposeResult:
    inp = Input(placeholder="Type a message... (/ for commands)")
    yield inp
    yield SlashAutocomplete(inp)
```

### Pattern 2: Dashboard Server as asyncio.create_task in on_mount()

**What:** In `ConductorApp.on_mount()`, if `self._dashboard_port` is set, create a `uvicorn.Server` and schedule `server.serve()` as a tracked asyncio task.

**When to use:** Any time you need uvicorn running inside an existing event loop (not as the owner).

**Example:**
```python
# Source: pattern from packages/conductor-core/src/conductor/cli/commands/run.py lines 101-115
async def on_mount(self) -> None:
    # ... existing footer setup ...
    if self._dashboard_port is not None:
        await self._start_dashboard()

async def _start_dashboard(self) -> None:
    import uvicorn
    from conductor.dashboard.server import create_app
    from pathlib import Path

    state_path = Path(self._cwd) / ".conductor" / "state.json"
    dashboard_app = create_app(state_path)
    config = uvicorn.Config(
        dashboard_app,
        host="127.0.0.1",
        port=self._dashboard_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    self._track_task(asyncio.create_task(server.serve()))
    logger.info("Dashboard started on port %s", self._dashboard_port)
```

**Key:** Use `self._track_task()` (already in `app.py`) to prevent GC-collection of the task.

### Pattern 3: Slash Command Dispatch in ConductorApp

**What:** `on_user_submitted` checks if the submitted text starts with `/` and routes to a handler instead of the SDK streaming worker.

**When to use:** When CommandInput passes through all text including slash commands (which textual-autocomplete does — it populates the input, user still presses Enter).

**Example:**
```python
async def on_user_submitted(self, event: UserSubmitted) -> None:
    text = event.text
    if text.startswith("/"):
        await self._handle_slash_command(text)
        return
    # ... existing SDK streaming path ...

async def _handle_slash_command(self, text: str) -> None:
    cmd = text.split()[0].lower()
    if cmd == "/help":
        # Post to transcript
        ...
    elif cmd == "/exit":
        await self.action_quit()
    elif cmd == "/status":
        self._delegation_manager.print_status()  # or post to transcript
    elif cmd == "/summarize":
        ...  # forward to SDK with summarize prompt
    elif cmd == "/resume":
        ...  # call delegation_manager.resume_delegation()
    else:
        # Show "Unknown command" in transcript
        ...
```

### Anti-Patterns to Avoid

- **Adding autocomplete as ModalScreen:** SlashAutocomplete is a sibling widget inside CommandInput, not a modal. Modals block the entire screen; a dropdown overlay allows typing to continue.
- **Using `asyncio.run(server.serve())`:** Textual owns the event loop. `asyncio.run()` creates a new loop and crashes. Always use `asyncio.create_task()`.
- **Calling `uvicorn.run()`:** Same problem — `uvicorn.run()` calls `asyncio.run()` internally.
- **Forgetting `_track_task()`:** asyncio tasks created with `asyncio.create_task()` are GC-collected if no reference is held. The existing `_track_task` pattern in `app.py` prevents this.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fuzzy matching text | Custom substring/Levenshtein filter | textual-autocomplete's built-in fuzzy match | textual-autocomplete already handles partial match ranking, case insensitivity, and match highlighting |
| Keyboard navigation in dropdown | Custom key bindings for arrow/Tab/Enter | textual-autocomplete's built-in nav | Arrow keys, Tab, Enter, Escape all handled; focus management handled |
| Dropdown positioning | Custom CSS overlay positioning | textual-autocomplete's default layout | AutoComplete places itself relative to target Input automatically |

**Key insight:** For 5 static slash commands, the overhead of textual-autocomplete is minimal; fuzzy matching handles the case where a user types `/hlp` and still sees `/help`.

---

## Common Pitfalls

### Pitfall 1: `get_search_string` signature mismatch

**What goes wrong:** `AutoComplete.get_search_string()` in textual-autocomplete v4.x may take a `state: TargetState` parameter. Overriding with wrong signature causes a `TypeError` at runtime.

**Why it happens:** The v3.x and v4.x APIs differ; v4 introduced `TargetState`.

**How to avoid:** Check the signature in the installed version. If `state` is provided, use `state.value` instead of `self.target_input.value`. Write a test that actually exercises the autocomplete widget.

**Warning signs:** `TypeError: get_search_string() takes 1 positional argument but 2 were given` in test output.

### Pitfall 2: AutoComplete widget composed as sibling vs. child

**What goes wrong:** If `SlashAutocomplete(inp)` is yielded inside a `with Container()` block that clips overflow, the dropdown may be hidden.

**Why it happens:** textual-autocomplete renders the dropdown using CSS absolute positioning relative to the target Input. Clipping containers cut it off.

**How to avoid:** Yield `SlashAutocomplete` as a direct child of `CommandInput`, not nested inside another container. Keep the `CommandInput` CSS simple (no `overflow: hidden`).

**Warning signs:** Dropdown not visible at all when typing `/`.

### Pitfall 3: uvicorn.Server lifespan tasks and Textual shutdown

**What goes wrong:** When the user quits (`action_quit()`), the dashboard task is cancelled mid-serve. FastAPI lifespan's `stop_event` may never be set, leaving the state watcher task running.

**Why it happens:** `task.cancel()` sends CancelledError into `server.serve()`, which may not propagate cleanly through FastAPI's lifespan context manager.

**How to avoid:** The existing `action_quit()` already calls `asyncio.gather(*self._background_tasks, return_exceptions=True)` — this correctly swallows CancelledError. `return_exceptions=True` is critical. Verify in tests that shutdown doesn't hang.

**Warning signs:** `pytest` hangs after test teardown; `asyncio.TimeoutError` in test cleanup.

### Pitfall 4: Slash command dispatch vs. streaming path

**What goes wrong:** `/status` or `/help` gets sent to the Claude SDK instead of the local handler.

**Why it happens:** `on_user_submitted` currently sends all text to `_stream_response`. If the slash check is added in the wrong place (e.g., in `CommandInput` but not in `on_user_submitted`), the command bypasses the check.

**How to avoid:** The guard `if text.startswith("/"):` must be in `on_user_submitted` in `app.py`, before the `_stream_response` call. The CommandInput widget should not need to know about slash semantics — it just posts `UserSubmitted`.

### Pitfall 5: run_test() inline requirement

**What goes wrong:** Tests using `async with app.run_test()` in a pytest fixture (not inline) fail with `NoActiveAppError` or contextvars errors.

**Why it happens:** Textual uses Python contextvars for app context; pytest-asyncio's event loop isolation breaks the context when it's set in a fixture and consumed in a test.

**How to avoid:** Always inline `async with app.run_test() as pilot:` inside the test function body. This is the established pattern in all existing TUI tests (see `test_tui_approval.py` line 1 comment).

---

## Code Examples

Verified patterns from official sources and existing codebase:

### Slash command registry (existing — read-only reference)
```python
# Source: packages/conductor-core/src/conductor/cli/chat.py lines 45-51
SLASH_COMMANDS: dict[str, str] = {
    "/help": "Show all available slash commands",
    "/exit": "Exit the chat session and restore terminal",
    "/status": "Show active sub-agents (ID, task, elapsed time)",
    "/summarize": "Summarize conversation to free context space",
    "/resume": "Resume interrupted delegation from state.json",
}
```

### Track task pattern (existing — reuse)
```python
# Source: packages/conductor-core/src/conductor/tui/app.py lines 293-300
def _track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
    self._background_tasks.add(task)
    task.add_done_callback(self._background_tasks.discard)
    return task
```

### uvicorn asyncio.create_task pattern (from run.py — adapt for on_mount)
```python
# Source: packages/conductor-core/src/conductor/cli/commands/run.py lines 101-115
import uvicorn
from conductor.dashboard.server import create_app

dashboard_app = create_app(conductor_dir / "state.json", orchestrator=orchestrator)
config = uvicorn.Config(
    dashboard_app,
    host="127.0.0.1",
    port=dashboard_port,
    log_level="warning",
)
server = uvicorn.Server(config)
gather_extras.append(server.serve())
```

### textual-autocomplete basic usage
```python
# Source: https://github.com/darrenburns/textual-autocomplete
from textual_autocomplete import AutoComplete, DropdownItem

class SimpleApp(App):
    def compose(self) -> ComposeResult:
        text_input = Input(placeholder="Type here...")
        yield text_input
        yield AutoComplete(
            text_input,
            candidates=["Red", "Green", "Blue"]
        )
```

### Test pattern: verify autocomplete widget in tree
```python
# Pattern established in test_tui_shell.py and test_tui_approval.py
async def test_slash_autocomplete_in_widget_tree():
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.command_input import CommandInput

    app = ConductorApp()
    async with app.run_test() as pilot:
        widget = app.query_one(CommandInput)
        assert widget is not None
        # query for SlashAutocomplete inside CommandInput
        from textual_autocomplete import AutoComplete
        ac = widget.query_one(AutoComplete)
        assert ac is not None
```

### Test pattern: type "/" and see candidates
```python
async def test_slash_shows_candidates():
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.press("/")
        await pilot.pause()
        from textual_autocomplete import AutoComplete
        ac = app.query_one(AutoComplete)
        # Dropdown should be visible and have candidates
        assert ac.display is True
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-rolled autocomplete with OptionList | `textual-autocomplete` library | Library at v4.0.6 as of 2025 | Eliminates ~80 lines of manual filtering/positioning code |
| `uvicorn.run()` in a thread | `asyncio.create_task(server.serve())` | uvicorn added `Server.serve()` coroutine API | Clean coexistence with Textual's event loop |
| prompt_toolkit REPL's `/help` dispatch | Textual `on_user_submitted` dispatch | Phase 31 (this codebase) | All slash command handling moves to TUI app layer |

**Deprecated/outdated:**
- `uvicorn.run()`: Calls `asyncio.run()` internally — crashes if an event loop is already running (Textual). Never use in TUI context.
- `ChatSession._handle_slash_command()` in `chat.py`: The `ChatSession` class is the prompt_toolkit REPL path. The Textual TUI must implement its own equivalent dispatch in `ConductorApp`.

---

## Open Questions

1. **textual-autocomplete `get_search_string` exact signature in v4.x**
   - What we know: v4.0.6 is the current version; method exists; v3/v4 introduced `TargetState`
   - What's unclear: Exact signature of `get_search_string(self)` vs `get_search_string(self, state: TargetState)` without access to the installed package source
   - Recommendation: Read `AutoComplete` source in the virtual environment after installing the package; add a smoke test for the override signature early in implementation

2. **`/status` output surface in TUI**
   - What we know: In `chat.py`, `/status` calls `self._delegation_manager.print_status()` which prints to Rich console
   - What's unclear: Should TUI /status output go to the transcript pane as a user-visible cell, or to a separate log? `print_status()` currently uses Rich console which writes to stderr — not Textual-aware
   - Recommendation: Post a "status" message cell to the transcript using the existing transcript pattern; skip calling `print_status()` from TUI path

3. **`/summarize` in TUI context**
   - What we know: It requires an active SDK connection and sends a query to Claude
   - What's unclear: Should it reuse `_stream_response()` with a specific prompt, or have its own worker?
   - Recommendation: Simplest path — call `_stream_response()` with the summarize prompt text, same as a user message. Output flows naturally to the transcript.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 0.23 + pytest-textual-snapshot 0.4 |
| Config file | `packages/conductor-core/pyproject.toml` — `asyncio_mode = "auto"` |
| Quick run command | `pytest tests/test_tui_slash_commands.py -x -v` |
| Full suite command | `pytest --tb=short -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APRV-04 | Typing `/` opens autocomplete dropdown | unit | `pytest tests/test_tui_slash_commands.py::test_slash_shows_autocomplete -x` | ❌ Wave 0 |
| APRV-04 | Tab/Enter selects command from dropdown | unit | `pytest tests/test_tui_slash_commands.py::test_slash_select_command -x` | ❌ Wave 0 |
| APRV-04 | `/help` executes correctly | unit | `pytest tests/test_tui_slash_commands.py::test_slash_help_command -x` | ❌ Wave 0 |
| APRV-04 | `/exit` exits the app | unit | `pytest tests/test_tui_slash_commands.py::test_slash_exit_command -x` | ❌ Wave 0 |
| APRV-04 | `/status` does not send to SDK | unit | `pytest tests/test_tui_slash_commands.py::test_slash_status_no_sdk -x` | ❌ Wave 0 |
| SC-04 | `--dashboard-port` starts uvicorn in same process | integration | `pytest tests/test_tui_slash_commands.py::test_dashboard_starts_with_port -x` | ❌ Wave 0 |
| SC-05 | `conductor run` batch mode works without TUI | smoke | manual / existing `run` command tests | N/A |

### Sampling Rate
- **Per task commit:** `pytest tests/test_tui_slash_commands.py -x -v`
- **Per wave merge:** `pytest --tb=short -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui_slash_commands.py` — covers APRV-04 autocomplete, slash dispatch, and dashboard port wiring

*(Existing test infrastructure is fully in place — pytest config, asyncio_mode=auto, pilot pattern all established. Only the new test file is needed.)*

---

## Sources

### Primary (HIGH confidence)
- [Textual official docs — OptionList](https://textual.textualize.io/widgets/option_list/) — API, event handling
- [Textual official docs — Input widget](https://textual.textualize.io/widgets/input/) — Changed event, Suggester API
- Existing codebase — `app.py`, `command_input.py`, `modals.py`, `chat.py`, `commands/run.py` — all read directly

### Secondary (MEDIUM confidence)
- [textual-autocomplete PyPI page](https://pypi.org/project/textual-autocomplete/) — v4.0.6, textual>=2.0 dependency confirmed
- [textual-autocomplete GitHub](https://github.com/darrenburns/textual-autocomplete) — API overview, AutoComplete/DropdownItem patterns
- [uvicorn discussions — running inside event loop](https://github.com/Kludex/uvicorn/discussions/2457) — `Server.serve()` coroutine confirmed as standard approach

### Tertiary (LOW confidence)
- `get_search_string` exact v4.x signature — inferred from library documentation; verify against installed source before implementing override

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — textual-autocomplete v4.0.6 confirmed compatible with textual>=2.0; uvicorn `Server.serve()` pattern confirmed in official docs and existing codebase
- Architecture: HIGH — both patterns (slash autocomplete, dashboard task) have direct precedents in the existing codebase
- Pitfalls: HIGH — all pitfalls documented from existing Phase 31-36 decisions and established project-level Textual patterns
- `get_search_string` exact signature: LOW — requires verification against installed package source

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable library, 30-day window)
