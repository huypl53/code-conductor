"""EscalationRouter — routes sub-agent questions to auto or human answers.

COMM-03: In auto mode, all questions are answered autonomously with a 'proceed'
         default and each decision is logged as a DecisionLog entry.
COMM-04: In interactive mode, low-confidence questions are escalated via an
         asyncio.Queue pair (human_out / human_in).  High-confidence questions
         are auto-answered without escalation.  If the human does not respond
         within *human_timeout* seconds the router falls back to 'proceed'.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

if TYPE_CHECKING:
    from conductor.state.manager import StateManager

logger = logging.getLogger("conductor.orchestrator")

# ---------------------------------------------------------------------------
# Confidence heuristic
# ---------------------------------------------------------------------------

_LOW_CONFIDENCE_KEYWORDS: frozenset[str] = frozenset(
    {
        "delete",
        "drop",
        "remove",
        "irreversible",
        "cannot be undone",
        "production",
        "deploy",
        "billing",
        "secret",
        "credentials",
    }
)


def _is_low_confidence(question: str) -> bool:
    """Return True if *question* contains any low-confidence keyword.

    The check is case-insensitive.
    """
    lowered = question.lower()
    return any(kw in lowered for kw in _LOW_CONFIDENCE_KEYWORDS)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class HumanQuery:
    """A question pushed to the human_out queue for human review."""

    question: str
    context: dict
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class DecisionLog:
    """Audit record of an autonomous escalation decision."""

    question: str
    answer: str
    confidence: str  # "high" | "low"
    rationale: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# EscalationRouter
# ---------------------------------------------------------------------------


class EscalationRouter:
    """Routes sub-agent questions based on mode and confidence.

    Parameters
    ----------
    mode:
        ``"auto"`` — all questions answered autonomously, decisions logged.
        ``"interactive"`` — high-confidence questions auto-answered;
        low-confidence questions escalated to *human_out* / *human_in*.
    human_out:
        Queue where :class:`HumanQuery` objects are pushed for human review.
        Only used in ``interactive`` mode.
    human_in:
        Queue from which the human's text answer is read.
        Only used in ``interactive`` mode.
    human_timeout:
        Seconds to wait for a human answer before falling back to ``"proceed"``.
    state_manager:
        Optional :class:`~conductor.state.manager.StateManager` — not used
        directly in routing but available for future context enrichment.
    """

    def __init__(
        self,
        *,
        mode: str = "auto",
        human_out: asyncio.Queue[HumanQuery] | None = None,
        human_in: asyncio.Queue[str] | None = None,
        human_timeout: float = 120.0,
        state_manager: StateManager | None = None,
    ) -> None:
        self._mode = mode
        self._human_out = human_out
        self._human_in = human_in
        self._human_timeout = human_timeout
        self._state_manager = state_manager

    # ------------------------------------------------------------------
    # Public API — compatible with PermissionHandler._AnswerFn
    # ------------------------------------------------------------------

    async def resolve(
        self, input_data: dict
    ) -> PermissionResultAllow | PermissionResultDeny:
        """Answer all questions in *input_data* and return an Allow result.

        This method is intentionally typed as ``PermissionResultAllow |
        PermissionResultDeny`` to satisfy the ``_AnswerFn`` contract, but in
        practice it always returns
        :class:`~claude_agent_sdk.types.PermissionResultAllow` because the
        escalation router never denies — it either uses the human's answer or
        falls back to ``"proceed"``.
        """
        questions: list[dict] = input_data.get("questions", [])
        answers: dict[str, str] = {}

        for i, q_obj in enumerate(questions):
            question_text: str = q_obj.get("question", "")
            answer = await self._resolve_question(question_text)
            answers[str(i)] = answer

        # If there were no questions, still return an Allow with empty answers
        if not questions:
            logger.info(
                "EscalationRouter: no questions to answer (mode=%s)", self._mode
            )

        return PermissionResultAllow(updated_input={**input_data, "answers": answers})

    # ------------------------------------------------------------------
    # Internal routing
    # ------------------------------------------------------------------

    async def _resolve_question(self, question: str) -> str:
        """Route a single question to auto or human answer."""
        low_conf = _is_low_confidence(question)
        confidence = "low" if low_conf else "high"

        if self._mode == "auto":
            return self._auto_answer(question, confidence)

        # Interactive mode
        if low_conf and self._human_out is not None and self._human_in is not None:
            return await self._escalate_to_human(question)

        # Interactive + high confidence OR no queues available
        return self._auto_answer(question, confidence)

    def _auto_answer(self, question: str, confidence: str) -> str:
        """Return 'proceed' and log the decision."""
        rationale = (
            "Auto mode: all questions answered autonomously."
            if self._mode == "auto"
            else f"Interactive mode: {confidence}-confidence question auto-answered."
        )
        log = DecisionLog(
            question=question,
            answer="proceed",
            confidence=confidence,
            rationale=rationale,
        )
        logger.info(
            "EscalationRouter decision: question=%r confidence=%s "
            "answer=%s rationale=%s ts=%s",
            log.question,
            log.confidence,
            log.answer,
            log.rationale,
            log.timestamp,
        )
        return "proceed"

    async def _escalate_to_human(self, question: str) -> str:
        """Push question to human_out, await answer from human_in with timeout."""
        assert self._human_out is not None
        assert self._human_in is not None

        query = HumanQuery(
            question=question,
            context={},
        )
        await self._human_out.put(query)

        try:
            answer = await asyncio.wait_for(
                self._human_in.get(),
                timeout=self._human_timeout,
            )
            logger.info(
                "EscalationRouter: human answered question=%r answer=%r",
                question,
                answer,
            )
            return answer
        except TimeoutError:
            logger.info(
                "EscalationRouter: human did not answer within %.1fs, "
                "falling back to 'proceed' for question=%r",
                self._human_timeout,
                question,
            )
            return "proceed"
