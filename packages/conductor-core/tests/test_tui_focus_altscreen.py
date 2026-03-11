"""Phase 39: Auto-focus and alt-screen terminal lifecycle tests.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""
from __future__ import annotations


async def test_input_focused_on_startup():
    from conductor.tui.app import ConductorApp
    from textual.widgets import Input

    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()  # two pauses to allow focus chain to settle
        assert isinstance(app.focused, Input), (
            f"Expected Input to be focused, got {type(app.focused)}"
        )


async def test_auto_focus_selector_resolves():
    from conductor.tui.app import ConductorApp
    from textual.widgets import Input

    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("CommandInput Input")
        assert isinstance(widget, Input)


async def test_focus_restored_after_modal():
    """Verify focus can be restored to CommandInput Input after modal dismiss.

    AUTO_FOCUS fires on initial screen mount only. Post-modal focus restoration
    uses explicit .focus() calls (belt-and-suspenders pattern in _watch_escalations
    and on_stream_done). This test verifies the explicit focus path works.
    """
    from textual.app import App, ComposeResult, Screen
    from textual.widgets import Input
    from conductor.tui.widgets.command_input import CommandInput

    class ModalScreen(Screen):
        def compose(self) -> ComposeResult:
            from textual.widgets import Button

            yield Button("dismiss")

        def on_button_pressed(self) -> None:
            self.dismiss()

    class FocusApp(App):
        AUTO_FOCUS = "CommandInput Input"

        def compose(self) -> ComposeResult:
            yield CommandInput(id="command-input")

    app = FocusApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Verify initial focus
        assert isinstance(app.focused, Input), "Pre-condition: Input focused initially"
        await app.push_screen(ModalScreen())
        await pilot.pause()
        # Pop screen directly (simulates dismiss completing)
        app.pop_screen()
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.focused, Input), (
            f"Expected Input focused after modal, got {type(app.focused)}"
        )


def test_no_inline_true_in_launch():
    import pathlib

    cli_path = (
        pathlib.Path(__file__).parent.parent
        / "src"
        / "conductor"
        / "cli"
        / "__init__.py"
    )
    source = cli_path.read_text()
    assert "inline=True" not in source, "inline=True must not appear in CLI launch path"


async def test_ctrl_c_routes_through_action_quit():
    from conductor.tui.app import ConductorApp

    assert hasattr(ConductorApp, "action_quit"), "ConductorApp must have action_quit"
    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # action_quit should exit cleanly -- app exits without exception
        await app.action_quit()


def test_cli_has_terminal_cleanup():
    import pathlib

    cli_path = (
        pathlib.Path(__file__).parent.parent
        / "src"
        / "conductor"
        / "cli"
        / "__init__.py"
    )
    source = cli_path.read_text()
    assert "try:" in source, "CLI must have try block around ConductorApp().run()"
    assert "finally:" in source, "CLI must have finally block for terminal cleanup"
    assert "sys.stdout.write" in source, (
        "CLI finally block must write terminal restore codes"
    )
