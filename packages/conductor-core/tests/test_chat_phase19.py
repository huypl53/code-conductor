"""Tests for Phase 19: Streaming Display and Session Lifecycle.

Covers:
- Token streaming display (mock SDK client)
- Tool activity line formatting (CHAT-06)
- Chat history persistence write/read roundtrip (SESS-05)
- Context warning trigger at threshold (CHAT-08)
- Working indicator lifecycle (CHAT-07)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage
from claude_agent_sdk.types import StreamEvent, TextBlock, ToolUseBlock

from conductor.cli.chat import SLASH_COMMANDS, ChatSession
from conductor.cli.chat_persistence import ChatHistoryStore
from conductor.cli.stream_display import (
    CONTEXT_WARNING_THRESHOLD,
    ContextTracker,
    format_tool_activity,
)


# ---------------------------------------------------------------------------
# Tool activity formatting (CHAT-06)
# ---------------------------------------------------------------------------


class TestFormatToolActivity:
    """Tests for human-readable tool activity lines."""

    def test_read_tool(self) -> None:
        result = format_tool_activity("Read", {"file_path": "/home/user/project/src/main.py"})
        assert result is not None
        assert "Reading" in result
        assert "src/main.py" in result

    def test_edit_tool(self) -> None:
        result = format_tool_activity("Edit", {"file_path": "/src/auth.py"})
        assert result is not None
        assert "Editing" in result
        assert "auth.py" in result

    def test_write_tool(self) -> None:
        result = format_tool_activity("Write", {"file_path": "/tmp/output.txt"})
        assert result is not None
        assert "Writing" in result

    def test_bash_tool(self) -> None:
        result = format_tool_activity("Bash", {"command": "pytest tests/"})
        assert result is not None
        assert "Running:" in result
        assert "pytest tests/" in result

    def test_bash_tool_long_command_truncated(self) -> None:
        long_cmd = "a" * 100
        result = format_tool_activity("Bash", {"command": long_cmd})
        assert result is not None
        assert len(result) < 80  # Should be truncated

    def test_glob_tool(self) -> None:
        result = format_tool_activity("Glob", {"pattern": "**/*.py"})
        assert result is not None
        assert "Searching:" in result

    def test_grep_tool(self) -> None:
        result = format_tool_activity("Grep", {"pattern": "def main"})
        assert result is not None
        assert "Grep:" in result

    def test_unknown_tool_has_fallback(self) -> None:
        result = format_tool_activity("CustomTool", {})
        assert result is not None
        assert "CustomTool" in result

    def test_empty_file_path(self) -> None:
        result = format_tool_activity("Read", {"file_path": ""})
        assert result is not None
        assert "<unknown>" in result


# ---------------------------------------------------------------------------
# Context tracker (CHAT-08)
# ---------------------------------------------------------------------------


class TestContextTracker:
    """Tests for context utilization tracking and warnings."""

    def test_initial_utilization_zero(self) -> None:
        tracker = ContextTracker()
        assert tracker.utilization == 0.0

    def test_update_usage(self) -> None:
        tracker = ContextTracker()
        tracker.update({"input_tokens": 50_000, "output_tokens": 1_000})
        assert tracker.input_tokens == 50_000
        assert tracker.output_tokens == 1_000

    def test_utilization_calculation(self) -> None:
        tracker = ContextTracker()
        # 100k of 200k context = 50%
        tracker.update({"input_tokens": 100_000, "output_tokens": 0})
        assert tracker.utilization == pytest.approx(0.5)

    def test_should_warn_at_threshold(self) -> None:
        tracker = ContextTracker()
        # Below threshold
        tracker.update({"input_tokens": 100_000, "output_tokens": 0})
        assert tracker.should_warn() is False

        # At threshold (75% of 200k = 150k)
        tracker.update({"input_tokens": 150_000, "output_tokens": 0})
        assert tracker.should_warn() is True

    def test_should_warn_only_once(self) -> None:
        tracker = ContextTracker()
        tracker.update({"input_tokens": 160_000, "output_tokens": 0})
        assert tracker.should_warn() is True
        assert tracker.should_warn() is False  # Second call returns False

    def test_reset_warning_allows_repeat(self) -> None:
        tracker = ContextTracker()
        tracker.update({"input_tokens": 160_000, "output_tokens": 0})
        assert tracker.should_warn() is True
        tracker.reset_warning()
        assert tracker.should_warn() is True  # Fires again after reset

    def test_update_with_none(self) -> None:
        tracker = ContextTracker()
        tracker.update(None)
        assert tracker.input_tokens == 0


# ---------------------------------------------------------------------------
# Chat history persistence (SESS-05)
# ---------------------------------------------------------------------------


class TestChatHistoryStore:
    """Tests for crash-safe chat history storage."""

    def test_creates_session_file(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        session_file = tmp_path / "chat_sessions" / f"{store.session_id}.json"
        assert session_file.exists()

    def test_save_turn_persists_immediately(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        store.save_turn("user", "hello", token_count=0)

        # Read back directly from disk
        data = json.loads(
            (tmp_path / "chat_sessions" / f"{store.session_id}.json").read_text()
        )
        assert len(data["turns"]) == 1
        assert data["turns"][0]["role"] == "user"
        assert data["turns"][0]["content"] == "hello"

    def test_multiple_turns(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        store.save_turn("user", "hi", token_count=0)
        store.save_turn("assistant", "hello!", token_count=42)
        store.save_turn("user", "how are you?", token_count=0)

        data = json.loads(
            (tmp_path / "chat_sessions" / f"{store.session_id}.json").read_text()
        )
        assert len(data["turns"]) == 3
        assert data["turns"][1]["token_count"] == 42

    def test_load_session_roundtrip(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        store.save_turn("user", "test message", token_count=10)
        store.save_turn("assistant", "test reply", token_count=50)

        loaded = ChatHistoryStore.load_session(tmp_path, store.session_id)
        assert loaded is not None
        assert loaded["session_id"] == store.session_id
        assert len(loaded["turns"]) == 2
        assert loaded["turns"][0]["content"] == "test message"

    def test_load_session_not_found(self, tmp_path: Path) -> None:
        result = ChatHistoryStore.load_session(tmp_path, "nonexistent")
        assert result is None

    def test_load_sessions_lists_all(self, tmp_path: Path) -> None:
        store1 = ChatHistoryStore(tmp_path)
        store1.save_turn("user", "session 1")

        store2 = ChatHistoryStore(tmp_path)
        store2.save_turn("user", "session 2")

        sessions = ChatHistoryStore.load_sessions(tmp_path)
        assert len(sessions) == 2
        session_ids = {s["session_id"] for s in sessions}
        assert store1.session_id in session_ids
        assert store2.session_id in session_ids

    def test_load_sessions_empty_dir(self, tmp_path: Path) -> None:
        sessions = ChatHistoryStore.load_sessions(tmp_path)
        assert sessions == []

    def test_session_has_metadata(self, tmp_path: Path) -> None:
        store = ChatHistoryStore(tmp_path)
        data = json.loads(
            (tmp_path / "chat_sessions" / f"{store.session_id}.json").read_text()
        )
        assert "session_id" in data
        assert "created_at" in data
        assert "turns" in data


# ---------------------------------------------------------------------------
# Streaming display integration (CHAT-02, CHAT-07)
# ---------------------------------------------------------------------------


# Helpers for creating real SDK message objects

def _make_stream_event(event_data: dict) -> StreamEvent:
    return StreamEvent(uuid="test-uuid", session_id="test-session", event=event_data)


def _make_text_delta_event(text: str) -> StreamEvent:
    return _make_stream_event({
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": text},
    })


def _make_result(usage: dict | None = None) -> ResultMessage:
    return ResultMessage(
        subtype="result",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=1,
        session_id="test-session",
        usage=usage,
    )


def _make_assistant_with_tool(tool_name: str, tool_input: dict) -> AssistantMessage:
    return AssistantMessage(
        content=[ToolUseBlock(id="tool-1", name=tool_name, input=tool_input)],
        model="test-model",
    )


class TestStreamingDisplay:
    """Tests for the streaming message processing in ChatSession."""

    def _make_session(self, tmp_path: Path) -> ChatSession:
        console = MagicMock()
        session = ChatSession(console=console, cwd=str(tmp_path))
        return session

    @pytest.mark.asyncio
    async def test_working_indicator_shown_and_cleared(self, tmp_path: Path) -> None:
        """CHAT-07: Spinner shown before first token, cleared when streaming starts."""
        session = self._make_session(tmp_path)

        async def mock_receive_response():
            yield _make_text_delta_event("Hello")
            yield _make_result(usage={"input_tokens": 10, "output_tokens": 5})

        mock_client = MagicMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive_response
        session._sdk_client = mock_client
        session._sdk_connected = True

        await session._process_message("test")

        all_prints = [str(c) for c in session._console.print.call_args_list]
        thinking_shown = any("Thinking" in p for p in all_prints)
        assert thinking_shown, "Working indicator should be shown"

    @pytest.mark.asyncio
    async def test_stream_tokens_incrementally(self, tmp_path: Path) -> None:
        """CHAT-02: Tokens stream incrementally to the console."""
        session = self._make_session(tmp_path)

        async def mock_receive_response():
            yield _make_text_delta_event("Hello")
            yield _make_text_delta_event(" world")
            yield _make_result(usage={"input_tokens": 10, "output_tokens": 5})

        mock_client = MagicMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive_response
        session._sdk_client = mock_client
        session._sdk_connected = True

        await session._process_message("test")

        calls = session._console.print.call_args_list
        printed_texts = [str(c) for c in calls]
        assert any("Hello" in p for p in printed_texts)
        assert any("world" in p for p in printed_texts)

    @pytest.mark.asyncio
    async def test_tool_activity_displayed(self, tmp_path: Path) -> None:
        """CHAT-06: Tool use blocks show human-readable status."""
        session = self._make_session(tmp_path)

        async def mock_receive_response():
            yield _make_assistant_with_tool("Read", {"file_path": "/src/auth.py"})
            yield _make_result(usage={"input_tokens": 10, "output_tokens": 5})

        mock_client = MagicMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive_response
        session._sdk_client = mock_client
        session._sdk_connected = True

        await session._process_message("read the file")

        calls = [str(c) for c in session._console.print.call_args_list]
        assert any("Reading" in p and "auth.py" in p for p in calls), (
            f"Expected tool activity line with 'Reading' and 'auth.py', got: {calls}"
        )

    @pytest.mark.asyncio
    async def test_context_warning_at_threshold(self, tmp_path: Path) -> None:
        """CHAT-08: Warning printed when context utilization hits ~75%."""
        session = self._make_session(tmp_path)

        async def mock_receive_response():
            yield _make_result(usage={"input_tokens": 160_000, "output_tokens": 1_000})

        mock_client = MagicMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive_response
        session._sdk_client = mock_client
        session._sdk_connected = True

        await session._process_message("long conversation")

        calls = [str(c) for c in session._console.print.call_args_list]
        assert any("Warning" in p and "summarize" in p.lower() for p in calls), (
            f"Expected context warning with /summarize suggestion, got: {calls}"
        )

    @pytest.mark.asyncio
    async def test_history_persisted_after_turn(self, tmp_path: Path) -> None:
        """SESS-05: User and assistant turns are persisted to disk."""
        session = self._make_session(tmp_path)

        async def mock_receive_response():
            yield _make_text_delta_event("Response text")
            yield _make_result(usage={"input_tokens": 10, "output_tokens": 5})

        mock_client = MagicMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive_response
        session._sdk_client = mock_client
        session._sdk_connected = True

        await session._process_message("my question")

        loaded = ChatHistoryStore.load_session(
            tmp_path / ".conductor", session._history_store.session_id
        )
        assert loaded is not None
        assert len(loaded["turns"]) == 2
        assert loaded["turns"][0]["role"] == "user"
        assert loaded["turns"][0]["content"] == "my question"
        assert loaded["turns"][1]["role"] == "assistant"
        assert loaded["turns"][1]["content"] == "Response text"

    @pytest.mark.asyncio
    async def test_no_response_shows_placeholder(self, tmp_path: Path) -> None:
        """When no tokens arrive, show a '(No response)' message."""
        session = self._make_session(tmp_path)

        async def mock_receive_response():
            yield _make_result(usage={"input_tokens": 10, "output_tokens": 0})

        mock_client = MagicMock()
        mock_client.query = AsyncMock()
        mock_client.receive_response = mock_receive_response
        session._sdk_client = mock_client
        session._sdk_connected = True

        await session._process_message("empty response")

        calls = [str(c) for c in session._console.print.call_args_list]
        assert any("No response" in p for p in calls)


# ---------------------------------------------------------------------------
# Slash command: /summarize
# ---------------------------------------------------------------------------


class TestSummarizeCommand:
    """Tests for the /summarize slash command."""

    def test_summarize_in_command_registry(self) -> None:
        assert "/summarize" in SLASH_COMMANDS

    @pytest.mark.asyncio
    async def test_summarize_when_not_connected(self) -> None:
        """Should print a message when no SDK session is active."""
        console = MagicMock()
        session = ChatSession(console=console)

        await session._handle_summarize()

        calls = [str(c) for c in console.print.call_args_list]
        assert any("No active conversation" in p for p in calls)


# ---------------------------------------------------------------------------
# ChatSession init with resume
# ---------------------------------------------------------------------------


class TestChatSessionResume:
    """Tests for session resume support."""

    def test_resume_session_id_stored(self) -> None:
        session = ChatSession(console=MagicMock(), resume_session_id="abc123")
        assert session._resume_session_id == "abc123"

    def test_no_resume_by_default(self) -> None:
        session = ChatSession(console=MagicMock())
        assert session._resume_session_id is None
