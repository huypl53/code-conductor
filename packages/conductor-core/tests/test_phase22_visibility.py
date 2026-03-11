"""Tests for Phase 22: Sub-Agent Visibility and Escalation Bridge.

Covers:
- VISB-01: Live per-agent status display during delegation
- VISB-02: Escalation bridge — sub-agent questions displayed, user replies relayed

Test structure:
- Status updater starts and stops with delegation
- Status lines show agent progress
- Status lines removed after completion
- Escalation question displayed with agent ID prefix
- Escalation reply sent back via human_in
- Edge cases: no escalations, multiple escalations, delegation completes while
  escalation pending
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


def _make_state_with_agents(
    state_manager: StateManager,
    agent_specs: list[tuple[str, str, AgentStatus]],
) -> None:
    """Populate state with agents and tasks.

    agent_specs: list of (agent_id, task_title, agent_status)
    """

    def _populate(state: ConductorState) -> None:
        for i, (agent_id, task_title, status) in enumerate(agent_specs):
            task_id = f"task-{i}"
            state.tasks.append(
                Task(
                    id=task_id,
                    title=task_title,
                    description=f"Description for {task_title}",
                    status=TaskStatus.IN_PROGRESS,
                    assigned_agent=agent_id,
                )
            )
            state.agents.append(
                AgentRecord(
                    id=agent_id,
                    name=agent_id,
                    role="developer",
                    current_task_id=task_id,
                    status=status,
                )
            )

    state_manager.mutate(_populate)


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
# VISB-01: Live status display
# ---------------------------------------------------------------------------


class TestLiveStatusDisplay:
    """Tests for the per-agent status line updater (VISB-01)."""

    def test_print_live_status_shows_working_agents(
        self, tmp_path: Path
    ) -> None:
        """Status lines show working agents with task info."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)

        state_path = tmp_path / ".conductor" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_manager = StateManager(state_path)

        _make_state_with_agents(
            state_manager,
            [
                ("agent-abc", "Implement OAuth", AgentStatus.WORKING),
                ("agent-def", "Add tests", AgentStatus.WORKING),
            ],
        )

        from conductor.orchestrator.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=str(tmp_path),
        )
        run = _DelegationRun(
            task_description="Build auth",
            orchestrator=orchestrator,
            state_manager=state_manager,
            started_at=time.monotonic() - 5,
        )

        mgr._print_live_status(run)

        calls = [str(c) for c in console.print.call_args_list]
        # Should have printed status lines for both agents
        assert any("agent-abc" in c for c in calls), f"Expected agent-abc in output: {calls}"
        assert any("agent-def" in c for c in calls), f"Expected agent-def in output: {calls}"
        assert any("Implement OAuth" in c for c in calls)
        assert any("Add tests" in c for c in calls)

    def test_print_live_status_shows_waiting_agents(
        self, tmp_path: Path
    ) -> None:
        """WAITING agents are also shown in status lines."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)

        state_path = tmp_path / ".conductor" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_manager = StateManager(state_path)

        _make_state_with_agents(
            state_manager,
            [("agent-wait", "Waiting task", AgentStatus.WAITING)],
        )

        from conductor.orchestrator.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=str(tmp_path),
        )
        run = _DelegationRun(
            task_description="test",
            orchestrator=orchestrator,
            state_manager=state_manager,
        )

        mgr._print_live_status(run)

        calls = [str(c) for c in console.print.call_args_list]
        assert any("agent-wait" in c for c in calls)

    def test_print_live_status_no_agents(self, tmp_path: Path) -> None:
        """No status lines printed when no active agents."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)

        state_path = tmp_path / ".conductor" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_manager = StateManager(state_path)

        from conductor.orchestrator.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=str(tmp_path),
        )
        run = _DelegationRun(
            task_description="test",
            orchestrator=orchestrator,
            state_manager=state_manager,
        )

        mgr._print_live_status(run)
        assert mgr._last_status_line_count == 0

    def test_clear_status_lines_resets_count(self, tmp_path: Path) -> None:
        """_clear_status_lines uses ANSI escapes and resets counter."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)
        mgr._last_status_line_count = 3

        mgr._clear_status_lines()

        assert mgr._last_status_line_count == 0
        # Should have printed ANSI escape sequences
        assert console.print.call_count == 3

    def test_clear_status_lines_noop_when_zero(self, tmp_path: Path) -> None:
        """_clear_status_lines is a no-op when no lines to clear."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)
        mgr._last_status_line_count = 0

        mgr._clear_status_lines()

        assert console.print.call_count == 0

    @pytest.mark.asyncio
    async def test_status_updater_starts_and_stops(
        self, tmp_path: Path
    ) -> None:
        """Status updater task runs during delegation and is cancelled after."""
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
        self, tmp_path: Path
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

    def test_status_lines_removed_after_done_agents(
        self, tmp_path: Path
    ) -> None:
        """When agents move to DONE, status lines disappear on next update."""
        console = MagicMock()
        mgr = _make_manager(tmp_path, console=console)

        state_path = tmp_path / ".conductor" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_manager = StateManager(state_path)

        # First: add a working agent
        _make_state_with_agents(
            state_manager,
            [("agent-x", "Task X", AgentStatus.WORKING)],
        )

        from conductor.orchestrator.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=str(tmp_path),
        )
        run = _DelegationRun(
            task_description="test",
            orchestrator=orchestrator,
            state_manager=state_manager,
        )

        # Print status — should show 1 line
        mgr._print_live_status(run)
        assert mgr._last_status_line_count == 1

        # Now mark agent as DONE
        def _mark_done(state: ConductorState) -> None:
            for a in state.agents:
                if a.id == "agent-x":
                    a.status = AgentStatus.DONE

        state_manager.mutate(_mark_done)

        console.reset_mock()
        mgr._print_live_status(run)

        # Should have cleared previous lines and set count to 0
        assert mgr._last_status_line_count == 0


# ---------------------------------------------------------------------------
# VISB-02: Escalation bridge
# ---------------------------------------------------------------------------


class TestEscalationBridge:
    """Tests for the escalation bridge (VISB-02)."""

    @pytest.mark.asyncio
    async def test_escalation_question_displayed(
        self, tmp_path: Path
    ) -> None:
        """Escalation questions appear in chat with agent prefix."""
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

        # Verify the question was displayed
        calls = [str(c) for c in console.print.call_args_list]
        assert any(
            "Agent escalation" in c for c in calls
        ), f"Expected 'Agent escalation' prefix: {calls}"
        assert any(
            "delete the production database" in c for c in calls
        ), f"Expected question text: {calls}"

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
