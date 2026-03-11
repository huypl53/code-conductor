"""Smart delegation infrastructure for the interactive chat TUI.

Phase 21: DELG-01..04, SESS-03
Phase 22: VISB-01 (live status display), VISB-02 (escalation bridge)

Provides:
- A ``Delegate`` MCP tool that tells Claude to hand off complex tasks
  to a fresh Orchestrator sub-agent team.
- Delegation announcement formatting (dashboard URL, summary).
- Active-orchestrator tracking for ``/status`` queries.
- Live per-agent status lines during delegation (VISB-01).
- Escalation bridge: sub-agent questions displayed in chat with agent ID
  prefix, user input collected and relayed back (VISB-02).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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

STATUS_UPDATE_INTERVAL = 2.0  # seconds between live status refreshes

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

    Phase 22 adds:
    - Live per-agent status display during delegation (VISB-01)
    - Escalation bridge for sub-agent questions (VISB-02)
    """

    def __init__(
        self,
        console: Console,
        repo_path: str,
        dashboard_url: str = DEFAULT_DASHBOARD_URL,
        input_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._console = console
        self._repo_path = repo_path
        self._dashboard_url = dashboard_url
        self._active_run: _DelegationRun | None = None
        self._delegation_count = 0
        # Phase 22: escalation bridge
        self._human_out: asyncio.Queue | None = None
        self._human_in: asyncio.Queue | None = None
        self._status_task: asyncio.Task | None = None
        self._escalation_task: asyncio.Task | None = None
        self._last_status_line_count = 0
        # Callable to collect user input for escalations (injected by ChatSession)
        self._input_fn = input_fn

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

        # Phase 22: Create escalation queues
        self._human_out = asyncio.Queue()
        self._human_in = asyncio.Queue()

        # Fresh orchestrator per delegation (architecture decision #3)
        conductor_dir = Path(self._repo_path) / ".conductor"
        conductor_dir.mkdir(parents=True, exist_ok=True)
        state_path = conductor_dir / "state.json"
        state_manager = StateManager(state_path)
        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=self._repo_path,
            mode="interactive",
            human_out=self._human_out,
            human_in=self._human_in,
        )

        run = _DelegationRun(
            task_description=task,
            orchestrator=orchestrator,
            state_manager=state_manager,
        )
        self._active_run = run

        # Phase 22: Start background tasks for status display and escalation
        self._status_task = asyncio.create_task(
            self._status_updater(run)
        )
        self._escalation_task = asyncio.create_task(
            self._escalation_listener()
        )

        try:
            await orchestrator.run(task)
            elapsed = time.monotonic() - run.started_at
            summary = (
                f"Delegation complete. Task: {task!r}. "
                f"Elapsed: {elapsed:.1f}s."
            )
            # Clear any remaining status lines
            self._clear_status_lines()
            self._console.print(
                f"\n[bold green]Delegation complete[/bold green] ({elapsed:.1f}s)"
            )
            return {"content": [{"type": "text", "text": summary}]}
        except Exception as exc:  # noqa: BLE001
            logger.exception("Delegation failed for task: %s", task)
            error_msg = f"Delegation failed: {exc}"
            self._clear_status_lines()
            self._console.print(f"\n[bold red]{error_msg}[/bold red]")
            return {
                "content": [{"type": "text", "text": error_msg}],
                "is_error": True,
            }
        finally:
            # Cancel background tasks
            self._cancel_background_tasks()
            self._active_run = None
            self._human_out = None
            self._human_in = None

    # -- Resume delegation ---------------------------------------------------

    async def resume_delegation(self) -> None:
        """Resume interrupted delegation by calling orchestrator.resume()."""
        conductor_dir = Path(self._repo_path) / ".conductor"
        state_path = conductor_dir / "state.json"

        if not state_path.exists():
            self._console.print("[yellow]No state file found — nothing to resume.[/yellow]")
            return

        state_manager = StateManager(state_path)
        state = state_manager.read_state()

        incomplete = [t for t in state.tasks if t.status != "completed"]
        if not incomplete:
            self._console.print("[green]All tasks already completed — nothing to resume.[/green]")
            return

        total = len(state.tasks)
        done = total - len(incomplete)
        self._console.print(
            f"\n[bold cyan]Resuming delegation...[/bold cyan] "
            f"{done}/{total} tasks completed, {len(incomplete)} remaining."
        )

        # Create escalation queues
        self._human_out = asyncio.Queue()
        self._human_in = asyncio.Queue()

        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=self._repo_path,
            mode="interactive",
            human_out=self._human_out,
            human_in=self._human_in,
        )

        run = _DelegationRun(
            task_description="(resumed)",
            orchestrator=orchestrator,
            state_manager=state_manager,
        )
        self._active_run = run

        # Start background status + escalation tasks
        self._status_task = asyncio.create_task(self._status_updater(run))
        if self._input_fn is not None:
            self._escalation_task = asyncio.create_task(self._escalation_listener())

        try:
            await orchestrator.resume()

            state = state_manager.read_state()
            done = sum(1 for t in state.tasks if t.status == "completed")
            self._console.print(
                f"\n[bold green]Delegation complete.[/bold green] "
                f"{done}/{len(state.tasks)} tasks finished."
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Resume failed")
            self._console.print(f"\n[red]Resume failed: {exc}[/red]")
        finally:
            self._cancel_background_tasks()
            self._active_run = None

    # -- Phase 22: Live status display (VISB-01) ----------------------------

    async def _status_updater(self, run: _DelegationRun) -> None:
        """Background task that periodically prints per-agent status lines.

        Runs every STATUS_UPDATE_INTERVAL seconds while delegation is active.
        Uses ANSI escape codes to overwrite previous status lines so the
        display stays compact.
        """
        try:
            while True:
                await asyncio.sleep(STATUS_UPDATE_INTERVAL)
                self._print_live_status(run)
        except asyncio.CancelledError:
            # Clean up status lines on cancellation
            self._clear_status_lines()

    def _print_live_status(self, run: _DelegationRun) -> None:
        """Print per-agent status lines, overwriting previous output."""
        try:
            state = run.state_manager.read_state()
        except Exception:  # noqa: BLE001
            return

        active_agents = [
            a for a in state.agents
            if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)
        ]

        # Clear previous status lines
        self._clear_status_lines()

        if not active_agents:
            self._last_status_line_count = 0
            return

        now = time.monotonic()
        lines: list[str] = []

        for agent in active_agents:
            # Find the task assigned to this agent
            task_desc = ""
            for task in state.tasks:
                if task.assigned_agent == agent.id:
                    task_desc = task.title or task.description[:60]
                    break

            elapsed = now - run.started_at
            status_icon = "..." if agent.status == AgentStatus.WORKING else "?"
            agent_short = agent.id
            # Shorten agent ID for display if it's very long
            if len(agent_short) > 30:
                agent_short = agent_short[:27] + "..."

            lines.append(
                f"  [{status_icon}] {agent_short}: {task_desc} ({elapsed:.0f}s)"
            )

        for line in lines:
            self._console.print(f"[dim]{line}[/dim]")

        self._last_status_line_count = len(lines)

    def _clear_status_lines(self) -> None:
        """Clear previously printed status lines using ANSI escape codes."""
        if self._last_status_line_count > 0:
            # Move cursor up and clear each line
            for _ in range(self._last_status_line_count):
                self._console.print("\033[A\033[2K", end="")
            self._last_status_line_count = 0

    # -- Phase 22: Escalation bridge (VISB-02) ------------------------------

    async def _escalation_listener(self) -> None:
        """Background task that monitors human_out for escalation questions.

        When a sub-agent escalates a question, it is displayed in the chat
        prefixed with the agent ID. User input is collected and sent back
        via human_in.
        """
        if self._human_out is None or self._human_in is None:
            return

        try:
            while True:
                # Wait for an escalation question
                human_query = await self._human_out.get()
                question = human_query.question

                # Display the escalation question prefixed with agent context
                self._clear_status_lines()
                self._console.print(
                    f"\n[bold yellow]Agent escalation:[/bold yellow] {question}"
                )

                # Collect user input
                answer = await self._collect_escalation_input()

                # Send the answer back
                if self._human_in is not None:
                    await self._human_in.put(answer)

        except asyncio.CancelledError:
            pass

    async def _collect_escalation_input(self) -> str:
        """Collect user input for an escalation question.

        Uses the injected input_fn if available (from ChatSession's
        prompt_toolkit session), otherwise falls back to a default answer.
        """
        if self._input_fn is not None:
            try:
                answer = await self._input_fn("  Reply> ")
                return answer.strip() if answer else "proceed"
            except (EOFError, KeyboardInterrupt):
                return "proceed"
        # Fallback if no input function is available
        return "proceed with best judgment"

    # -- Background task management -----------------------------------------

    def _cancel_background_tasks(self) -> None:
        """Cancel the status updater and escalation listener tasks."""
        if self._status_task is not None and not self._status_task.done():
            self._status_task.cancel()
        if self._escalation_task is not None and not self._escalation_task.done():
            self._escalation_task.cancel()
        self._status_task = None
        self._escalation_task = None

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
