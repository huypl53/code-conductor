"""Tests for ACPClient — session lifecycle, streaming, and options wiring.

All SDK interactions are fully mocked. No real Claude processes are spawned.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.acp.client import ACPClient
from conductor.acp.errors import SessionError
from conductor.acp.permission import PermissionHandler


# ---------------------------------------------------------------------------
# Minimal mock types to avoid requiring Claude CLI for test collection
# ---------------------------------------------------------------------------


class _MockToolUseBlock:
    """Minimal ToolUseBlock stand-in."""

    def __init__(self, name: str, input: dict) -> None:  # noqa: A002
        self.name = name
        self.input = input
        self.type = "tool_use"


class _MockAssistantMessage:
    """Minimal AssistantMessage stand-in."""

    def __init__(self, content: list) -> None:
        self.content = content
        self.type = "assistant"


class _MockResultMessage:
    """Minimal ResultMessage stand-in."""

    def __init__(self) -> None:
        self.type = "result"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sdk_client_mock() -> MagicMock:
    """Return a configured mock for ClaudeSDKClient with async ctx manager."""
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.query = AsyncMock()
    mock.interrupt = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# TestComm01SessionLifecycle
# ---------------------------------------------------------------------------


class TestComm01SessionLifecycle:
    @pytest.fixture()
    def sdk_mock(self):
        return _make_sdk_client_mock()

    async def test_context_manager_opens_and_closes_session(self, sdk_mock):
        """__aenter__ and __aexit__ are called exactly once each."""
        with patch("conductor.acp.client.ClaudeSDKClient", return_value=sdk_mock):
            client = ACPClient(cwd="/tmp")
            async with client:
                pass

        sdk_mock.__aenter__.assert_called_once()
        sdk_mock.__aexit__.assert_called_once()

    async def test_context_manager_closes_on_exception(self, sdk_mock):
        """__aexit__ is called even when an exception is raised inside the block."""
        with patch("conductor.acp.client.ClaudeSDKClient", return_value=sdk_mock):
            client = ACPClient(cwd="/tmp")
            with pytest.raises(RuntimeError, match="test error"):
                async with client:
                    raise RuntimeError("test error")

        sdk_mock.__aexit__.assert_called_once()

    async def test_session_not_reusable_after_close(self, sdk_mock):
        """Calling send() after context manager exits raises SessionError."""
        with patch("conductor.acp.client.ClaudeSDKClient", return_value=sdk_mock):
            client = ACPClient(cwd="/tmp")
            async with client:
                pass

            with pytest.raises(SessionError):
                await client.send("hello")


# ---------------------------------------------------------------------------
# TestComm01Streaming
# ---------------------------------------------------------------------------


class TestComm01Streaming:
    @pytest.fixture()
    def sdk_mock(self):
        return _make_sdk_client_mock()

    async def test_receive_streams_tool_use_blocks(self, sdk_mock):
        """ToolUseBlock is yielded from stream_response()."""
        tool_block = _MockToolUseBlock(name="Read", input={"file_path": "/tmp/x"})
        assistant_msg = _MockAssistantMessage(content=[tool_block])
        result_msg = _MockResultMessage()

        async def _fake_receive():
            yield assistant_msg
            yield result_msg

        sdk_mock.receive_response = _fake_receive

        with patch("conductor.acp.client.ClaudeSDKClient", return_value=sdk_mock):
            client = ACPClient(cwd="/tmp")
            async with client:
                messages = [msg async for msg in client.stream_response()]

        assert assistant_msg in messages

    async def test_receive_streams_until_result(self, sdk_mock):
        """stream_response() yields AssistantMessage then ResultMessage and stops."""
        assistant_msg = _MockAssistantMessage(content=[])
        result_msg = _MockResultMessage()

        async def _fake_receive():
            yield assistant_msg
            yield result_msg

        sdk_mock.receive_response = _fake_receive

        with patch("conductor.acp.client.ClaudeSDKClient", return_value=sdk_mock):
            client = ACPClient(cwd="/tmp")
            async with client:
                messages = [msg async for msg in client.stream_response()]

        assert messages == [assistant_msg, result_msg]

    async def test_send_query_calls_sdk_query(self, sdk_mock):
        """send() delegates to the underlying SDK client.query()."""
        with patch("conductor.acp.client.ClaudeSDKClient", return_value=sdk_mock):
            client = ACPClient(cwd="/tmp")
            async with client:
                await client.send("implement feature X")

        sdk_mock.query.assert_called_once_with("implement feature X")


# ---------------------------------------------------------------------------
# TestComm01OptionsWiring
# ---------------------------------------------------------------------------


class TestComm01OptionsWiring:
    """Verify that ClaudeAgentOptions is built correctly from ACPClient params."""

    def _capture_options(self) -> tuple[MagicMock, list]:
        """Return (sdk_mock, captured_options_list).

        captured_options_list will contain the options passed to the
        ClaudeSDKClient constructor after the patch is applied.
        """
        captured: list = []
        sdk_mock = _make_sdk_client_mock()

        class CapturingConstructor:
            def __new__(cls, options=None, **kwargs):  # noqa: ARG003
                captured.append(options)
                return sdk_mock

        return CapturingConstructor, captured

    async def test_keepalive_hook_registered(self):
        """PreToolUse hooks list contains a HookMatcher with the keepalive fn."""
        handler = PermissionHandler()
        constructor, captured = self._capture_options()

        with patch("conductor.acp.client.ClaudeSDKClient", constructor):
            client = ACPClient(cwd="/tmp", permission_handler=handler)
            async with client:
                pass

        options = captured[0]
        assert options is not None
        hooks = options.hooks
        assert hooks is not None
        pre_tool_use_hooks = hooks.get("PreToolUse", [])
        assert len(pre_tool_use_hooks) >= 1
        # Each entry should be a HookMatcher (has .hooks attribute)
        hook_matcher = pre_tool_use_hooks[0]
        assert hasattr(hook_matcher, "hooks")
        assert len(hook_matcher.hooks) >= 1

    async def test_permission_handler_wired_as_can_use_tool(self):
        """options.can_use_tool is bound to PermissionHandler.handle."""
        handler = PermissionHandler()
        # Capture the bound method reference before it changes — Python bound
        # methods are recreated on each attribute access so identity (is) check
        # would fail. Use == which compares the underlying function + instance.
        handle_ref = handler.handle
        constructor, captured = self._capture_options()

        with patch("conductor.acp.client.ClaudeSDKClient", constructor):
            client = ACPClient(cwd="/tmp", permission_handler=handler)
            async with client:
                pass

        options = captured[0]
        assert options.can_use_tool == handle_ref

    async def test_system_prompt_passed_through(self):
        """options.system_prompt matches the value given to ACPClient."""
        constructor, captured = self._capture_options()

        with patch("conductor.acp.client.ClaudeSDKClient", constructor):
            client = ACPClient(cwd="/tmp", system_prompt="You are Ariel")
            async with client:
                pass

        options = captured[0]
        assert options.system_prompt == "You are Ariel"

    async def test_allowed_tools_passed_through(self):
        """options.allowed_tools matches the value given to ACPClient."""
        constructor, captured = self._capture_options()

        with patch("conductor.acp.client.ClaudeSDKClient", constructor):
            client = ACPClient(
                cwd="/tmp",
                allowed_tools=["Read", "Edit"],
            )
            async with client:
                pass

        options = captured[0]
        assert options.allowed_tools == ["Read", "Edit"]

    async def test_max_turns_default(self):
        """options.max_turns defaults to 50 when not specified."""
        constructor, captured = self._capture_options()

        with patch("conductor.acp.client.ClaudeSDKClient", constructor):
            client = ACPClient(cwd="/tmp")
            async with client:
                pass

        options = captured[0]
        assert options.max_turns == 50
