"""Tests for EscalationRouter — COMM-03 (auto mode) and COMM-04 (interactive mode)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

from conductor.orchestrator.escalation import (  # RED: will fail until escalation.py exists
    DecisionLog,
    EscalationRouter,
    HumanQuery,
    _is_low_confidence,
)
from conductor.orchestrator.errors import EscalationError, OrchestratorError


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestEscalationError:
    def test_escalation_error_is_orchestrator_error(self) -> None:
        """EscalationError must be a subclass of OrchestratorError."""
        err = EscalationError("something went wrong")
        assert isinstance(err, OrchestratorError)
        assert isinstance(err, EscalationError)


# ---------------------------------------------------------------------------
# Confidence heuristic
# ---------------------------------------------------------------------------


class TestIsLowConfidence:
    @pytest.mark.parametrize(
        "question",
        [
            "Should I delete the database?",
            "Do you want me to deploy to production?",
            "Should I drop the users table?",
            "Are these credentials correct?",
            "This action is irreversible, shall I proceed?",
            "I need to use the billing API, is that okay?",
            "Should I remove the config file?",
            "This cannot be undone, shall I continue?",
            "Should I expose the secret key?",
        ],
    )
    def test_low_confidence_keywords(self, question: str) -> None:
        """Questions containing sensitive keywords are low-confidence."""
        assert _is_low_confidence(question) is True

    @pytest.mark.parametrize(
        "question",
        [
            "Should I use async?",
            "Should I add a type annotation here?",
            "Is this the right variable name?",
            "Should I use a list or a tuple?",
        ],
    )
    def test_high_confidence_benign_questions(self, question: str) -> None:
        """Benign questions are NOT low-confidence."""
        assert _is_low_confidence(question) is False


# ---------------------------------------------------------------------------
# COMM-03: Auto mode
# ---------------------------------------------------------------------------


class TestComm03AutoMode:
    @pytest.fixture
    def router(self) -> EscalationRouter:
        return EscalationRouter(mode="auto")

    async def test_auto_mode_high_confidence_returns_allow(
        self, router: EscalationRouter
    ) -> None:
        """Auto mode: high-confidence question -> PermissionResultAllow with 'proceed'."""
        input_data = {"questions": [{"question": "Should I use async?"}]}
        result = await router.resolve(input_data)
        assert isinstance(result, PermissionResultAllow)
        assert result.updated_input is not None

    async def test_auto_mode_low_confidence_still_returns_allow(
        self, router: EscalationRouter
    ) -> None:
        """Auto mode: low-confidence question -> still PermissionResultAllow (never deny)."""
        input_data = {"questions": [{"question": "Should I delete the table?"}]}
        result = await router.resolve(input_data)
        assert isinstance(result, PermissionResultAllow)

    async def test_auto_mode_never_writes_to_human_out(self) -> None:
        """Auto mode: never writes to human_out even for low-confidence questions."""
        human_out: asyncio.Queue[HumanQuery] = asyncio.Queue()
        human_in: asyncio.Queue[str] = asyncio.Queue()
        router = EscalationRouter(mode="auto", human_out=human_out, human_in=human_in)
        input_data = {"questions": [{"question": "Should I delete the table?"}]}
        await router.resolve(input_data)
        assert human_out.empty(), "Auto mode must never push to human_out"

    async def test_auto_mode_empty_questions_returns_allow(
        self, router: EscalationRouter
    ) -> None:
        """Auto mode: empty questions list -> PermissionResultAllow."""
        input_data = {"questions": []}
        result = await router.resolve(input_data)
        assert isinstance(result, PermissionResultAllow)

    async def test_auto_mode_logs_decision(self, router: EscalationRouter) -> None:
        """Auto mode: each resolution logs a DecisionLog via logging.info."""
        input_data = {"questions": [{"question": "Should I use async?"}]}
        with patch("conductor.orchestrator.escalation.logger") as mock_logger:
            await router.resolve(input_data)
            assert mock_logger.info.called, "Auto mode must log each decision"

    async def test_auto_mode_answers_in_updated_input(
        self, router: EscalationRouter
    ) -> None:
        """Auto mode: result.updated_input contains 'answers' key."""
        input_data = {"questions": [{"question": "Should I use async?"}]}
        result = await router.resolve(input_data)
        assert isinstance(result, PermissionResultAllow)
        assert "answers" in result.updated_input


# ---------------------------------------------------------------------------
# COMM-04: Interactive mode
# ---------------------------------------------------------------------------


class TestComm04InteractiveMode:
    async def test_interactive_high_confidence_no_human_out_write(self) -> None:
        """Interactive: high-confidence -> auto answer, no human_out write."""
        human_out: asyncio.Queue[HumanQuery] = asyncio.Queue()
        human_in: asyncio.Queue[str] = asyncio.Queue()
        router = EscalationRouter(
            mode="interactive", human_out=human_out, human_in=human_in
        )
        input_data = {"questions": [{"question": "Should I use async?"}]}
        result = await router.resolve(input_data)
        assert isinstance(result, PermissionResultAllow)
        assert human_out.empty(), "High-confidence questions must not escalate"

    async def test_interactive_low_confidence_writes_to_human_out(self) -> None:
        """Interactive: low-confidence -> HumanQuery pushed to human_out."""
        human_out: asyncio.Queue[HumanQuery] = asyncio.Queue()
        human_in: asyncio.Queue[str] = asyncio.Queue()

        router = EscalationRouter(
            mode="interactive",
            human_out=human_out,
            human_in=human_in,
            human_timeout=2.0,
        )

        # Pre-load human_in so the router doesn't time out
        await human_in.put("yes")

        input_data = {"questions": [{"question": "Should I delete the table?"}]}
        result = await router.resolve(input_data)

        assert isinstance(result, PermissionResultAllow)
        # human_out should have received the query
        assert not human_out.empty(), "Low-confidence question must be pushed to human_out"

    async def test_interactive_low_confidence_uses_human_answer(self) -> None:
        """Interactive: answer from human_in is used in the response."""
        human_out: asyncio.Queue[HumanQuery] = asyncio.Queue()
        human_in: asyncio.Queue[str] = asyncio.Queue()
        await human_in.put("confirmed by human")

        router = EscalationRouter(
            mode="interactive",
            human_out=human_out,
            human_in=human_in,
            human_timeout=2.0,
        )
        input_data = {"questions": [{"question": "Should I delete the table?"}]}
        result = await router.resolve(input_data)

        assert isinstance(result, PermissionResultAllow)
        # The human answer should appear somewhere in updated_input
        answers = result.updated_input.get("answers", {})
        assert any("confirmed by human" in str(v) for v in answers.values())

    async def test_interactive_low_confidence_timeout_fallback(self) -> None:
        """Interactive: if human_in times out, falls back to 'proceed'."""
        human_out: asyncio.Queue[HumanQuery] = asyncio.Queue()
        human_in: asyncio.Queue[str] = asyncio.Queue()  # empty — will time out

        router = EscalationRouter(
            mode="interactive",
            human_out=human_out,
            human_in=human_in,
            human_timeout=0.05,  # very short timeout
        )
        input_data = {"questions": [{"question": "Should I delete the table?"}]}
        result = await router.resolve(input_data)

        # Must not raise; must return PermissionResultAllow with fallback
        assert isinstance(result, PermissionResultAllow)
        answers = result.updated_input.get("answers", {})
        assert any("proceed" in str(v) for v in answers.values())

    async def test_interactive_no_queues_falls_back_to_auto(self) -> None:
        """Interactive mode with no queues: falls back to auto answer for all questions."""
        router = EscalationRouter(mode="interactive")  # no human_out/human_in
        input_data = {"questions": [{"question": "Should I delete the table?"}]}
        result = await router.resolve(input_data)
        assert isinstance(result, PermissionResultAllow)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TestDataModels:
    def test_human_query_has_required_fields(self) -> None:
        """HumanQuery dataclass has question, context, timestamp fields."""
        q = HumanQuery(question="foo?", context={"key": "val"}, timestamp="2026-01-01T00:00:00Z")
        assert q.question == "foo?"
        assert q.context == {"key": "val"}
        assert q.timestamp == "2026-01-01T00:00:00Z"

    def test_decision_log_has_required_fields(self) -> None:
        """DecisionLog dataclass has question, answer, confidence, rationale, timestamp."""
        d = DecisionLog(
            question="Should I proceed?",
            answer="proceed",
            confidence="high",
            rationale="benign question",
            timestamp="2026-01-01T00:00:00Z",
        )
        assert d.confidence == "high"
        assert d.answer == "proceed"
