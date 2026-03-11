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
