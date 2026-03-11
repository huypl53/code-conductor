"""Tests for Phase 21: Smart Delegation and Orchestrator Integration.

Covers:
- DELG-01: Simple requests complete directly (no delegation)
- DELG-02: Complex requests trigger delegation announcement and sub-agents
- DELG-03: Delegation decision visible before work begins
- DELG-04: Dashboard URL included in delegation announcement
- SESS-03: /status shows active sub-agents or "No active agents"
- Delegate tool registration
- Fresh orchestrator per delegation
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.cli.delegation import (
    DEFAULT_DASHBOARD_URL,
    DELEGATION_SYSTEM_PROMPT_ADDENDUM,
    DelegationManager,
    _DelegationRun,
    create_delegate_tool,
    create_delegation_mcp_server,
)


# ---------------------------------------------------------------------------
# DelegationManager basics
# ---------------------------------------------------------------------------


class TestDelegationManager:
    """Unit tests for DelegationManager."""

    def _make_manager(
        self, tmp_path: Path, console: MagicMock | None = None
    ) -> DelegationManager:
        console = console or MagicMock()
        return DelegationManager(
            console=console,
            repo_path=str(tmp_path),
        )

    def test_initial_state(self, tmp_path: Path) -> None:
        mgr = self._make_manager(tmp_path)
        assert not mgr.is_delegating
        assert mgr.delegation_count == 0

    def test_custom_dashboard_url(self, tmp_path: Path) -> None:
        mgr = DelegationManager(
            console=MagicMock(),
            repo_path=str(tmp_path),
            dashboard_url="http://example.com:8080",
        )
        assert mgr._dashboard_url == "http://example.com:8080"

    # -- /status (SESS-03) --------------------------------------------------

    def test_status_no_active_agents(self, tmp_path: Path) -> None:
        """SESS-03: /status prints 'No active agents' when idle."""
        console = MagicMock()
        mgr = self._make_manager(tmp_path, console=console)
        mgr.print_status()
        calls = [str(c) for c in console.print.call_args_list]
        assert any("No active agents" in p for p in calls)

    def test_status_with_active_agents(self, tmp_path: Path) -> None:
        """SESS-03: /status shows table of active agents during delegation."""
        from conductor.state import StateManager
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        console = MagicMock()
        mgr = self._make_manager(tmp_path, console=console)

        # Set up state with active agents
        state_path = tmp_path / ".conductor" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_manager = StateManager(state_path)

        def add_data(state: ConductorState) -> None:
            state.tasks.append(
                Task(
                    id="task-1",
                    title="Implement OAuth",
                    description="Add OAuth login flow",
                    status=TaskStatus.IN_PROGRESS,
                    assigned_agent="agent-task-1-abc123",
                )
            )
            state.agents.append(
                AgentRecord(
                    id="agent-task-1-abc123",
                    name="agent-task-1-abc123",
                    role="developer",
                    current_task_id="task-1",
                    status=AgentStatus.WORKING,
                )
            )

        state_manager.mutate(add_data)

        # Simulate active delegation run
        from conductor.orchestrator.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=str(tmp_path),
        )
        mgr._active_run = _DelegationRun(
            task_description="Add OAuth login",
            orchestrator=orchestrator,
            state_manager=state_manager,
            started_at=time.monotonic() - 10,  # 10 seconds ago
        )

        mgr.print_status()

        # Should have printed a Rich Table (console.print called with a Table)
        calls = console.print.call_args_list
        assert len(calls) > 0
        # The table is passed as positional arg
        from rich.table import Table

        table_printed = any(
            isinstance(c.args[0], Table) if c.args else False
            for c in calls
        )
        assert table_printed, f"Expected a Rich Table, got: {calls}"

    def test_status_no_working_agents_shows_no_active(
        self, tmp_path: Path
    ) -> None:
        """When delegation is active but all agents are DONE, show no active."""
        from conductor.state import StateManager
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        console = MagicMock()
        mgr = self._make_manager(tmp_path, console=console)

        state_path = tmp_path / ".conductor" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_manager = StateManager(state_path)

        def add_data(state: ConductorState) -> None:
            state.agents.append(
                AgentRecord(
                    id="agent-1",
                    name="agent-1",
                    role="developer",
                    status=AgentStatus.DONE,
                )
            )

        state_manager.mutate(add_data)

        from conductor.orchestrator.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=str(tmp_path),
        )
        mgr._active_run = _DelegationRun(
            task_description="test",
            orchestrator=orchestrator,
            state_manager=state_manager,
        )

        mgr.print_status()
        calls = [str(c) for c in console.print.call_args_list]
        assert any("No active agents" in p for p in calls)


# ---------------------------------------------------------------------------
# Delegate tool handler
# ---------------------------------------------------------------------------


class TestDelegateHandler:
    """Tests for the delegate tool handler."""

    @pytest.mark.asyncio
    async def test_missing_task_returns_error(self, tmp_path: Path) -> None:
        """Delegate with empty task returns error."""
        console = MagicMock()
        mgr = DelegationManager(
            console=console, repo_path=str(tmp_path)
        )
        result = await mgr.handle_delegate({})
        assert result.get("is_error") is True
        assert "required" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_delegation_announcement_printed(
        self, tmp_path: Path
    ) -> None:
        """DELG-02, DELG-04: Delegation announcement with dashboard URL."""
        console = MagicMock()
        mgr = DelegationManager(
            console=console, repo_path=str(tmp_path)
        )

        # Mock the Orchestrator.run to avoid real SDK calls
        with patch(
            "conductor.cli.delegation.Orchestrator"
        ) as MockOrch:
            mock_orch_instance = MagicMock()
            mock_orch_instance.run = AsyncMock()
            MockOrch.return_value = mock_orch_instance

            result = await mgr.handle_delegate(
                {"task": "Add OAuth login"}
            )

        calls = [str(c) for c in console.print.call_args_list]
        # DELG-02: "Delegating to team..." announcement
        assert any("Delegating to team" in p for p in calls), (
            f"Expected 'Delegating to team' in output, got: {calls}"
        )
        # DELG-04: Dashboard URL in announcement
        assert any(DEFAULT_DASHBOARD_URL in p for p in calls), (
            f"Expected dashboard URL in output, got: {calls}"
        )
        # Completion announcement
        assert any("Delegation complete" in p for p in calls), (
            f"Expected completion message, got: {calls}"
        )
        # Tool result is success
        assert "is_error" not in result or not result.get("is_error")

    @pytest.mark.asyncio
    async def test_delegation_failure_handled(self, tmp_path: Path) -> None:
        """Delegation failure returns error result."""
        console = MagicMock()
        mgr = DelegationManager(
            console=console, repo_path=str(tmp_path)
        )

        with patch(
            "conductor.cli.delegation.Orchestrator"
        ) as MockOrch:
            mock_orch_instance = MagicMock()
            mock_orch_instance.run = AsyncMock(
                side_effect=RuntimeError("decomposition failed")
            )
            MockOrch.return_value = mock_orch_instance

            result = await mgr.handle_delegate(
                {"task": "broken task"}
            )

        assert result.get("is_error") is True
        assert "failed" in result["content"][0]["text"].lower()

    @pytest.mark.asyncio
    async def test_fresh_orchestrator_per_delegation(
        self, tmp_path: Path
    ) -> None:
        """Architecture decision #3: fresh Orchestrator each time."""
        console = MagicMock()
        mgr = DelegationManager(
            console=console, repo_path=str(tmp_path)
        )

        instances: list[Any] = []

        with patch(
            "conductor.cli.delegation.Orchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock()

            def capture_instance(*args: Any, **kwargs: Any) -> Any:
                inst = MagicMock()
                inst.run = AsyncMock()
                instances.append(inst)
                return inst

            MockOrch.side_effect = capture_instance

            await mgr.handle_delegate({"task": "task 1"})
            await mgr.handle_delegate({"task": "task 2"})

        assert len(instances) == 2
        assert instances[0] is not instances[1]

    @pytest.mark.asyncio
    async def test_delegation_count_increments(
        self, tmp_path: Path
    ) -> None:
        console = MagicMock()
        mgr = DelegationManager(
            console=console, repo_path=str(tmp_path)
        )

        with patch(
            "conductor.cli.delegation.Orchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock()
            MockOrch.return_value = mock_orch

            assert mgr.delegation_count == 0
            await mgr.handle_delegate({"task": "task 1"})
            assert mgr.delegation_count == 1
            await mgr.handle_delegate({"task": "task 2"})
            assert mgr.delegation_count == 2

    @pytest.mark.asyncio
    async def test_active_run_cleared_after_delegation(
        self, tmp_path: Path
    ) -> None:
        """Active run is None after delegation completes (success or failure)."""
        console = MagicMock()
        mgr = DelegationManager(
            console=console, repo_path=str(tmp_path)
        )

        with patch(
            "conductor.cli.delegation.Orchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.run = AsyncMock()
            MockOrch.return_value = mock_orch

            await mgr.handle_delegate({"task": "task 1"})

        assert mgr._active_run is None
        assert not mgr.is_delegating


# ---------------------------------------------------------------------------
# MCP tool and server creation
# ---------------------------------------------------------------------------


class TestDelegateToolCreation:
    """Tests for Delegate tool and MCP server factory."""

    def test_create_delegate_tool_returns_sdk_mcp_tool(
        self, tmp_path: Path
    ) -> None:
        """create_delegate_tool returns an SdkMcpTool."""
        from claude_agent_sdk import SdkMcpTool

        mgr = DelegationManager(
            console=MagicMock(), repo_path=str(tmp_path)
        )
        tool = create_delegate_tool(mgr)
        assert isinstance(tool, SdkMcpTool)
        assert tool.name == "conductor_delegate"

    def test_create_delegation_mcp_server_returns_config(
        self, tmp_path: Path
    ) -> None:
        """create_delegation_mcp_server returns an McpSdkServerConfig dict."""
        mgr = DelegationManager(
            console=MagicMock(), repo_path=str(tmp_path)
        )
        config = create_delegation_mcp_server(mgr)
        assert config["type"] == "sdk"
        assert config["name"] == "conductor-delegation"
        assert "instance" in config


# ---------------------------------------------------------------------------
# System prompt addendum
# ---------------------------------------------------------------------------


class TestDelegationSystemPrompt:
    """Tests for the delegation system prompt heuristics."""

    def test_prompt_mentions_delegate_tool(self) -> None:
        assert "conductor_delegate" in DELEGATION_SYSTEM_PROMPT_ADDENDUM

    def test_prompt_has_direct_handling_guidance(self) -> None:
        assert "handle directly" in DELEGATION_SYSTEM_PROMPT_ADDENDUM.lower()

    def test_prompt_has_delegation_guidance(self) -> None:
        assert "delegate" in DELEGATION_SYSTEM_PROMPT_ADDENDUM.lower()


# ---------------------------------------------------------------------------
# ChatSession integration
# ---------------------------------------------------------------------------


class TestChatSessionDelegation:
    """Tests for delegation integration in ChatSession."""

    def test_chat_session_has_delegation_manager(self) -> None:
        """ChatSession initializes a DelegationManager."""
        from conductor.cli.chat import ChatSession

        session = ChatSession(console=MagicMock())
        assert hasattr(session, "_delegation_manager")
        assert isinstance(session._delegation_manager, DelegationManager)

    @pytest.mark.asyncio
    async def test_status_command_uses_delegation_manager(self) -> None:
        """SESS-03: /status delegates to DelegationManager.print_status."""
        from conductor.cli.chat import ChatSession

        console = MagicMock()
        session = ChatSession(console=console)

        with patch.object(
            session._delegation_manager, "print_status"
        ) as mock_status:
            result = await session._handle_slash_command("/status")

        assert result is False
        mock_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_no_agents_message(self) -> None:
        """SESS-03: /status prints 'No active agents' when idle."""
        from conductor.cli.chat import ChatSession

        console = MagicMock()
        session = ChatSession(console=console)
        await session._handle_slash_command("/status")

        calls = [str(c) for c in console.print.call_args_list]
        assert any("No active agents" in p for p in calls)
