"""ACP PermissionHandler — routes sub-agent tool permission requests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from conductor.acp.errors import PermissionTimeoutError

if TYPE_CHECKING:
    from conductor.state.manager import StateManager

_AnswerFn = Callable[[dict], Awaitable[PermissionResultAllow | PermissionResultDeny]]

_ASK_USER_QUESTION = "AskUserQuestion"


class PermissionHandler:
    """Routes sub-agent tool permission requests and AskUserQuestion calls.

    Every sub-agent tool call flows through :meth:`handle`.  Regular tool
    requests (Read, Edit, Bash, …) are default-allowed.  AskUserQuestion
    calls are forwarded to *answer_fn* so the orchestrator can craft a
    context-aware response using shared state.

    All async decision logic is wrapped in :func:`asyncio.wait_for` to
    enforce *timeout*.  On timeout the handler returns
    :class:`~claude_agent_sdk.types.PermissionResultDeny` (safe default =
    deny) and raises :class:`~conductor.acp.errors.PermissionTimeoutError`
    internally (logged but not propagated to the caller).
    """

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        answer_fn: _AnswerFn | None = None,
        state_manager: StateManager | None = None,
    ) -> None:
        self._timeout = timeout
        self._state_manager = state_manager

        if answer_fn is not None:
            self._answer_fn: _AnswerFn = answer_fn
        elif state_manager is not None:
            self._answer_fn = self._default_answer_with_state
        else:
            self._answer_fn = self._default_answer_no_state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle(
        self,
        tool_name: str,
        input_data: dict,
        context: ToolPermissionContext,  # noqa: ARG002
    ) -> PermissionResultAllow | PermissionResultDeny:
        """Callback compatible with the claude-agent-sdk *can_use_tool* hook.

        Parameters
        ----------
        tool_name:
            Name of the tool the sub-agent wants to invoke.
        input_data:
            Arguments the sub-agent passed to the tool.
        context:
            SDK-provided context (suggestions, abort signal).  Not used
            directly by the handler but kept for API compatibility.

        Returns
        -------
        PermissionResultAllow | PermissionResultDeny
        """
        try:
            return await asyncio.wait_for(
                self._route(tool_name, input_data),
                timeout=self._timeout,
            )
        except TimeoutError:
            _ = PermissionTimeoutError(
                f"Permission callback for '{tool_name}' timed out after "
                f"{self._timeout}s"
            )
            return PermissionResultDeny(
                message=(
                    f"Permission timeout after {self._timeout}s"
                    " — denied by safe default"
                )
            )

    # ------------------------------------------------------------------
    # Internal routing
    # ------------------------------------------------------------------

    async def _route(
        self,
        tool_name: str,
        input_data: dict,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name == _ASK_USER_QUESTION:
            return await self._answer_fn(input_data)
        return PermissionResultAllow(updated_input=input_data)

    # ------------------------------------------------------------------
    # Default answer functions
    # ------------------------------------------------------------------

    async def _default_answer_with_state(
        self,
        input_data: dict,
    ) -> PermissionResultAllow:
        """Read current state and answer all questions with 'proceed'."""
        assert self._state_manager is not None  # guaranteed by __init__
        await asyncio.to_thread(self._state_manager.read_state)
        questions: list[dict] = input_data.get("questions", [])
        answers = {str(i): "proceed" for i in range(len(questions))}
        return PermissionResultAllow(updated_input={**input_data, "answers": answers})

    async def _default_answer_no_state(
        self,
        input_data: dict,
    ) -> PermissionResultAllow:
        """Answer all questions with 'proceed' (no state manager available)."""
        questions: list[dict] = input_data.get("questions", [])
        answers = {str(i): "proceed" for i in range(len(questions))}
        return PermissionResultAllow(updated_input={**input_data, "answers": answers})
