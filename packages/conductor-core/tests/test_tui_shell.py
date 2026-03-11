"""Phase 32: Static TUI Shell tests.

Tests that the two-column layout renders correctly in headless mode and
that CommandInput -> TranscriptPane message routing works.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
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
