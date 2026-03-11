"""Tests for the interactive chat TUI (Phase 18).

Covers:
- Slash command parsing and dispatch
- Input history tracking
- Ctrl+C state machine (idle vs running)
- ChatSession lifecycle

Updated for Phase 19: _handle_slash_command is now async,
_process_message now uses SDK (tested in test_chat_phase19.py).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.cli.chat import SLASH_COMMANDS, ChatSession, _CtrlCState


# ---------------------------------------------------------------------------
# Slash command dispatch
# ---------------------------------------------------------------------------


class TestSlashCommands:
    """Unit tests for slash command dispatch logic."""

    def _make_session(self) -> ChatSession:
        console = MagicMock()
        return ChatSession(console=console)

    @pytest.mark.asyncio
    async def test_help_returns_false(self) -> None:
        session = self._make_session()
        assert await session._handle_slash_command("/help") is False

    @pytest.mark.asyncio
    async def test_help_prints_all_commands(self) -> None:
        session = self._make_session()
        await session._handle_slash_command("/help")
        # Should have printed header + one line per command
        calls = session._console.print.call_args_list
        # At least one call per command + header
        assert len(calls) >= len(SLASH_COMMANDS) + 1

    @pytest.mark.asyncio
    async def test_exit_returns_true(self) -> None:
        session = self._make_session()
        assert await session._handle_slash_command("/exit") is True

    @pytest.mark.asyncio
    async def test_status_returns_false(self) -> None:
        session = self._make_session()
        assert await session._handle_slash_command("/status") is False

    @pytest.mark.asyncio
    async def test_unknown_command_returns_false(self) -> None:
        session = self._make_session()
        assert await session._handle_slash_command("/foobar") is False

    @pytest.mark.asyncio
    async def test_unknown_command_prints_error(self) -> None:
        session = self._make_session()
        await session._handle_slash_command("/foobar")
        printed = str(session._console.print.call_args)
        assert "Unknown command" in printed

    def test_slash_commands_registry_has_required_commands(self) -> None:
        assert "/help" in SLASH_COMMANDS
        assert "/exit" in SLASH_COMMANDS
        assert "/status" in SLASH_COMMANDS
        assert "/resume" in SLASH_COMMANDS

    @pytest.mark.asyncio
    async def test_resume_dispatches_to_delegation_manager(self) -> None:
        session = self._make_session()
        session._delegation_manager = MagicMock()
        session._delegation_manager.resume_delegation = AsyncMock()
        result = await session._handle_slash_command("/resume")
        assert result is False
        session._delegation_manager.resume_delegation.assert_called_once()


# ---------------------------------------------------------------------------
# Input history
# ---------------------------------------------------------------------------


class TestInputHistory:
    """Tests that prompt_toolkit InMemoryHistory is wired up correctly."""

    def test_session_has_in_memory_history(self) -> None:
        from prompt_toolkit.history import InMemoryHistory

        session = ChatSession(console=MagicMock())
        assert isinstance(session._history, InMemoryHistory)

    def test_prompt_session_uses_history(self) -> None:
        session = ChatSession(console=MagicMock())
        assert session._prompt_session.history is session._history


# ---------------------------------------------------------------------------
# Ctrl+C state machine
# ---------------------------------------------------------------------------


class TestCtrlCStateMachine:
    """Tests for Ctrl+C behaviour in idle vs running states."""

    def test_initial_state_is_idle(self) -> None:
        session = ChatSession(console=MagicMock())
        assert session._state == _CtrlCState.IDLE

    @pytest.mark.asyncio
    async def test_cancel_running_task_cancels(self) -> None:
        session = ChatSession(console=MagicMock())

        async def _long_task() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(_long_task())
        session._running_task = task
        session._cancel_running_task()
        assert task.cancelling() > 0
        # Let the cancellation propagate
        with pytest.raises(asyncio.CancelledError):
            await task

    def test_cancel_running_task_noop_when_none(self) -> None:
        session = ChatSession(console=MagicMock())
        session._running_task = None
        session._cancel_running_task()  # should not raise


# ---------------------------------------------------------------------------
# ChatSession.run() integration
# ---------------------------------------------------------------------------


class TestChatSessionRun:
    """Integration-style tests for the REPL loop."""

    @pytest.mark.asyncio
    async def test_exit_command_exits(self) -> None:
        """Typing /exit should cause run() to return."""
        session = ChatSession(console=MagicMock())

        with patch.object(
            session._prompt_session,
            "prompt_async",
            new=AsyncMock(return_value="/exit"),
        ):
            await session.run()  # should return without error

    @pytest.mark.asyncio
    async def test_help_then_exit(self) -> None:
        """Typing /help then /exit should work."""
        session = ChatSession(console=MagicMock())

        responses = iter(["/help", "/exit"])

        async def _fake_prompt(*args: object, **kwargs: object) -> str:
            return next(responses)

        with patch.object(
            session._prompt_session,
            "prompt_async",
            new=_fake_prompt,
        ):
            await session.run()

    @pytest.mark.asyncio
    async def test_empty_input_ignored(self) -> None:
        """Empty/whitespace input should be ignored, not processed."""
        console = MagicMock()
        session = ChatSession(console=console)

        responses = iter(["", "   ", "/exit"])

        async def _fake_prompt(*args: object, **kwargs: object) -> str:
            return next(responses)

        with patch.object(
            session._prompt_session,
            "prompt_async",
            new=_fake_prompt,
        ):
            await session.run()

        all_printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "(echo)" not in all_printed

    @pytest.mark.asyncio
    async def test_eof_exits(self) -> None:
        """Ctrl+D (EOFError) should exit the session."""
        session = ChatSession(console=MagicMock())

        with patch.object(
            session._prompt_session,
            "prompt_async",
            new=AsyncMock(side_effect=EOFError),
        ):
            await session.run()  # should return

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_at_idle_exits(self) -> None:
        """Ctrl+C at idle prompt should exit the session."""
        session = ChatSession(console=MagicMock())

        with patch.object(
            session._prompt_session,
            "prompt_async",
            new=AsyncMock(side_effect=KeyboardInterrupt),
        ):
            await session.run()  # should return
