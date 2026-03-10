"""Tests for ACP PermissionHandler — COMM-01 and COMM-02."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

from conductor.acp.permission import PermissionHandler  # noqa: E402 — RED: will fail


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context() -> ToolPermissionContext:
    return ToolPermissionContext()


# ---------------------------------------------------------------------------
# COMM-01: Permission routing and timeout
# ---------------------------------------------------------------------------

class TestComm01PermissionCallback:
    async def test_tool_request_returns_allow(self) -> None:
        """Regular tool calls are default-allowed with input passed through."""
        handler = PermissionHandler()
        input_data = {"file_path": "/tmp/x"}
        result = await handler.handle("Read", input_data, _make_context())
        assert isinstance(result, PermissionResultAllow)
        assert result.updated_input == input_data

    async def test_unknown_tool_returns_allow(self) -> None:
        """Unknown tools also get the default-allow treatment."""
        handler = PermissionHandler()
        result = await handler.handle("SomeNewTool", {}, _make_context())
        assert isinstance(result, PermissionResultAllow)


class TestComm01Timeout:
    async def test_timeout_returns_deny(self) -> None:
        """When answer_fn takes too long, handler returns PermissionResultDeny."""

        async def slow_answer_fn(input_data: dict) -> PermissionResultAllow:
            await asyncio.sleep(1.0)
            return PermissionResultAllow(updated_input=input_data)

        handler = PermissionHandler(timeout=0.01, answer_fn=slow_answer_fn)
        result = await handler.handle(
            "AskUserQuestion",
            {"questions": [{"question": "Proceed?"}]},
            _make_context(),
        )
        assert isinstance(result, PermissionResultDeny)
        assert "timeout" in result.message.lower()

    async def test_normal_call_completes_within_timeout(self) -> None:
        """Fast tool permission resolves to allow well within timeout."""
        handler = PermissionHandler(timeout=5.0)
        result = await handler.handle("Read", {"file_path": "/tmp/x"}, _make_context())
        assert isinstance(result, PermissionResultAllow)


# ---------------------------------------------------------------------------
# COMM-02: AskUserQuestion routing
# ---------------------------------------------------------------------------

class TestComm02AnswerQuestion:
    async def test_ask_user_question_routed_to_answer_fn(self) -> None:
        """AskUserQuestion is routed to answer_fn and returns PermissionResultAllow."""
        received: list[dict] = []

        async def mock_answer_fn(input_data: dict) -> PermissionResultAllow:
            received.append(input_data)
            return PermissionResultAllow(updated_input={**input_data, "answers": {"0": "yes"}})

        handler = PermissionHandler(answer_fn=mock_answer_fn)
        input_data = {"questions": [{"question": "Should I proceed?"}]}
        result = await handler.handle("AskUserQuestion", input_data, _make_context())

        assert isinstance(result, PermissionResultAllow)
        assert result.updated_input is not None
        assert "answers" in result.updated_input

    async def test_answer_fn_receives_questions_list(self) -> None:
        """answer_fn receives the full input_data dict including questions list."""
        captured: list[dict] = []

        async def capturing_fn(input_data: dict) -> PermissionResultAllow:
            captured.append(input_data)
            return PermissionResultAllow(updated_input=input_data)

        questions = [{"question": "Is the sky blue?"}, {"question": "Are we done?"}]
        handler = PermissionHandler(answer_fn=capturing_fn)
        await handler.handle("AskUserQuestion", {"questions": questions}, _make_context())

        assert len(captured) == 1
        assert captured[0]["questions"] == questions

    async def test_answer_from_state_context(self) -> None:
        """Default answer_fn reads StateManager and returns PermissionResultAllow."""
        from conductor.state.manager import StateManager
        from conductor.state.models import ConductorState, Task, TaskStatus

        # Build a minimal state file
        state = ConductorState(
            tasks=[
                Task(
                    id="t1",
                    title="Write auth module",
                    description="Implement JWT authentication",
                    status=TaskStatus.PENDING,
                )
            ]
        )

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(state.model_dump_json())

            manager = StateManager(state_path)
            handler = PermissionHandler(state_manager=manager)

            result = await handler.handle(
                "AskUserQuestion",
                {"questions": [{"question": "Should I proceed?"}]},
                _make_context(),
            )

        # Must allow (state was readable, default answer_fn worked)
        assert isinstance(result, PermissionResultAllow)
