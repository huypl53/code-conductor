---
phase: 32-static-tui-shell
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/src/conductor/tui/app.py
  - packages/conductor-core/src/conductor/tui/conductor.tcss
  - packages/conductor-core/src/conductor/tui/messages.py
  - packages/conductor-core/src/conductor/tui/widgets/__init__.py
  - packages/conductor-core/src/conductor/tui/widgets/transcript.py
  - packages/conductor-core/src/conductor/tui/widgets/command_input.py
  - packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py
  - packages/conductor-core/src/conductor/tui/widgets/status_footer.py
  - packages/conductor-core/tests/test_tui_shell.py
autonomous: true
requirements: [TRNS-01]

must_haves:
  truths:
    - "User can type a message and press Enter — a UserCell appears in the transcript with distinct styling"
    - "The transcript scrolls as cells are added and older cells remain visible by scrolling up"
    - "CommandInput clears after Enter is pressed and immediately accepts the next message"
    - "A status footer bar is visible at the bottom of the TUI screen"
    - "An AgentMonitorPane placeholder is visible on the right side of the screen"
  artifacts:
    - path: "packages/conductor-core/src/conductor/tui/widgets/transcript.py"
      provides: "TranscriptPane + UserCell + AssistantCell widgets"
      exports: ["TranscriptPane", "UserCell", "AssistantCell"]
    - path: "packages/conductor-core/src/conductor/tui/widgets/command_input.py"
      provides: "CommandInput widget — Input that posts UserSubmitted message on Enter"
      exports: ["CommandInput"]
    - path: "packages/conductor-core/src/conductor/tui/widgets/status_footer.py"
      provides: "StatusFooter widget — static docked bar with placeholder text"
      exports: ["StatusFooter"]
    - path: "packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py"
      provides: "AgentMonitorPane placeholder widget"
      exports: ["AgentMonitorPane"]
    - path: "packages/conductor-core/src/conductor/tui/conductor.tcss"
      provides: "Two-column CSS layout, cell styling, footer docking"
      contains: "TranscriptPane, AgentMonitorPane, CommandInput, StatusFooter"
    - path: "packages/conductor-core/tests/test_tui_shell.py"
      provides: "Headless tests verifying layout renders and CommandInput creates cells"
  key_links:
    - from: "CommandInput"
      to: "TranscriptPane"
      via: "UserSubmitted message posted on Input.Submitted"
      pattern: "on_command_input_user_submitted"
    - from: "ConductorApp.compose()"
      to: "all four layout widgets"
      via: "yield calls replacing placeholder Label"
      pattern: "yield TranscriptPane|AgentMonitorPane|CommandInput|StatusFooter"
    - from: "conductor.tcss"
      to: "StatusFooter"
      via: "dock: bottom CSS rule"
      pattern: "dock: bottom"
---

<objective>
Build the two-column Textual TUI layout with hard-coded content: TranscriptPane (left, scrollable),
AgentMonitorPane (right, placeholder), CommandInput (bottom input bar), and StatusFooter (docked bottom bar).
Typing a message and pressing Enter adds a UserCell to the transcript. No live SDK or state data yet.

Purpose: Verify the visual shell is correct with static content before connecting live data in Phase 33.
Layout bugs discovered here are cheap; layout bugs discovered after SDK streaming is wired are expensive.

Output:
  - conductor/tui/widgets/ package with four new widget modules
  - Updated ConductorApp.compose() replacing the Phase 31 placeholder label
  - Updated conductor.tcss with two-column layout rules and cell styling
  - Updated messages.py with UserSubmitted message type
  - Headless tests confirming layout renders and input creates cells
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/31/31-01-SUMMARY.md

# Existing Phase 31 files (must understand before modifying)
@packages/conductor-core/src/conductor/tui/app.py
@packages/conductor-core/src/conductor/tui/messages.py
@packages/conductor-core/src/conductor/tui/conductor.tcss
@packages/conductor-core/tests/test_tui_foundation.py

<interfaces>
<!-- Phase 31 contracts the executor MUST preserve and build on. -->

From packages/conductor-core/src/conductor/tui/app.py:
```python
class ConductorApp(App):
    CSS_PATH = Path(__file__).parent / "conductor.tcss"
    _background_tasks: set[asyncio.Task[Any]]

    def __init__(self, resume_session_id: str | None = None, dashboard_port: int | None = None) -> None: ...

    def compose(self) -> ComposeResult:
        # Phase 31: yields Label with id="placeholder-label"
        # Phase 32: REPLACE this with the four layout widgets

    async def on_mount(self) -> None: ...  # launch workers here in Phase 32+

    def _track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]: ...
    async def action_quit(self) -> None: ...  # cancels _background_tasks then exits
```

From packages/conductor-core/src/conductor/tui/messages.py:
```python
class TokenChunk(Message):      # streaming token from SDK (Phase 33)
class ToolActivity(Message):    # tool use line (Phase 33)
class StreamDone(Message):      # stream complete (Phase 33)
class TokensUpdated(Message):   # token usage data (Phase 33)
class DelegationStarted(Message):  # delegation began (Phase 35)
class DelegationComplete(Message): # delegation ended (Phase 35)
# Phase 32 MUST ADD: UserSubmitted message so CommandInput can post to app
```

From packages/conductor-core/tests/test_tui_foundation.py (test patterns to follow):
```python
# CRITICAL: Always use async with app.run_test() as pilot: INLINE in each test function.
# NEVER put run_test() in a pytest fixture — causes contextvars/pytest-asyncio incompatibility.
async def test_conductor_app_starts_headless():
    from conductor.tui.app import ConductorApp
    app = ConductorApp()
    async with app.run_test() as pilot:
        assert pilot.app is not None
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create widgets package and four layout widgets</name>
  <files>
    packages/conductor-core/src/conductor/tui/widgets/__init__.py
    packages/conductor-core/src/conductor/tui/widgets/transcript.py
    packages/conductor-core/src/conductor/tui/widgets/command_input.py
    packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py
    packages/conductor-core/src/conductor/tui/widgets/status_footer.py
    packages/conductor-core/src/conductor/tui/messages.py
  </files>
  <action>
Create the widgets/ package and four widget modules. Also add UserSubmitted to messages.py.

**messages.py — ADD UserSubmitted (keep all existing messages intact):**
```python
class UserSubmitted(Message):
    """User pressed Enter in CommandInput — text ready for transcript."""
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()
```

**widgets/__init__.py** — empty module marker with docstring:
```python
"""Conductor TUI widget library."""
```

**widgets/transcript.py:**

```python
"""TranscriptPane — scrollable conversation history with UserCell and AssistantCell."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
from textual.widget import Widget


class UserCell(Widget):
    """A single user message turn. Visually distinct from AssistantCell."""

    DEFAULT_CSS = """
    UserCell {
        background: $primary 10%;
        border-left: thick $primary;
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


class AssistantCell(Widget):
    """A single assistant message turn. Lighter background than UserCell."""

    DEFAULT_CSS = """
    AssistantCell {
        background: $surface;
        border-left: thick $accent;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    AssistantCell .cell-label {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static("Conductor", classes="cell-label")
        yield Static(self._text)


class TranscriptPane(VerticalScroll):
    """Scrollable vertical container for conversation cells.

    Receives UserSubmitted messages from CommandInput (via app message bus)
    and mounts a new UserCell. AssistantCell creation comes in Phase 33.
    """

    DEFAULT_CSS = """
    TranscriptPane {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        scrollbar-gutter: stable;
    }
    """

    def on_mount(self) -> None:
        """Mount a welcome cell so the pane is not blank on first launch."""
        self.mount(
            AssistantCell(
                "Welcome to Conductor. Type a message below to begin."
            )
        )

    async def add_user_message(self, text: str) -> None:
        """Mount a UserCell and scroll to bottom."""
        cell = UserCell(text)
        await self.mount(cell)
        self.scroll_end(animate=False)
```

**widgets/command_input.py:**

```python
"""CommandInput — single-line input bar that posts UserSubmitted on Enter."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input
from conductor.tui.messages import UserSubmitted


class CommandInput(Widget):
    """Input bar at the bottom of the screen.

    On Enter: posts UserSubmitted(text) to the app message bus, then clears.
    Phase 37 will add slash command autocomplete popup.
    """

    DEFAULT_CSS = """
    CommandInput {
        height: 3;
        padding: 0 1;
        background: $panel;
        border-top: solid $primary 30%;
    }
    CommandInput Input {
        background: $panel;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type a message... (Enter to send, Ctrl+C to quit)")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """User pressed Enter — post message to app bus, clear input."""
        text = event.value.strip()
        if not text:
            return
        self.post_message(UserSubmitted(text))
        event.input.clear()
        # Stop event from bubbling further — CommandInput owns this submission
        event.stop()
```

**widgets/agent_monitor.py:**

```python
"""AgentMonitorPane — right-side placeholder for agent status panels.

Phase 32: static placeholder only.
Phase 35: wired to StateWatchWorker — collapsible per-agent rows.
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class AgentMonitorPane(VerticalScroll):
    """Right-side panel showing agent status. Placeholder in Phase 32."""

    DEFAULT_CSS = """
    AgentMonitorPane {
        width: 30;
        height: 1fr;
        background: $panel;
        border-left: solid $primary 20%;
        padding: 1 1;
    }
    AgentMonitorPane #monitor-heading {
        color: $text-muted;
        text-style: bold;
        text-align: center;
        width: 1fr;
        padding-bottom: 1;
    }
    AgentMonitorPane #monitor-empty {
        color: $text-muted;
        text-align: center;
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Agents", id="monitor-heading")
        yield Static("No agents active", id="monitor-empty")
```

**widgets/status_footer.py:**

```python
"""StatusFooter — static docked bar at the bottom showing structural info.

Phase 32: static placeholder text only.
Phase 33: wired to TokensUpdated messages for live model/token display.
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class StatusFooter(Widget):
    """Bottom status bar. Docked via CSS dock: bottom.

    Phase 32 shows placeholder. Phase 33 wires live model/token data.
    """

    DEFAULT_CSS = """
    StatusFooter {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        layout: horizontal;
    }
    StatusFooter .footer-left {
        width: 1fr;
        color: $text;
    }
    StatusFooter .footer-right {
        color: $text-muted;
        text-align: right;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Conductor v2.0 | model: — | mode: interactive | tokens: —", classes="footer-left")
        yield Static("Ctrl+C to quit", classes="footer-right")
```
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && python -c "from conductor.tui.widgets.transcript import TranscriptPane, UserCell, AssistantCell; from conductor.tui.widgets.command_input import CommandInput; from conductor.tui.widgets.agent_monitor import AgentMonitorPane; from conductor.tui.widgets.status_footer import StatusFooter; from conductor.tui.messages import UserSubmitted; print('all imports OK')"</automated>
  </verify>
  <done>
    Five new files exist. All four widget classes import cleanly. UserSubmitted message is importable from conductor.tui.messages. No import errors.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wire ConductorApp layout and write headless tests</name>
  <files>
    packages/conductor-core/src/conductor/tui/app.py
    packages/conductor-core/src/conductor/tui/conductor.tcss
    packages/conductor-core/tests/test_tui_shell.py
  </files>
  <behavior>
    - Test 1: App composes without error and TranscriptPane is present in widget tree
    - Test 2: AgentMonitorPane is present in widget tree
    - Test 3: CommandInput is present in widget tree
    - Test 4: StatusFooter is present in widget tree
    - Test 5: Typing text and pressing Enter adds a UserCell to TranscriptPane
    - Test 6: CommandInput clears after Enter is pressed (input value is empty string)
    - Test 7: Welcome AssistantCell is present on startup (TranscriptPane on_mount)
    - Test 8: Submitting empty string (whitespace only) does NOT add a cell
  </behavior>
  <action>
**app.py — replace compose() body, keep everything else intact:**

Replace the Phase 31 placeholder `compose()` method with the four-widget layout.
Keep `__init__`, `on_mount`, `_track_task`, `action_quit` exactly as they are.

The new compose():
```python
def compose(self) -> ComposeResult:
    """Phase 32: two-column layout — TranscriptPane + AgentMonitorPane + CommandInput + StatusFooter."""
    from textual.containers import Horizontal
    from conductor.tui.widgets.transcript import TranscriptPane
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane
    from conductor.tui.widgets.command_input import CommandInput
    from conductor.tui.widgets.status_footer import StatusFooter

    with Horizontal(id="app-body"):
        yield TranscriptPane(id="transcript")
        yield AgentMonitorPane(id="agent-monitor")
    yield CommandInput(id="command-input")
    yield StatusFooter(id="status-footer")
```

Add a UserSubmitted handler on ConductorApp that routes to TranscriptPane:
```python
async def on_command_input_user_submitted(self, event: UserSubmitted) -> None:
    """Route user message to the transcript pane."""
    from conductor.tui.widgets.transcript import TranscriptPane
    from conductor.tui.messages import UserSubmitted
    pane = self.query_one(TranscriptPane)
    await pane.add_user_message(event.text)
```

Note: The import is `UserSubmitted` from messages. The handler name is derived from the
message namespace: `CommandInput` widget posts `UserSubmitted`, so Textual routes it as
`on_command_input_user_submitted` on ancestor widgets.

**conductor.tcss — replace entire file with Phase 32 layout:**

```css
/* Conductor TUI — Phase 32 two-column layout */

Screen {
    layers: base overlay;
    background: $surface;
}

#app-body {
    width: 1fr;
    /* Height accounts for CommandInput (3) and StatusFooter (1) */
    height: 1fr;
    layout: horizontal;
}

/* TranscriptPane takes remaining width after AgentMonitorPane */
/* TranscriptPane DEFAULT_CSS handles its own sizing */

/* CommandInput DEFAULT_CSS handles height: 3, dock is positional (not docked) */
/* StatusFooter DEFAULT_CSS handles dock: bottom, height: 1 */
```

**tests/test_tui_shell.py:**

```python
"""Phase 32: Static TUI Shell tests.

Tests that the two-column layout renders correctly in headless mode and
that CommandInput → TranscriptPane message routing works.

IMPORTANT: Keep run_test() inline in each test function — never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility — GitHub #4998)
"""
import pytest


async def test_transcript_pane_in_widget_tree():
    """TranscriptPane must be present after compose."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import TranscriptPane

    app = ConductorApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)
        assert pane is not None


async def test_agent_monitor_pane_in_widget_tree():
    """AgentMonitorPane must be present after compose."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane

    app = ConductorApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        assert pane is not None


async def test_command_input_in_widget_tree():
    """CommandInput must be present after compose."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.command_input import CommandInput

    app = ConductorApp()
    async with app.run_test() as pilot:
        widget = app.query_one(CommandInput)
        assert widget is not None


async def test_status_footer_in_widget_tree():
    """StatusFooter must be present after compose."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.status_footer import StatusFooter

    app = ConductorApp()
    async with app.run_test() as pilot:
        footer = app.query_one(StatusFooter)
        assert footer is not None


async def test_submit_message_adds_user_cell():
    """Typing text and pressing Enter adds a UserCell to TranscriptPane."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import TranscriptPane, UserCell

    app = ConductorApp()
    async with app.run_test() as pilot:
        # Focus the Input widget inside CommandInput, type, press Enter
        await pilot.click("#command-input Input")
        await pilot.press("h", "e", "l", "l", "o")
        await pilot.press("enter")
        await pilot.pause()

        pane = app.query_one(TranscriptPane)
        user_cells = pane.query(UserCell)
        assert len(user_cells) == 1
        # Verify cell contains the typed text
        assert "hello" in user_cells.first().query_one(".cell-label + Static").renderable


async def test_command_input_clears_after_submit():
    """Input value must be empty string after pressing Enter."""
    from conductor.tui.app import ConductorApp
    from textual.widgets import Input

    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.click("#command-input Input")
        await pilot.press("t", "e", "s", "t")
        await pilot.press("enter")
        await pilot.pause()

        input_widget = app.query_one("#command-input Input", Input)
        assert input_widget.value == ""


async def test_welcome_cell_present_on_startup():
    """TranscriptPane must show a welcome AssistantCell on mount."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import TranscriptPane, AssistantCell

    app = ConductorApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)
        cells = pane.query(AssistantCell)
        assert len(cells) >= 1


async def test_empty_submit_does_not_add_cell():
    """Pressing Enter with only whitespace must NOT add a UserCell."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import TranscriptPane, UserCell

    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.click("#command-input Input")
        await pilot.press("space", "space")
        await pilot.press("enter")
        await pilot.pause()

        pane = app.query_one(TranscriptPane)
        user_cells = pane.query(UserCell)
        assert len(user_cells) == 0


async def test_placeholder_label_removed():
    """Phase 31 placeholder Label must NOT be present in Phase 32 layout."""
    from conductor.tui.app import ConductorApp
    from textual.widgets import Label

    app = ConductorApp()
    async with app.run_test() as pilot:
        labels = app.query("#placeholder-label")
        assert len(labels) == 0
```

**Run tests:** After writing all files, run:
```
cd /home/huypham/code/digest/claude-auto/packages/conductor-core && python -m pytest tests/test_tui_shell.py -v
```

If any test fails, fix the implementation (not the test) and re-run. The RED→GREEN cycle:
1. Write tests (they will fail if app.py still has placeholder label)
2. Update app.py compose() to the four-widget layout
3. Run tests — all 8 must pass
4. Run full suite to confirm no regressions: `python -m pytest --tb=short -q`
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && python -m pytest tests/test_tui_shell.py tests/test_tui_foundation.py -v --tb=short</automated>
  </verify>
  <done>
    All 8 new tests in test_tui_shell.py pass. All 7 Phase 31 tests in test_tui_foundation.py still pass.
    Full suite shows no regressions (585+ tests passing, no failures).
    Running `conductor` (or `python -m conductor`) launches the two-column TUI layout — not the Phase 31 placeholder label.
  </done>
</task>

</tasks>

<verification>
After both tasks complete:

1. Widget imports: `python -c "from conductor.tui.widgets.transcript import TranscriptPane, UserCell, AssistantCell"` — no error
2. Message bus: `python -c "from conductor.tui.messages import UserSubmitted"` — no error
3. Shell layout test: `cd packages/conductor-core && python -m pytest tests/test_tui_shell.py -v` — 8/8 pass
4. Foundation regression: `python -m pytest tests/test_tui_foundation.py -v` — 7/7 pass
5. Full suite: `python -m pytest --tb=short -q` — 593+ pass, 0 failures

Manual check (requires terminal):
- Run `conductor` — terminal should switch to alternate screen with two-column layout visible
- Left side: wider transcript pane with "Welcome to Conductor" assistant cell
- Right side: narrow panel with "Agents / No agents active" placeholder text
- Bottom input: text input bar with placeholder hint text
- Bottom status: 1-line status bar with "Conductor v2.0 | model: — | ..." text
- Type "hello" + Enter: UserCell appears in transcript with blue-accented left border
- Input clears after Enter
- Ctrl+C exits cleanly
</verification>

<success_criteria>
Phase 32 is complete when:
1. User can type a message and press Enter — a UserCell appears in TranscriptPane with visually distinct styling (left border, "You" label) different from the AssistantCell (accent border, "Conductor" label)
2. The transcript scrolls as cells are added and older cells remain visible on scroll-up (VerticalScroll container behavior)
3. CommandInput clears after submission and immediately accepts the next message
4. A status footer bar is visible at the bottom of the screen showing placeholder model/mode/token info
5. AgentMonitorPane placeholder is visible on the right side showing "No agents active"
6. All 8 new tests pass, all 7 Phase 31 tests still pass, full suite shows zero regressions
</success_criteria>

<output>
After completion, create `.planning/phases/32/32-01-SUMMARY.md` following the template at
`@/home/huypham/.claude/get-shit-done/templates/summary.md`.

Key fields to capture:
- files_created: all new widget modules + test file
- files_modified: app.py, conductor.tcss, messages.py
- decisions: any CSS layout choices, widget hierarchy choices, Textual API choices made during execution
- metrics: test count (target: 593+ passing), files created/modified
</output>
