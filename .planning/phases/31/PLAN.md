---
phase: 31-tui-foundation
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/pyproject.toml
  - packages/conductor-core/src/conductor/tui/__init__.py
  - packages/conductor-core/src/conductor/tui/app.py
  - packages/conductor-core/src/conductor/tui/messages.py
  - packages/conductor-core/src/conductor/tui/conductor.tcss
  - packages/conductor-core/src/conductor/cli/__init__.py
  - packages/conductor-core/src/conductor/cli/delegation.py
  - packages/conductor-core/tests/test_tui_foundation.py
autonomous: true
requirements:
  - TUIF-01
  - TUIF-02
  - TUIF-03
  - TUIF-04

must_haves:
  truths:
    - "Running `conductor` switches the terminal to alternate screen mode (Textual TUI launches)"
    - "No prompt_toolkit import is executed during TUI lifetime — grep and runtime audit confirm zero imports"
    - "SDK client, orchestrator delegation, and uvicorn are launched as workers/tasks inside ConductorApp.on_mount — no competing asyncio.run() exists"
    - "A pytest test using run_test() pilot can assert ConductorApp starts without error in headless mode"
    - "DelegationManager._status_updater and _clear_status_lines are removed — no ANSI cursor codes emitted during TUI lifetime"
  artifacts:
    - path: "packages/conductor-core/src/conductor/tui/__init__.py"
      provides: "tui module marker"
    - path: "packages/conductor-core/src/conductor/tui/app.py"
      provides: "ConductorApp Textual App root"
      exports: ["ConductorApp"]
    - path: "packages/conductor-core/src/conductor/tui/messages.py"
      provides: "Custom Textual message types (internal event bus)"
      exports: ["TokenChunk", "ToolActivity", "StreamDone", "TokensUpdated", "DelegationStarted", "DelegationComplete"]
    - path: "packages/conductor-core/src/conductor/tui/conductor.tcss"
      provides: "Textual CSS layout skeleton"
    - path: "packages/conductor-core/tests/test_tui_foundation.py"
      provides: "Headless pytest tests via run_test() pilot"
  key_links:
    - from: "packages/conductor-core/src/conductor/cli/__init__.py"
      to: "packages/conductor-core/src/conductor/tui/app.py"
      via: "ConductorApp(...).run() replaces asyncio.run(_run_chat_with_dashboard(...))"
      pattern: "ConductorApp.*\\.run\\(\\)"
    - from: "packages/conductor-core/src/conductor/tui/app.py"
      to: "packages/conductor-core/src/conductor/cli/delegation.py"
      via: "DelegationManager constructed inside ConductorApp with input_fn=None (escalation via modal, Phase 36)"
      pattern: "DelegationManager"
---

<objective>
Establish Textual as the sole event loop owner for the interactive `conductor` command. ConductorApp replaces the prompt_toolkit ChatSession, delegation.py is stripped of ANSI terminal manipulation, and the test infrastructure for headless Textual testing is established. Phase 31 delivers the load-bearing architecture that all subsequent TUI phases depend on.

Purpose: Three existing patterns conflict fatally with Textual — asyncio.run() cohabitation, Rich Console.print() during TUI lifetime, and prompt_toolkit terminal ownership. All three must be eliminated before any widget work begins. Failure to settle event loop ownership here produces cascading runtime errors that are expensive to unwind later.

Output:
- `conductor/tui/` module with ConductorApp, messages.py, skeleton CSS
- Modified `cli/__init__.py` — ConductorApp.run() replaces asyncio.run()
- Modified `cli/delegation.py` — _status_updater and _clear_status_lines removed, Console.print calls removed from delegation lifecycle (logging.info only)
- Test file with headless pilot confirming app starts without error
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md

<interfaces>
<!-- Key existing contracts the executor needs. Extracted from codebase. -->

From packages/conductor-core/src/conductor/cli/__init__.py (BEING MODIFIED):
```python
# Current entry point — asyncio.run() must be replaced with ConductorApp.run()
@app.callback(invoke_without_command=True)
def _default_callback(ctx, resume, resume_id, dashboard_port) -> None:
    # Currently calls: asyncio.run(_run_chat_with_dashboard(session_id, dashboard_port))
    # Must become:    ConductorApp(resume_session_id=session_id, dashboard_port=dashboard_port).run()
```

From packages/conductor-core/src/conductor/cli/delegation.py (BEING MODIFIED):
```python
class DelegationManager:
    def __init__(self, console, repo_path, dashboard_url, input_fn, build_command) -> None:
        self._console = console          # REMOVE Console.print() calls from delegation lifecycle
        self._status_task: asyncio.Task  # keep (used for cancellation)
        self._escalation_task: asyncio.Task  # keep

    async def _status_updater(self, run) -> None:
        # DELETE THIS METHOD ENTIRELY — replaced by StateWatchWorker in Phase 35
        ...

    def _clear_status_lines(self) -> None:
        # DELETE THIS METHOD ENTIRELY — ANSI cursor codes corrupt Textual renderer
        ...

    def _print_live_status(self, run) -> None:
        # DELETE THIS METHOD ENTIRELY
        ...
```

From packages/conductor-core/pyproject.toml (BEING MODIFIED):
```toml
dependencies = [
  "prompt-toolkit>=3.0.52",  # KEEP (still used by conductor run batch mode — do NOT remove)
  # ADD: "textual>=4.0"
  # ADD: "pytest-textual-snapshot>=0.4" in dev group
]
```

From packages/conductor-core/src/conductor/cli/delegation.py (MCP wiring kept intact):
```python
def create_delegation_mcp_server(manager: DelegationManager) -> Any:
    # KEEP UNCHANGED — this wires the conductor_delegate MCP tool
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add textual dependency, create tui/ module scaffold and messages.py</name>
  <files>
    packages/conductor-core/pyproject.toml
    packages/conductor-core/src/conductor/tui/__init__.py
    packages/conductor-core/src/conductor/tui/messages.py
    packages/conductor-core/src/conductor/tui/conductor.tcss
  </files>
  <action>
Add `textual>=4.0` to `[project].dependencies` in pyproject.toml. Also add `pytest-textual-snapshot>=0.4` to `[dependency-groups].dev`. Do NOT remove `prompt-toolkit` — it is still used by `conductor run` batch-mode (`cli/input_loop.py`).

Create `packages/conductor-core/src/conductor/tui/__init__.py` as an empty module marker (just a docstring: `"""Textual TUI for Conductor v2.0."""`).

Create `packages/conductor-core/src/conductor/tui/messages.py` with all custom Textual message types that form the internal event bus. These prevent circular imports and make the bus explicit. Import from `textual.message import Message`.

Define these message classes (each as a dataclass-style Message subclass):

```python
from textual.message import Message

class TokenChunk(Message):
    """A streaming text token from the SDK."""
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()

class ToolActivity(Message):
    """A tool use event formatted as a human-readable activity line."""
    def __init__(self, activity_line: str) -> None:
        self.activity_line = activity_line
        super().__init__()

class StreamDone(Message):
    """Streaming response has completed — active cell becomes immutable."""

class TokensUpdated(Message):
    """SDK result message with token usage data."""
    def __init__(self, usage: dict) -> None:
        self.usage = usage
        super().__init__()

class DelegationStarted(Message):
    """A conductor_delegate tool call has begun."""
    def __init__(self, task_description: str) -> None:
        self.task_description = task_description
        super().__init__()

class DelegationComplete(Message):
    """Delegation finished (success or error)."""
    def __init__(self, summary: str, error: bool = False) -> None:
        self.summary = summary
        self.error = error
        super().__init__()
```

Create `packages/conductor-core/src/conductor/tui/conductor.tcss` with a skeleton CSS layout. This is the layout foundation — widgets will be sparse until Phase 32. Write minimal CSS:

```css
/* Conductor TUI — layout skeleton for Phase 31 */
/* Full layout established in Phase 32 */

Screen {
    layers: base overlay;
    background: $surface;
}

#app-body {
    width: 1fr;
    height: 1fr;
}

#placeholder-label {
    content-align: center middle;
    width: 1fr;
    height: 1fr;
    color: $text-muted;
}
```
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv pip show textual 2>/dev/null | grep -q "Name: textual" || uv add textual && python -c "from conductor.tui.messages import TokenChunk, ToolActivity, StreamDone, TokensUpdated, DelegationStarted, DelegationComplete; print('messages ok')"</automated>
  </verify>
  <done>
    - `pyproject.toml` has `textual>=4.0` in dependencies and `pytest-textual-snapshot>=0.4` in dev group
    - `conductor/tui/__init__.py` exists
    - `from conductor.tui.messages import TokenChunk` succeeds without error
    - `conductor.tcss` exists with Screen layout block
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create ConductorApp, strip delegation.py of ANSI/Console pollution, rewire CLI entry point</name>
  <files>
    packages/conductor-core/src/conductor/tui/app.py
    packages/conductor-core/src/conductor/cli/delegation.py
    packages/conductor-core/src/conductor/cli/__init__.py
    packages/conductor-core/tests/test_tui_foundation.py
  </files>
  <behavior>
    - Test 1: `async with ConductorApp().run_test() as pilot:` — app starts without RuntimeError, NoActiveAppError, or any import from prompt_toolkit being triggered
    - Test 2: ConductorApp exits cleanly when pilot calls `app.exit()` — no terminal corruption
    - Test 3: Importing `conductor.tui.app` does not import `prompt_toolkit` anywhere in the import chain
    - Test 4: `DelegationManager` constructed without a console argument no longer requires a Rich Console — it accepts `console=None` and skips Console.print() calls in the lifecycle
    - Test 5: `DelegationManager` has no `_status_updater`, `_clear_status_lines`, or `_print_live_status` methods
  </behavior>
  <action>
**Step A — Write the test file FIRST (TDD red phase):**

Create `packages/conductor-core/tests/test_tui_foundation.py`:

```python
"""Phase 31: TUI Foundation tests.

Tests for ConductorApp headless launch, prompt_toolkit isolation,
and delegation.py ANSI cleanup.

IMPORTANT: Keep run_test() inline in each test function — never in fixtures.
This avoids Textual's contextvars/pytest-asyncio incompatibility (GitHub #4998).
"""
import importlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Test 1: App starts in headless mode without error
# ---------------------------------------------------------------------------

async def test_conductor_app_starts_headless():
    """ConductorApp must start without RuntimeError or NoActiveAppError."""
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    async with app.run_test() as pilot:
        assert pilot.app is not None
        assert not pilot.app._closed


# ---------------------------------------------------------------------------
# Test 2: App exits cleanly
# ---------------------------------------------------------------------------

async def test_conductor_app_exits_cleanly():
    """App.exit() must not raise or leave terminal in broken state."""
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.app.action_quit()
    # No exception = pass


# ---------------------------------------------------------------------------
# Test 3: prompt_toolkit not imported in tui code path
# ---------------------------------------------------------------------------

def test_no_prompt_toolkit_in_tui_imports():
    """Importing conductor.tui.app must not trigger any prompt_toolkit import."""
    # Unload any cached module to get a clean import trace
    mods_before = set(sys.modules.keys())

    # Force reimport
    if "conductor.tui.app" in sys.modules:
        del sys.modules["conductor.tui.app"]

    import conductor.tui.app  # noqa: F401

    new_mods = set(sys.modules.keys()) - mods_before
    pt_mods = [m for m in new_mods if "prompt_toolkit" in m]
    assert pt_mods == [], f"prompt_toolkit imported via tui.app: {pt_mods}"


# ---------------------------------------------------------------------------
# Test 4 & 5: DelegationManager cleanup
# ---------------------------------------------------------------------------

def test_delegation_manager_no_status_updater():
    """DelegationManager must not have _status_updater or _clear_status_lines."""
    from conductor.cli.delegation import DelegationManager

    dm = DelegationManager(repo_path="/tmp")
    assert not hasattr(dm, "_status_updater"), "_status_updater was not removed"
    assert not hasattr(dm, "_clear_status_lines"), "_clear_status_lines was not removed"
    assert not hasattr(dm, "_print_live_status"), "_print_live_status was not removed"


def test_delegation_manager_no_console_required():
    """DelegationManager must be constructable without a Rich Console argument."""
    from conductor.cli.delegation import DelegationManager

    # Must not raise even without console
    dm = DelegationManager(repo_path="/tmp")
    assert dm is not None
```

Run tests — they MUST fail at this point (RED). Then implement:

**Step B — Create `packages/conductor-core/src/conductor/tui/app.py`:**

```python
"""ConductorApp — Textual App root for Conductor v2.0.

Phase 31: Minimal skeleton — event loop ownership, lifecycle, background task
          reference tracking. No widgets beyond a placeholder label.
Phase 32: Full two-column layout (TranscriptPane, CommandInput, StatusFooter,
          AgentMonitorPane) replaces the placeholder.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.widgets import Label

logger = logging.getLogger("conductor.tui")


class ConductorApp(App):
    """Textual application root.

    Owns the asyncio event loop. All async subsystems (SDK streaming,
    uvicorn dashboard server, orchestrator delegation) launch as workers
    or asyncio tasks inside on_mount() — never alongside this app.

    CSS_PATH references the Textual CSS layout file.
    """

    CSS_PATH = Path(__file__).parent / "conductor.tcss"

    # Background task reference store (Pitfall 5: GC-collected tasks die silently)
    _background_tasks: set[asyncio.Task[Any]]

    def __init__(
        self,
        resume_session_id: str | None = None,
        dashboard_port: int | None = None,
    ) -> None:
        super().__init__()
        self._resume_session_id = resume_session_id
        self._dashboard_port = dashboard_port
        self._background_tasks = set()

    def compose(self) -> ComposeResult:
        """Phase 31: placeholder label — replaced by full layout in Phase 32."""
        yield Label(
            "Conductor TUI — Phase 31 Foundation (layout coming in Phase 32)",
            id="placeholder-label",
        )

    async def on_mount(self) -> None:
        """Launch all async subsystems on Textual's event loop.

        Pattern: asyncio.create_task() for raw tasks (stored in
        _background_tasks to prevent GC); self.run_worker() for Textual
        @work coroutines (WorkerManager holds references automatically).
        """
        # Phase 32: mount SDKStreamWorker, StateWatchWorker here
        # Phase 37: mount DashboardWorker here if dashboard_port is set
        logger.debug(
            "ConductorApp mounted. resume_session_id=%s, dashboard_port=%s",
            self._resume_session_id,
            self._dashboard_port,
        )

    def _track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Store a background task reference to prevent GC collection.

        Usage:
            t = self._track_task(asyncio.create_task(my_coro()))
        """
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def action_quit(self) -> None:
        """Clean exit — cancels background tasks, then calls app.exit()."""
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self.exit()
```

**Step C — Strip `packages/conductor-core/src/conductor/cli/delegation.py`:**

Remove these methods entirely from DelegationManager:
- `_status_updater(self, run)` — Phase 35 replaces this with StateWatchWorker
- `_print_live_status(self, run)` — called only by _status_updater
- `_clear_status_lines(self)` — ANSI cursor codes that corrupt Textual renderer

Remove the `self._last_status_line_count = 0` init line (no longer needed).

Remove `self._console = console` and the `console` parameter from `__init__` — DelegationManager must not hold a Rich Console reference. **Do not remove console parameter from the constructor signature yet** — keep it as an optional parameter with `console=None` default so existing unit tests (`test_delegation.py`) that pass a Console do not break. Simply stop using `self._console` inside delegation lifecycle methods (handle_delegate, resume_delegation). Replace the Console.print() announcement lines with `logger.info(...)` calls.

Specifically in `handle_delegate`:
- Replace `self._console.print(f"\n[bold magenta]Delegating to team...[/bold magenta]...")` with `logger.info("Delegating task to team: %s", task)`
- Replace `self._console.print(f"\n[bold green]Delegation complete[/bold green] ({elapsed:.1f}s)")` with `logger.info("Delegation complete in %.1fs", elapsed)`
- Replace the error console.print with `logger.error("Delegation failed: %s", exc)`
- Remove all `self._clear_status_lines()` calls (method no longer exists)
- Remove `self._status_task = asyncio.create_task(self._status_updater(run))` — status updates are now handled by Textual widgets

In `resume_delegation`:
- Replace all `self._console.print(...)` calls with `logger.info(...)` equivalents
- Remove `self._status_task = asyncio.create_task(self._status_updater(run))` line
- Remove the escalation_task line for resume too — escalation bridge wired in Phase 36

Also remove `self._last_status_line_count` from `__init__`.

Keep intact (do NOT modify):
- `_escalation_listener`, `_collect_escalation_input` — Phase 36 rewires these
- `_cancel_background_tasks`
- `print_status` — still needed for /status slash command (uses Rich Table via Console but only when called explicitly, not during TUI lifetime)
- `create_delegate_tool`, `create_delegation_mcp_server`
- The `_human_out`, `_human_in`, escalation queue logic

**Step D — Rewire `packages/conductor-core/src/conductor/cli/__init__.py`:**

Replace the `_default_callback` function's body. Remove `asyncio.run(_run_chat_with_dashboard(...))`. Replace with `ConductorApp(resume_session_id=session_id, dashboard_port=dashboard_port).run()`.

Remove the `_run_chat_with_dashboard` async function entirely (its functionality moves to `ConductorApp.on_mount` incrementally across Phases 32-37).

Keep the `pick_session()` import for the `--resume` flag. Keep all typer options unchanged.

The modified callback becomes:
```python
@app.callback(invoke_without_command=True)
def _default_callback(ctx, resume, resume_id, dashboard_port) -> None:
    """Launch interactive TUI when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return

    from conductor.cli.chat import pick_session
    from conductor.tui.app import ConductorApp

    session_id = resume_id
    if resume and session_id is None:
        session_id = pick_session()
        if session_id is None:
            return

    ConductorApp(resume_session_id=session_id, dashboard_port=dashboard_port).run()
```

Remove the now-unused `_console = Console(highlight=False)` module-level variable.
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && python -m pytest tests/test_tui_foundation.py -v --tb=short 2>&1 | tail -30</automated>
  </verify>
  <done>
    - All 5 tests in test_tui_foundation.py pass (GREEN)
    - `python -c "from conductor.tui.app import ConductorApp"` succeeds without error
    - `grep -r "prompt_toolkit" src/conductor/tui/` returns no results
    - `grep -r "_status_updater\|_clear_status_lines\|_print_live_status" src/conductor/cli/delegation.py` returns no results
    - Existing test suite (excluding test_tui_foundation.py) still passes: `python -m pytest tests/ -v --ignore=tests/test_tui_foundation.py -x --tb=short 2>&1 | tail -20`
  </done>
</task>

<task type="auto">
  <name>Task 3: Runtime audit and integration smoke test</name>
  <files>
    packages/conductor-core/tests/test_tui_foundation.py
  </files>
  <action>
Add two additional tests to `test_tui_foundation.py` to cover the runtime audit requirements from the phase success criteria.

**Test 6 — No asyncio.run() cohabitation:**

Verify that `conductor/cli/__init__.py` does NOT contain any remaining `asyncio.run(` call. Use a static code check:

```python
def test_no_asyncio_run_in_cli_entry():
    """cli/__init__.py must not call asyncio.run() — ConductorApp.run() is the entry point."""
    import inspect
    import conductor.cli as cli_module

    source = inspect.getsource(cli_module)
    assert "asyncio.run(" not in source, (
        "asyncio.run() found in cli/__init__.py — must use ConductorApp.run() instead"
    )
```

**Test 7 — Background task tracking convention:**

Verify ConductorApp has the `_track_task` helper and `_background_tasks` set:

```python
def test_conductor_app_background_task_tracking():
    """ConductorApp must provide _track_task() and _background_tasks set."""
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    assert hasattr(app, "_background_tasks"), "Missing _background_tasks set"
    assert hasattr(app, "_track_task"), "Missing _track_task() helper"
    assert callable(app._track_task)
```

**Test 8 — Full suite integration (existing tests still pass):**

Add a comment block (not a test function) that documents the manual integration check:

```python
# ---------------------------------------------------------------------------
# MANUAL INTEGRATION CHECK (not automated — requires a terminal)
# ---------------------------------------------------------------------------
# 1. Run: cd packages/conductor-core && conductor
# 2. Expected: terminal switches to Textual alternate screen mode
# 3. Expected: placeholder label visible ("Conductor TUI — Phase 31 Foundation")
# 4. Expected: Ctrl+C exits cleanly and restores the terminal
# 5. Run: grep -r "prompt_toolkit" src/conductor/tui/ — must return zero results
# ---------------------------------------------------------------------------
```

Run the full test suite to confirm no regressions:
```bash
cd /home/huypham/code/digest/claude-auto/packages/conductor-core
python -m pytest tests/ -v --tb=short 2>&1 | tail -40
```

If `test_delegation.py` or `test_phase22_visibility.py` fail because they pass a `Console` object to `DelegationManager`, update those tests to construct DelegationManager with `console=None` (or simply remove the console kwarg if tests were passing it).

If `test_chat.py` fails because it imports ChatSession (which imports prompt_toolkit), that is expected — ChatSession is NOT removed (it remains for potential fallback use and has its own tests). The key requirement is that prompt_toolkit is NOT imported through the TUI code path, not that it is removed from the package entirely.
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && python -m pytest tests/test_tui_foundation.py -v --tb=short 2>&1 | tail -20 && python -m pytest tests/ -v --tb=short 2>&1 | grep -E "passed|failed|error" | tail -5</automated>
  </verify>
  <done>
    - All tests in test_tui_foundation.py pass (7 automated tests total)
    - Full test suite shows no new failures compared to pre-phase baseline
    - `python -c "import conductor.cli; print('cli ok')"` succeeds
    - `python -c "from conductor.tui.app import ConductorApp; print('tui ok')"` succeeds
  </done>
</task>

</tasks>

<verification>
Phase 31 is complete when ALL of the following are true:

1. **TUIF-01** — Running `conductor` (no subcommand) calls `ConductorApp(...).run()` and switches the terminal to Textual alternate screen mode. Verify by running the command interactively and confirming the terminal changes to full-screen mode.

2. **TUIF-02** — All async subsystems are wired into `ConductorApp.on_mount()`. Currently the skeleton on_mount is a placeholder — uvicorn, SDK, and state watcher are registered in later phases. The key constraint verified here is that NO `asyncio.run()` call exists in the TUI startup path: `grep "asyncio.run(" packages/conductor-core/src/conductor/cli/__init__.py` returns no results.

3. **TUIF-03** — `grep -r "from prompt_toolkit\|import prompt_toolkit" packages/conductor-core/src/conductor/tui/` returns zero results. `grep -r "from prompt_toolkit\|import prompt_toolkit" packages/conductor-core/src/conductor/cli/__init__.py` returns zero results.

4. **TUIF-04** — `python -m pytest tests/test_tui_foundation.py -v` shows all 7 tests passing with no errors.

5. **No regressions** — `python -m pytest tests/ -v` shows the same number of passing tests as before Phase 31 (or more). If delegation tests fail due to Console removal, they must be fixed as part of this phase.
</verification>

<success_criteria>
- `conductor/tui/__init__.py`, `conductor/tui/app.py`, `conductor/tui/messages.py`, `conductor/tui/conductor.tcss` exist and import cleanly
- `ConductorApp().run_test()` pilot succeeds in 7 headless tests
- Zero `prompt_toolkit` imports in any code path reachable from `ConductorApp` or `cli/__init__.py` (TUI entry)
- `delegation.py` has no `_status_updater`, `_clear_status_lines`, `_print_live_status` methods
- `cli/__init__.py` calls `ConductorApp(...).run()` instead of `asyncio.run(...)`
- Full test suite passes without regressions
</success_criteria>

<output>
After completion, create `.planning/phases/31/31-01-SUMMARY.md` with:
- What was built (files created/modified with brief description)
- Key decisions made (e.g., console=None kept for backward compat, pick_session() kept for --resume)
- Any deviations from this plan and why
- Pitfalls encountered and how they were resolved
- Test results (pass/fail counts)
</output>
