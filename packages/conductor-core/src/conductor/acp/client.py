"""ACPClient — async context manager wrapping ClaudeSDKClient for sub-agent sessions."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, cast

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher
from claude_agent_sdk.types import SettingSource, SyncHookJSONOutput

from conductor.acp.errors import SessionError

if TYPE_CHECKING:
    from conductor.acp.permission import PermissionHandler

_DEFAULT_ALLOWED_TOOLS: list[str] = ["Read", "Edit", "Write", "Bash", "Glob", "Grep"]
_DEFAULT_MAX_TURNS = 50
_DEFAULT_SETTING_SOURCES: list[SettingSource] = cast(
    "list[SettingSource]", ["project"]
)


class ACPClient:
    """Async context manager wrapping ClaudeSDKClient for sub-agent sessions.

    Handles session lifecycle, streaming, and correct options wiring
    including the mandatory PreToolUse keepalive hook.

    Usage::
        handler = PermissionHandler(state_manager=mgr)
        async with ACPClient(
            cwd="/path/to/repo",
            system_prompt="You are Ariel, a backend developer.",
            permission_handler=handler,
        ) as client:
            await client.send("Implement the /api/users endpoint")
            async for message in client.stream_response():
                process(message)
    """

    def __init__(
        self,
        *,
        cwd: str,
        system_prompt: str = "",
        resume: str | None = None,
        allowed_tools: list[str] | None = None,
        permission_handler: PermissionHandler | None = None,
        max_turns: int = _DEFAULT_MAX_TURNS,
        setting_sources: list[SettingSource] | None = None,
    ) -> None:
        self._closed = False
        self._sdk_client: ClaudeSDKClient | None = None

        hooks: dict | None = None
        can_use_tool = None

        if permission_handler is not None:
            can_use_tool = permission_handler.handle

            async def _keepalive(  # noqa: ARG001
                input_data, tool_use_id, context
            ) -> SyncHookJSONOutput:
                return SyncHookJSONOutput(continue_=True)

            hooks = {"PreToolUse": [HookMatcher(matcher=None, hooks=[_keepalive])]}

        resolved_tools = (
            allowed_tools if allowed_tools is not None else _DEFAULT_ALLOWED_TOOLS
        )
        resolved_sources: list[SettingSource] = (
            setting_sources if setting_sources is not None else _DEFAULT_SETTING_SOURCES
        )
        self._options = ClaudeAgentOptions(
            cwd=cwd,
            system_prompt=system_prompt,
            resume=resume,
            allowed_tools=resolved_tools,
            max_turns=max_turns,
            setting_sources=resolved_sources,
            permission_mode="default",
            can_use_tool=can_use_tool,
            hooks=hooks,
        )

    async def __aenter__(self) -> ACPClient:
        self._sdk_client = ClaudeSDKClient(options=self._options)
        await self._sdk_client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        try:
            if self._sdk_client is not None:
                await self._sdk_client.__aexit__(exc_type, exc_val, exc_tb)
        finally:
            self._closed = True
        return False

    async def send(self, prompt: str) -> None:
        """Send a prompt to the sub-agent.

        Parameters
        ----------
        prompt:
            The instruction or message to send to the sub-agent.

        Raises
        ------
        SessionError
            If the session has already been closed.
        """
        if self._closed:
            raise SessionError("Session is closed")
        assert self._sdk_client is not None
        await self._sdk_client.query(prompt)

    async def stream_response(self) -> AsyncIterator:
        """Yield messages from the sub-agent as they arrive.

        Raises
        ------
        SessionError
            If the session has already been closed.
        """
        if self._closed:
            raise SessionError("Session is closed")
        assert self._sdk_client is not None
        async for message in self._sdk_client.receive_response():
            yield message

    async def interrupt(self) -> None:
        """Interrupt the current sub-agent task.

        For future use in Phase 6 (task cancellation).
        """
        if self._sdk_client is not None:
            await self._sdk_client.interrupt()
