"""Tests for Phase 22: Sub-Agent Visibility and Escalation Bridge.

Covers:
- VISB-02: Escalation bridge — sub-agent questions displayed, user replies relayed

Note (Phase 31): Live status display methods (_status_updater, _print_live_status,
_clear_status_lines) were removed from DelegationManager as they corrupt the
Textual TUI renderer with ANSI cursor codes. Status display will be re-added
in Phase 35 via StateWatchWorker.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.cli.delegation import (
    DelegationManager,
    STATUS_UPDATE_INTERVAL,
    _DelegationRun,
)
from conductor.orchestrator.escalation import HumanQuery
from conductor.state import StateManager
from conductor.state.models import (
    AgentRecord,
    AgentStatus,
    ConductorState,
    Task,
    TaskStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(
    tmp_path: Path,
    console: MagicMock | None = None,
    input_fn: Any = None,
) -> DelegationManager:
    console = console or MagicMock()
    return DelegationManager(
        console=console,
        repo_path=str(tmp_path),
        input_fn=input_fn,
    )


# ---------------------------------------------------------------------------
# STATUS_UPDATE_INTERVAL constant
# ---------------------------------------------------------------------------


def test_status_update_interval_constant() -> None:
    """STATUS_UPDATE_INTERVAL constant is still exported for backward compat."""
    assert isinstance(STATUS_UPDATE_INTERVAL, float)
    assert STATUS_UPDATE_INTERVAL > 0


# ---------------------------------------------------------------------------
# VISB-01: Live status display methods removed in Phase 31
# ---------------------------------------------------------------------------


def test_status_updater_removed() -> None:
    """Phase 31: _status_updater was removed (replaced by StateWatchWorker in Phase 35)."""
    dm = DelegationManager(repo_path="/tmp")
    assert not hasattr(dm, "_status_updater"), (
        "_status_updater should have been removed in Phase 31"
    )


def test_clear_status_lines_removed() -> None:
    """Phase 31: _clear_status_lines was removed (ANSI codes corrupt Textual renderer)."""
    dm = DelegationManager(repo_path="/tmp")
    assert not hasattr(dm, "_clear_status_lines"), (
        "_clear_status_lines should have been removed in Phase 31"
    )


def test_print_live_status_removed() -> None:
    """Phase 31: _print_live_status was removed."""
    dm = DelegationManager(repo_path="/tmp")
    assert not hasattr(dm, "_print_live_status"), (
        "_print_live_status should have been removed in Phase 31"
    )


def test_last_status_line_count_removed() -> None:
    """Phase 31: _last_status_line_count was removed."""
    dm = DelegationManager(repo_path="/tmp")
    assert not hasattr(dm, "_last_status_line_count"), (
        "_last_status_line_count should have been removed in Phase 31"
    )


# ---------------------------------------------------------------------------
# VISB-01: Background task management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_updater_starts_and_stops(
    tmp_path: Path
) -> None:
    """Status task is None after delegation (no status_updater to start)."""
    console = MagicMock()
    mgr = _make_manager(tmp_path, console=console)

    with patch(
        "conductor.cli.delegation.Orchestrator"
    ) as MockOrch:
        mock_orch = MagicMock()
        mock_orch.run = AsyncMock()
        MockOrch.return_value = mock_orch

        await mgr.handle_delegate({"task": "build feature"})

    # After delegation completes, background tasks should be cancelled
    assert mgr._status_task is None
    assert mgr._escalation_task is None
    assert not mgr.is_delegating


@pytest.mark.asyncio
async def test_status_updater_cancelled_on_failure(
    tmp_path: Path
) -> None:
    """Background tasks are cleaned up even when delegation fails."""
    console = MagicMock()
    mgr = _make_manager(tmp_path, console=console)

    with patch(
        "conductor.cli.delegation.Orchestrator"
    ) as MockOrch:
        mock_orch = MagicMock()
        mock_orch.run = AsyncMock(side_effect=RuntimeError("boom"))
        MockOrch.return_value = mock_orch

        result = await mgr.handle_delegate({"task": "broken"})

    assert result.get("is_error") is True
    assert mgr._status_task is None
    assert mgr._escalation_task is None


# ---------------------------------------------------------------------------
# VISB-02: Escalation bridge
# ---------------------------------------------------------------------------


class TestEscalationBridge:
    """Tests for the escalation bridge (VISB-02)."""

    @pytest.mark.asyncio
    async def test_escalation_question_logged(
        self, tmp_path: Path
    ) -> None:
        """Escalation questions are processed by the escalation listener."""
        console = MagicMock()

        async def mock_input(prompt: str) -> str:
            return "yes, proceed"

        mgr = _make_manager(tmp_path, console=console, input_fn=mock_input)
        mgr._human_out = asyncio.Queue()
        mgr._human_in = asyncio.Queue()

        # Start the escalation listener
        listener = asyncio.create_task(mgr._escalation_listener())

        # Push an escalation question
        query = HumanQuery(
            question="Should I delete the production database?",
            context={},
        )
        await mgr._human_out.put(query)

        # Give the listener time to process
        await asyncio.sleep(0.1)

        # Cancel the listener
        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

        # Reply should be in human_in queue now (picked up before cancel)
        # The escalation was processed — listener did not crash

    @pytest.mark.asyncio
    async def test_escalation_reply_sent_back(
        self, tmp_path: Path
    ) -> None:
        """User reply is sent back through human_in queue."""
        console = MagicMock()

        async def mock_input(prompt: str) -> str:
            return "no, do not delete"

        mgr = _make_manager(tmp_path, console=console, input_fn=mock_input)
        mgr._human_out = asyncio.Queue()
        mgr._human_in = asyncio.Queue()

        listener = asyncio.create_task(mgr._escalation_listener())

        await mgr._human_out.put(
            HumanQuery(question="Delete files?", context={})
        )

        # Wait for the reply to appear on human_in
        reply = await asyncio.wait_for(mgr._human_in.get(), timeout=2.0)

        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

        assert reply == "no, do not delete"

    @pytest.mark.asyncio
    async def test_escalation_empty_reply_defaults_to_proceed(
        self, tmp_path: Path
    ) -> None:
        """Empty user input defaults to 'proceed'."""
        console = MagicMock()

        async def mock_input(prompt: str) -> str:
            return ""

        mgr = _make_manager(tmp_path, console=console, input_fn=mock_input)
        mgr._human_out = asyncio.Queue()
        mgr._human_in = asyncio.Queue()

        listener = asyncio.create_task(mgr._escalation_listener())

        await mgr._human_out.put(
            HumanQuery(question="Continue?", context={})
        )

        reply = await asyncio.wait_for(mgr._human_in.get(), timeout=2.0)

        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

        assert reply == "proceed"

    @pytest.mark.asyncio
    async def test_escalation_no_input_fn_defaults(
        self, tmp_path: Path
    ) -> None:
        """Without input_fn, escalation defaults to 'proceed with best judgment'."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console, input_fn=None)
        mgr._human_out = asyncio.Queue()
        mgr._human_in = asyncio.Queue()

        listener = asyncio.create_task(mgr._escalation_listener())

        await mgr._human_out.put(
            HumanQuery(question="How to proceed?", context={})
        )

        reply = await asyncio.wait_for(mgr._human_in.get(), timeout=2.0)

        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

        assert reply == "proceed with best judgment"

    @pytest.mark.asyncio
    async def test_multiple_escalations_handled(
        self, tmp_path: Path
    ) -> None:
        """Multiple escalation questions are handled sequentially."""
        console = MagicMock()
        call_count = 0

        async def mock_input(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"answer-{call_count}"

        mgr = _make_manager(tmp_path, console=console, input_fn=mock_input)
        mgr._human_out = asyncio.Queue()
        mgr._human_in = asyncio.Queue()

        listener = asyncio.create_task(mgr._escalation_listener())

        # Push two questions
        await mgr._human_out.put(
            HumanQuery(question="Question 1?", context={})
        )
        reply1 = await asyncio.wait_for(mgr._human_in.get(), timeout=2.0)

        await mgr._human_out.put(
            HumanQuery(question="Question 2?", context={})
        )
        reply2 = await asyncio.wait_for(mgr._human_in.get(), timeout=2.0)

        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

        assert reply1 == "answer-1"
        assert reply2 == "answer-2"

    @pytest.mark.asyncio
    async def test_escalation_keyboard_interrupt_defaults(
        self, tmp_path: Path
    ) -> None:
        """KeyboardInterrupt during input defaults to 'proceed'."""
        console = MagicMock()

        async def mock_input(prompt: str) -> str:
            raise KeyboardInterrupt

        mgr = _make_manager(tmp_path, console=console, input_fn=mock_input)
        mgr._human_out = asyncio.Queue()
        mgr._human_in = asyncio.Queue()

        listener = asyncio.create_task(mgr._escalation_listener())

        await mgr._human_out.put(
            HumanQuery(question="Question?", context={})
        )

        reply = await asyncio.wait_for(mgr._human_in.get(), timeout=2.0)

        listener.cancel()
        try:
            await listener
        except asyncio.CancelledError:
            pass

        assert reply == "proceed"

    @pytest.mark.asyncio
    async def test_no_escalation_listener_exits_without_queues(
        self, tmp_path: Path
    ) -> None:
        """Escalation listener returns immediately when no queues are set."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)
        mgr._human_out = None
        mgr._human_in = None

        # Should return immediately without error
        await mgr._escalation_listener()


# ---------------------------------------------------------------------------
# Integration: handle_delegate wires queues to orchestrator
# ---------------------------------------------------------------------------


class TestDelegationEscalationIntegration:
    """Tests that handle_delegate properly wires escalation queues."""

    @pytest.mark.asyncio
    async def test_orchestrator_receives_queues(
        self, tmp_path: Path
    ) -> None:
        """Orchestrator is constructed with human_out and human_in queues."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)

        captured_kwargs: dict[str, Any] = {}

        with patch(
            "conductor.cli.delegation.Orchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock()

            def capture(*args: Any, **kwargs: Any) -> Any:
                captured_kwargs.update(kwargs)
                return mock_orch

            MockOrch.side_effect = capture

            await mgr.handle_delegate({"task": "build feature"})

        assert "human_out" in captured_kwargs
        assert "human_in" in captured_kwargs
        assert captured_kwargs["human_out"] is not None
        assert captured_kwargs["human_in"] is not None
        assert captured_kwargs["mode"] == "interactive"

    @pytest.mark.asyncio
    async def test_queues_cleaned_up_after_delegation(
        self, tmp_path: Path
    ) -> None:
        """Queues are set to None after delegation completes."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)

        with patch(
            "conductor.cli.delegation.Orchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock()
            MockOrch.return_value = mock_orch

            await mgr.handle_delegate({"task": "build"})

        assert mgr._human_out is None
        assert mgr._human_in is None

    @pytest.mark.asyncio
    async def test_cancel_background_tasks_idempotent(
        self, tmp_path: Path
    ) -> None:
        """_cancel_background_tasks is safe to call when tasks are None."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)
        # Should not raise
        mgr._cancel_background_tasks()
        assert mgr._status_task is None
        assert mgr._escalation_task is None


# ---------------------------------------------------------------------------
# ChatSession wiring
# ---------------------------------------------------------------------------


class TestChatSessionEscalationWiring:
    """Tests that ChatSession wires the escalation input function."""

    def test_delegation_manager_has_input_fn(self) -> None:
        """ChatSession injects _escalation_input into DelegationManager."""
        from conductor.cli.chat import ChatSession

        session = ChatSession(console=MagicMock())
        mgr = session._delegation_manager
        assert mgr._input_fn is not None
        assert callable(mgr._input_fn)

    def test_input_fn_is_escalation_input(self) -> None:
        """The injected function is ChatSession._escalation_input."""
        from conductor.cli.chat import ChatSession

        session = ChatSession(console=MagicMock())
        mgr = session._delegation_manager
        # The bound method should be the session's _escalation_input
        assert mgr._input_fn.__func__ is ChatSession._escalation_input
