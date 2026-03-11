"""Smart delegation infrastructure for the interactive chat TUI.

Phase 21: DELG-01..04, SESS-03

Provides:
- A ``Delegate`` MCP tool that tells Claude to hand off complex tasks
  to a fresh Orchestrator sub-agent team.
- Delegation announcement formatting (dashboard URL, summary).
- Active-orchestrator tracking for ``/status`` queries.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from conductor.orchestrator.orchestrator import Orchestrator
from conductor.state import StateManager
from conductor.state.models import AgentStatus

logger = logging.getLogger("conductor.delegation")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_DASHBOARD_URL = "http://localhost:4173"

DELEGATION_SYSTEM_PROMPT_ADDENDUM = """\

## Delegation

You have access to a tool called `conductor_delegate`.

**When to handle directly (do NOT use conductor_delegate):**
- Single file edits, renames, small refactors
- Quick lookups, searches, or explanations
- Bug fixes contained to one or two files
- Adding or modifying a single test

**When to delegate (use conductor_delegate):**
- New features spanning multiple files or modules
- Large refactors across a codebase
- Adding entire subsystems (e.g. authentication, API layer)
- Tasks requiring coordinated changes across 3+ files

When you decide, state your decision before acting:
- For direct handling: briefly note you are handling it directly.
- For delegation: call the conductor_delegate tool with a clear task description.
"""

# ---------------------------------------------------------------------------
# Delegation state tracker
# ---------------------------------------------------------------------------


@dataclass
class _DelegationRun:
    """Tracks a single delegation invocation."""

    task_description: str
    orchestrator: Orchestrator
    state_manager: StateManager
    started_at: float = field(default_factory=time.monotonic)


class DelegationManager:
    """Manages delegation lifecycle for a ChatSession.

    Owns the ``Delegate`` MCP tool handler, tracks the active orchestrator
    for ``/status``, and formats delegation announcements.
    """

    def __init__(
        self,
        console: Console,
        repo_path: str,
        dashboard_url: str = DEFAULT_DASHBOARD_URL,
    ) -> None:
        self._console = console
        self._repo_path = repo_path
        self._dashboard_url = dashboard_url
        self._active_run: _DelegationRun | None = None
        self._delegation_count = 0

    # -- MCP tool handler ---------------------------------------------------

    async def handle_delegate(self, args: dict[str, Any]) -> dict[str, Any]:
        """Handle a ``conductor_delegate`` tool call from the SDK.

        Creates a fresh Orchestrator, prints the delegation announcement,
        runs the orchestration loop, and returns a summary as tool output.
        """
        task = args.get("task", "")
        if not task:
            return {
                "content": [{"type": "text", "text": "Error: 'task' parameter is required."}],
                "is_error": True,
            }

        self._delegation_count += 1

        # Delegation announcement (DELG-02, DELG-04)
        self._console.print(
            f"\n[bold magenta]Delegating to team...[/bold magenta]  "
            f"Dashboard: [link={self._dashboard_url}]{self._dashboard_url}[/link]"
        )

        # Fresh orchestrator per delegation (architecture decision #3)
        conductor_dir = Path(self._repo_path) / ".conductor"
        conductor_dir.mkdir(parents=True, exist_ok=True)
        state_path = conductor_dir / "state.json"
        state_manager = StateManager(state_path)
        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=self._repo_path,
            mode="auto",
        )

        run = _DelegationRun(
            task_description=task,
            orchestrator=orchestrator,
            state_manager=state_manager,
        )
        self._active_run = run

        try:
            await orchestrator.run(task)
            elapsed = time.monotonic() - run.started_at
            summary = (
                f"Delegation complete. Task: {task!r}. "
                f"Elapsed: {elapsed:.1f}s."
            )
            self._console.print(
                f"\n[bold green]Delegation complete[/bold green] ({elapsed:.1f}s)"
            )
            return {"content": [{"type": "text", "text": summary}]}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Delegation failed for task: %s", task)
            error_msg = f"Delegation failed: {exc}"
            self._console.print(f"\n[bold red]{error_msg}[/bold red]")
            return {
                "content": [{"type": "text", "text": error_msg}],
                "is_error": True,
            }
        finally:
            self._active_run = None

    # -- /status support (SESS-03) ------------------------------------------

    def print_status(self) -> None:
        """Print the status of active sub-agents, or 'No active agents'."""
        if self._active_run is None:
            self._console.print("[dim]No active agents[/dim]")
            return

        run = self._active_run
        now = time.monotonic()

        try:
            state = run.state_manager.read_state()
        except Exception:  # noqa: BLE001
            self._console.print("[dim]No active agents[/dim]")
            return

        # Filter to agents that are currently working
        active_agents = [
            a for a in state.agents
            if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)
        ]

        if not active_agents:
            self._console.print("[dim]No active agents[/dim]")
            return

        table = Table(title="Active Sub-Agents")
        table.add_column("Agent ID", style="cyan")
        table.add_column("Task", style="white")
        table.add_column("Elapsed", style="yellow")

        for agent in active_agents:
            # Find the task assigned to this agent
            task_desc = ""
            for task in state.tasks:
                if task.assigned_agent == agent.id:
                    task_desc = task.title or task.description[:60]
                    break

            # Elapsed time since delegation started
            elapsed = now - run.started_at
            elapsed_str = f"{elapsed:.0f}s"

            table.add_row(agent.id, task_desc, elapsed_str)

        self._console.print(table)

    # -- properties ---------------------------------------------------------

    @property
    def is_delegating(self) -> bool:
        """True when a delegation is currently in progress."""
        return self._active_run is not None

    @property
    def delegation_count(self) -> int:
        """Number of delegations triggered so far."""
        return self._delegation_count


# ---------------------------------------------------------------------------
# MCP tool + server factory
# ---------------------------------------------------------------------------


def create_delegate_tool(manager: DelegationManager) -> Any:
    """Create the ``conductor_delegate`` SdkMcpTool for registration.

    Returns an SdkMcpTool instance ready to be passed to
    ``create_sdk_mcp_server()``.
    """
    from claude_agent_sdk import tool

    @tool(
        "conductor_delegate",
        "Delegate a complex task to a team of sub-agents managed by the "
        "Conductor orchestrator. Use this for multi-file features, large "
        "refactors, or new subsystems. The task description should be a "
        "clear, self-contained specification of what needs to be built.",
        {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "A clear description of the complex task to delegate.",
                },
            },
            "required": ["task"],
        },
    )
    async def delegate(args: dict[str, Any]) -> dict[str, Any]:
        return await manager.handle_delegate(args)

    return delegate


def create_delegation_mcp_server(manager: DelegationManager) -> Any:
    """Create an in-process MCP server with the Delegate tool.

    Returns an McpSdkServerConfig for use in ClaudeAgentOptions.mcp_servers.
    """
    from claude_agent_sdk import create_sdk_mcp_server

    delegate_tool = create_delegate_tool(manager)
    return create_sdk_mcp_server(
        name="conductor-delegation",
        version="1.0.0",
        tools=[delegate_tool],
    )
