"""Tests for Phase 20: Session Resumption (SESS-04).

Covers:
- Session listing shows correct sessions with first prompt
- Session picker displays and handles selection
- History replay formatting on resume
- Crash recovery (partial turns)
- Edge cases: no sessions, invalid selection, empty session
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.cli.chat import ChatSession, pick_session
from conductor.cli.chat_persistence import ChatHistoryStore


# ---------------------------------------------------------------------------
# ChatHistoryStore enhancements for SESS-04
# ---------------------------------------------------------------------------


class TestLoadSessionsWithFirstPrompt:
    """Tests that load_sessions now includes first_prompt."""

    def test_includes_first_prompt(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        store.save_turn("user", "Hello world")
        store.save_turn("assistant", "Hi there!")

        sessions = ChatHistoryStore.load_sessions(tmp_path)
        assert len(sessions) == 1
        assert sessions[0]["first_prompt"] == "Hello world"

    def test_first_prompt_empty_when_no_user_turns(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        # Only an assistant turn (edge case)
        store.save_turn("assistant", "Unprompted response")

        sessions = ChatHistoryStore.load_sessions(tmp_path)
        assert len(sessions) == 1
        assert sessions[0]["first_prompt"] == ""

    def test_multiple_sessions_sorted_newest_first(self, tmp_path: Path) -> None:
        store1 = ChatHistoryStore(tmp_path)
        store1.save_turn("user", "First session")

        store2 = ChatHistoryStore(tmp_path)
        store2.save_turn("user", "Second session")

        sessions = ChatHistoryStore.load_sessions(tmp_path)
        assert len(sessions) == 2
        # Most recent first
        assert sessions[0]["session_id"] == store2.session_id
        assert sessions[0]["first_prompt"] == "Second session"
        assert sessions[1]["session_id"] == store1.session_id
        assert sessions[1]["first_prompt"] == "First session"


class TestChatHistoryStoreResume:
    """Tests for resuming an existing session via resume_id."""

    def test_resume_existing_session(self, tmp_path: Path) -> None:
        # Create a session with some turns
        store = ChatHistoryStore(tmp_path)
        store.save_turn("user", "Hello")
        store.save_turn("assistant", "Hi!")
        original_id = store.session_id

        # Resume it
        resumed = ChatHistoryStore(tmp_path, resume_id=original_id)
        assert resumed.session_id == original_id
        assert len(resumed._turns) == 2

    def test_resume_and_append(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        store.save_turn("user", "Hello")
        original_id = store.session_id

        # Resume and add a turn
        resumed = ChatHistoryStore(tmp_path, resume_id=original_id)
        resumed.save_turn("user", "Follow up")

        # Verify 2 turns on disk
        loaded = ChatHistoryStore.load_session(tmp_path, original_id)
        assert loaded is not None
        assert len(loaded["turns"]) == 2
        assert loaded["turns"][1]["content"] == "Follow up"

    def test_resume_nonexistent_creates_new(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path, resume_id="nonexistent")
        # Should create a new session (not the missing ID)
        assert store.session_id != "nonexistent"
        assert (tmp_path / "chat_sessions" / f"{store.session_id}.json").exists()


# ---------------------------------------------------------------------------
# Session picker
# ---------------------------------------------------------------------------


class TestPickSession:
    """Tests for the interactive session picker."""

    def test_no_sessions_returns_none(self, tmp_path: Path) -> None:
        console = MagicMock()
        result = pick_session(cwd=str(tmp_path), console=console)
        assert result is None
        calls = [str(c) for c in console.print.call_args_list]
        assert any("No previous sessions" in c for c in calls)

    def test_valid_selection(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Test prompt")

        console = MagicMock()
        with patch("builtins.input", return_value="1"):
            result = pick_session(cwd=str(tmp_path), console=console)

        assert result == store.session_id

    def test_invalid_number_returns_none(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Test prompt")

        console = MagicMock()
        with patch("builtins.input", return_value="99"):
            result = pick_session(cwd=str(tmp_path), console=console)

        assert result is None

    def test_non_numeric_returns_none(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Test prompt")

        console = MagicMock()
        with patch("builtins.input", return_value="abc"):
            result = pick_session(cwd=str(tmp_path), console=console)

        assert result is None

    def test_empty_input_returns_none(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Test")

        console = MagicMock()
        with patch("builtins.input", return_value=""):
            result = pick_session(cwd=str(tmp_path), console=console)

        assert result is None

    def test_keyboard_interrupt_returns_none(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Test")

        console = MagicMock()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = pick_session(cwd=str(tmp_path), console=console)

        assert result is None

    def test_displays_session_info(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "What is Python?")
        store.save_turn("assistant", "A programming language.")

        console = MagicMock()
        with patch("builtins.input", return_value="1"):
            pick_session(cwd=str(tmp_path), console=console)

        calls = [str(c) for c in console.print.call_args_list]
        # Should show the first prompt text
        assert any("What is Python?" in c for c in calls)
        # Should show turn count
        assert any("2 turns" in c for c in calls)

    def test_long_prompt_truncated(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        store = ChatHistoryStore(conductor_dir)
        long_prompt = "x" * 100
        store.save_turn("user", long_prompt)

        console = MagicMock()
        with patch("builtins.input", return_value="1"):
            pick_session(cwd=str(tmp_path), console=console)

        calls = [str(c) for c in console.print.call_args_list]
        # The full 100-char prompt should not appear; it should be truncated
        assert not any(long_prompt in c for c in calls)
        # But a truncated version with "..." should
        assert any("..." in c for c in calls)

    def test_limits_to_10_sessions(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        for i in range(15):
            store = ChatHistoryStore(conductor_dir)
            store.save_turn("user", f"Session {i}")

        console = MagicMock()
        with patch("builtins.input", return_value=""):
            pick_session(cwd=str(tmp_path), console=console)

        # Count lines with numbered session entries
        calls = [str(c) for c in console.print.call_args_list]
        numbered_lines = [c for c in calls if "Session " in c and "turn" in c]
        assert len(numbered_lines) == 10


# ---------------------------------------------------------------------------
# History replay
# ---------------------------------------------------------------------------


class TestHistoryReplay:
    """Tests for replaying conversation history on resume."""

    def _make_session_with_history(
        self, tmp_path: Path, turns: list[dict]
    ) -> str:
        """Create a persisted session and return its ID."""
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir(exist_ok=True)
        store = ChatHistoryStore(conductor_dir)
        for t in turns:
            store.save_turn(t["role"], t["content"], t.get("token_count", 0))
        return store.session_id

    def test_replay_shows_user_and_assistant_turns(self, tmp_path: Path) -> None:
        session_id = self._make_session_with_history(tmp_path, [
            {"role": "user", "content": "What is 2+2?"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "And 3+3?"},
            {"role": "assistant", "content": "6"},
        ])

        console = MagicMock()
        session = ChatSession(
            console=console, cwd=str(tmp_path), resume_session_id=session_id
        )

        session._replay_history()

        calls = [str(c) for c in console.print.call_args_list]
        assert any("What is 2+2?" in c for c in calls)
        assert any("4" in c and "Assistant" in c for c in calls)
        assert any("And 3+3?" in c for c in calls)
        assert any("6" in c and "Assistant" in c for c in calls)

    def test_replay_shows_resuming_message(self, tmp_path: Path) -> None:
        session_id = self._make_session_with_history(tmp_path, [
            {"role": "user", "content": "Hello"},
        ])

        console = MagicMock()
        session = ChatSession(
            console=console, cwd=str(tmp_path), resume_session_id=session_id
        )

        session._replay_history()

        calls = [str(c) for c in console.print.call_args_list]
        assert any("Resuming session" in c for c in calls)

    def test_replay_shows_end_marker(self, tmp_path: Path) -> None:
        session_id = self._make_session_with_history(tmp_path, [
            {"role": "user", "content": "Hello"},
        ])

        console = MagicMock()
        session = ChatSession(
            console=console, cwd=str(tmp_path), resume_session_id=session_id
        )

        session._replay_history()

        calls = [str(c) for c in console.print.call_args_list]
        assert any("End of history" in c for c in calls)

    def test_replay_nonexistent_session(self, tmp_path: Path) -> None:
        console = MagicMock()
        session = ChatSession(
            console=console, cwd=str(tmp_path), resume_session_id="nonexistent"
        )

        session._replay_history()

        calls = [str(c) for c in console.print.call_args_list]
        assert any("not found" in c for c in calls)

    def test_replay_empty_session(self, tmp_path: Path) -> None:
        """An empty session (no turns) should show a message."""
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir(exist_ok=True)
        store = ChatHistoryStore(conductor_dir)
        session_id = store.session_id

        console = MagicMock()
        session = ChatSession(
            console=console, cwd=str(tmp_path), resume_session_id=session_id
        )

        session._replay_history()

        calls = [str(c) for c in console.print.call_args_list]
        assert any("No conversation history" in c for c in calls)


# ---------------------------------------------------------------------------
# Crash recovery (SESS-04 resilience)
# ---------------------------------------------------------------------------


class TestCrashRecovery:
    """Tests that resuming a session with partial turns works correctly."""

    def test_resume_session_with_only_user_turn(self, tmp_path: Path) -> None:
        """Simulates crash after user sent message but before assistant replied."""
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir(exist_ok=True)
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "This was my last message before crash")
        session_id = store.session_id

        console = MagicMock()
        session = ChatSession(
            console=console, cwd=str(tmp_path), resume_session_id=session_id
        )

        session._replay_history()

        calls = [str(c) for c in console.print.call_args_list]
        assert any("This was my last message before crash" in c for c in calls)
        # Should still show end-of-history marker
        assert any("End of history" in c for c in calls)

    def test_resume_preserves_all_persisted_turns(self, tmp_path: Path) -> None:
        """All turns that were flushed before crash are recoverable."""
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir(exist_ok=True)
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Turn 1")
        store.save_turn("assistant", "Reply 1")
        store.save_turn("user", "Turn 2")
        # Simulate crash here — assistant reply for Turn 2 never saved
        session_id = store.session_id

        loaded = ChatHistoryStore.load_session(conductor_dir, session_id)
        assert loaded is not None
        assert len(loaded["turns"]) == 3
        assert loaded["turns"][-1]["content"] == "Turn 2"

    def test_resume_and_continue_after_crash(self, tmp_path: Path) -> None:
        """After resuming a crashed session, new turns append correctly."""
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir(exist_ok=True)
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Before crash")
        session_id = store.session_id

        # Resume the session
        resumed_store = ChatHistoryStore(conductor_dir, resume_id=session_id)
        resumed_store.save_turn("user", "After recovery")

        loaded = ChatHistoryStore.load_session(conductor_dir, session_id)
        assert loaded is not None
        assert len(loaded["turns"]) == 2
        assert loaded["turns"][0]["content"] == "Before crash"
        assert loaded["turns"][1]["content"] == "After recovery"


# ---------------------------------------------------------------------------
# Integration: run() calls _replay_history on resume
# ---------------------------------------------------------------------------


class TestRunWithResume:
    """Tests that run() replays history when resume_session_id is set."""

    @pytest.mark.asyncio
    async def test_run_replays_history_then_prompts(self, tmp_path: Path) -> None:
        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir(exist_ok=True)
        store = ChatHistoryStore(conductor_dir)
        store.save_turn("user", "Earlier question")
        store.save_turn("assistant", "Earlier answer")
        session_id = store.session_id

        console = MagicMock()
        session = ChatSession(
            console=console, cwd=str(tmp_path), resume_session_id=session_id
        )

        # Have the prompt return /exit immediately
        with patch.object(
            session._prompt_session,
            "prompt_async",
            new=AsyncMock(return_value="/exit"),
        ):
            await session.run()

        calls = [str(c) for c in console.print.call_args_list]
        # History should be replayed
        assert any("Earlier question" in c for c in calls)
        assert any("Earlier answer" in c for c in calls)
        # Session welcome message should appear
        assert any("Conductor" in c for c in calls)

    @pytest.mark.asyncio
    async def test_run_without_resume_does_not_replay(self, tmp_path: Path) -> None:
        console = MagicMock()
        session = ChatSession(console=console, cwd=str(tmp_path))

        with patch.object(
            session._prompt_session,
            "prompt_async",
            new=AsyncMock(return_value="/exit"),
        ):
            await session.run()

        calls = [str(c) for c in console.print.call_args_list]
        # Should not have any replay markers
        assert not any("End of history" in c for c in calls)
        assert not any("Resuming session" in c for c in calls)
