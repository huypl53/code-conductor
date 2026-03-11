"""Phase 42: Ctrl-G external editor tests.

Tests that ConductorApp suspends the TUI, opens an external editor,
and fills CommandInput with the edited content.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""
from unittest.mock import MagicMock, patch

import pytest


# -- Test 1: Binding registration ---------------------------------------------


async def test_ctrl_g_binding_registered():
    """ConductorApp.BINDINGS contains a ctrl+g binding for open_editor."""
    from conductor.tui.app import ConductorApp

    matches = [b for b in ConductorApp.BINDINGS if hasattr(b, "key") and b.key == "ctrl+g"]
    assert len(matches) == 1, f"Expected exactly 1 ctrl+g binding, found {len(matches)}"
    assert matches[0].action == "open_editor"


# -- Test 2: EditorContentReady message ----------------------------------------


async def test_editor_content_ready_message():
    """EditorContentReady can be instantiated with a text argument and is a Message subclass."""
    from textual.message import Message

    from conductor.tui.messages import EditorContentReady

    msg = EditorContentReady("hello world")
    assert msg.text == "hello world"
    assert isinstance(msg, Message)


# -- Test 3: Ctrl-G noop during replay ----------------------------------------


async def test_ctrl_g_noop_during_replay():
    """When CommandInput is disabled, action_open_editor returns immediately without opening editor."""
    from textual.app import App, ComposeResult
    from textual.widgets import Input

    from conductor.tui.widgets.command_input import CommandInput

    class ReplayTestApp(App):
        BINDINGS = []
        editor_messages = []

        def compose(self) -> ComposeResult:
            yield CommandInput(id="command-input")

        def on_editor_content_ready(self, event):
            self.editor_messages.append(event)

    app = ReplayTestApp()
    async with app.run_test() as pilot:
        cmd = app.query_one(CommandInput)
        cmd.disabled = True
        await pilot.pause()

        # Import and call action_open_editor directly -- it should bail immediately
        from conductor.tui.app import ConductorApp

        with patch("subprocess.run") as mock_run:
            # Bind the action method to our app instance
            ConductorApp.action_open_editor(app)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()
            mock_run.assert_not_called()

        assert len(app.editor_messages) == 0, "No EditorContentReady should be posted during replay"


# -- Test 4: Graceful handling when suspend not supported ----------------------


async def test_ctrl_g_graceful_no_suspend():
    """When App.suspend() raises SuspendNotSupported, a warning notification is shown."""
    from textual.app import App, ComposeResult, SuspendNotSupported
    from textual.widgets import Input

    from conductor.tui.widgets.command_input import CommandInput

    class NoSuspendApp(App):
        BINDINGS = []
        notifications = []

        def compose(self) -> ComposeResult:
            yield CommandInput(id="command-input")

        def notify(self, message, *, severity="information", **kwargs):
            self.notifications.append((message, severity))
            return super().notify(message, severity=severity, **kwargs)

    app = NoSuspendApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        from conductor.tui.app import ConductorApp

        # Patch suspend to raise SuspendNotSupported
        with patch.object(app, "suspend", side_effect=SuspendNotSupported("no tty")):
            ConductorApp.action_open_editor(app)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

        warnings = [(m, s) for m, s in app.notifications if s == "warning"]
        assert len(warnings) >= 1, f"Expected a warning notification, got: {app.notifications}"


# -- Test 5: on_editor_content_ready fills input -------------------------------


async def test_on_editor_content_ready_fills_input():
    """CommandInput.on_editor_content_ready sets Input.value and cursor position."""
    from textual.app import App, ComposeResult
    from textual.widgets import Input

    from conductor.tui.messages import EditorContentReady
    from conductor.tui.widgets.command_input import CommandInput

    class FillTestApp(App):
        def compose(self) -> ComposeResult:
            yield CommandInput(id="command-input")

    app = FillTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        cmd = app.query_one(CommandInput)
        cmd.post_message(EditorContentReady("test text"))
        await pilot.pause()
        await pilot.pause()

        inp = cmd.query_one(Input)
        assert inp.value == "test text", f"Expected 'test text', got '{inp.value}'"
        assert inp.cursor_position == len("test text")


# -- Test 6: Full editor flow with mock subprocess -----------------------------


async def test_editor_flow_with_mock_subprocess():
    """Full integration: Ctrl-G opens editor, edited content fills CommandInput."""
    import os
    from contextlib import contextmanager

    from textual.app import App, ComposeResult
    from textual.widgets import Input

    from conductor.tui.widgets.command_input import CommandInput

    @contextmanager
    def noop_suspend():
        yield

    def mock_subprocess_run(cmd, **kwargs):
        """Write 'edited content' into the temp file the editor received."""
        tmp_path = cmd[1]  # [editor, tmp_path]
        with open(tmp_path, "w") as f:
            f.write("edited content\n")

    class EditorFlowApp(App):
        BINDINGS = []

        def compose(self) -> ComposeResult:
            yield CommandInput(id="command-input")

    app = EditorFlowApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        from conductor.tui.app import ConductorApp

        with (
            patch.object(app, "suspend", side_effect=noop_suspend),
            patch("subprocess.run", side_effect=mock_subprocess_run),
            patch.dict(os.environ, {"VISUAL": "mock-editor"}, clear=False),
        ):
            ConductorApp.action_open_editor(app)
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

        cmd = app.query_one(CommandInput)
        inp = cmd.query_one(Input)
        assert inp.value == "edited content", f"Expected 'edited content', got '{inp.value}'"
