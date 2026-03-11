"""Phase 37: Slash command autocomplete and dispatch tests.

Tests for SlashAutocomplete widget, slash command dispatch in ConductorApp,
and dashboard wiring.

IMPORTANT: Keep run_test() inline in each test function — never in fixtures.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Task 1: SlashAutocomplete widget tests
# ---------------------------------------------------------------------------


async def test_slash_autocomplete_in_widget_tree():
    """SlashAutocomplete widget must exist in CommandInput's widget tree."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.command_input import CommandInput
    from textual_autocomplete import AutoComplete

    app = ConductorApp()
    async with app.run_test() as pilot:
        widget = app.query_one(CommandInput)
        assert widget is not None
        ac = widget.query_one(AutoComplete)
        assert ac is not None


async def test_slash_candidates_count():
    """get_candidates() must return exactly 5 items matching SLASH_COMMANDS."""
    from conductor.tui.widgets.command_input import SlashAutocomplete
    from conductor.cli.chat import SLASH_COMMANDS
    from textual_autocomplete import TargetState

    # We need a running app to test the widget
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    async with app.run_test() as pilot:
        from textual_autocomplete import AutoComplete
        ac = app.query_one(AutoComplete)
        assert isinstance(ac, SlashAutocomplete)
        state = TargetState(text="/", cursor_position=1)
        candidates = ac.get_candidates(state)
        assert len(candidates) == len(SLASH_COMMANDS)
        # Check that all command names appear as candidates
        candidate_mains = [c.main.plain if hasattr(c.main, 'plain') else str(c.main) for c in candidates]
        for cmd in SLASH_COMMANDS:
            assert cmd in candidate_mains


async def test_slash_search_string_with_slash():
    """get_search_string returns text after '/' when input starts with '/'."""
    from conductor.tui.app import ConductorApp
    from textual_autocomplete import AutoComplete, TargetState

    app = ConductorApp()
    async with app.run_test() as pilot:
        ac = app.query_one(AutoComplete)
        state = TargetState(text="/hel", cursor_position=4)
        result = ac.get_search_string(state)
        assert result == "hel"


async def test_slash_search_string_without_slash():
    """get_search_string returns no-match sentinel when input doesn't start with '/'."""
    from conductor.tui.app import ConductorApp
    from textual_autocomplete import AutoComplete, TargetState

    app = ConductorApp()
    async with app.run_test() as pilot:
        ac = app.query_one(AutoComplete)
        state = TargetState(text="hello", cursor_position=5)
        result = ac.get_search_string(state)
        assert result == "\x00"


# ---------------------------------------------------------------------------
# Task 2: Slash command dispatch tests
# ---------------------------------------------------------------------------


async def test_slash_help_shows_in_transcript():
    """Submitting '/help' adds a help message cell to the transcript."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import TranscriptPane, AssistantCell

    app = ConductorApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)
        initial_count = len(pane.query(AssistantCell))

        # Dispatch /help directly via the handler
        await app._handle_slash_command("/help")
        await pilot.pause()

        # A new AssistantCell should have been added
        cells = pane.query(AssistantCell)
        assert len(cells) > initial_count
        # The last cell should contain "Available commands"
        last_cell = cells[-1]
        assert last_cell._text is not None
        assert "Available commands" in last_cell._text


async def test_slash_exit_quits():
    """Submitting '/exit' calls _force_quit."""
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    async with app.run_test() as pilot:
        with patch.object(app, "_force_quit", new_callable=AsyncMock) as mock_quit:
            await app._handle_slash_command("/exit")
            mock_quit.assert_called_once()


async def test_slash_unknown_shows_error():
    """Submitting unknown '/foo' shows 'Unknown command' in transcript."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import TranscriptPane, AssistantCell

    app = ConductorApp()
    async with app.run_test() as pilot:
        await app._handle_slash_command("/foo")
        await pilot.pause()

        pane = app.query_one(TranscriptPane)
        cells = pane.query(AssistantCell)
        last_cell = cells[-1]
        assert last_cell._text is not None
        assert "Unknown command" in last_cell._text


async def test_slash_does_not_stream():
    """Slash commands must NOT call _stream_response."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.messages import UserSubmitted

    app = ConductorApp()
    async with app.run_test() as pilot:
        with patch.object(app, "_stream_response") as mock_stream:
            await app._handle_slash_command("/help")
            mock_stream.assert_not_called()


async def test_slash_status_no_delegation():
    """'/status' with no delegation_manager shows appropriate message."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import TranscriptPane, AssistantCell

    app = ConductorApp()
    async with app.run_test() as pilot:
        # _delegation_manager is None by default
        await app._handle_slash_command("/status")
        await pilot.pause()

        pane = app.query_one(TranscriptPane)
        cells = pane.query(AssistantCell)
        last_cell = cells[-1]
        assert last_cell._text is not None
        assert "delegation" in last_cell._text.lower() or "agent" in last_cell._text.lower()


async def test_on_user_submitted_routes_slash():
    """on_user_submitted routes slash commands to _handle_slash_command, not streaming."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.messages import UserSubmitted

    app = ConductorApp()
    async with app.run_test() as pilot:
        with patch.object(app, "_handle_slash_command", new_callable=AsyncMock) as mock_handler:
            with patch.object(app, "_stream_response") as mock_stream:
                event = UserSubmitted("/help")
                await app.on_user_submitted(event)
                mock_handler.assert_called_once_with("/help")
                mock_stream.assert_not_called()


async def test_dashboard_port_stored():
    """ConductorApp stores dashboard_port attribute."""
    from conductor.tui.app import ConductorApp

    app = ConductorApp(dashboard_port=9999)
    assert app._dashboard_port == 9999


async def test_start_dashboard_method_exists():
    """ConductorApp has _start_dashboard method."""
    from conductor.tui.app import ConductorApp

    assert hasattr(ConductorApp, "_start_dashboard")
    assert callable(getattr(ConductorApp, "_start_dashboard"))
