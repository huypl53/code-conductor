"""Interactive chat TUI for conductor.

Provides a REPL-style chat interface using prompt_toolkit for async input,
in-memory history, multi-line paste support, and slash command dispatch.

Actual Claude SDK integration is deferred to Phase 19 — this module provides
the input/output infrastructure with a placeholder response handler.
"""

from __future__ import annotations

import asyncio
import enum
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

# ---------------------------------------------------------------------------
# Slash-command registry
# ---------------------------------------------------------------------------

SLASH_COMMANDS: dict[str, str] = {
    "/help": "Show all available slash commands",
    "/exit": "Exit the chat session and restore terminal",
    "/status": "Show current orchestrator status (placeholder)",
}


# ---------------------------------------------------------------------------
# Ctrl+C state machine
# ---------------------------------------------------------------------------


class _CtrlCState(enum.Enum):
    """Tracks whether the user is idle at the prompt or a task is running."""

    IDLE = "idle"
    RUNNING = "running"


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------


class ChatSession:
    """Interactive chat REPL powered by prompt_toolkit.

    Lifecycle::

        session = ChatSession()
        await session.run()   # blocks until /exit or double Ctrl+C
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()
        self._history = InMemoryHistory()
        self._prompt_session: PromptSession[str] = PromptSession(
            history=self._history,
            multiline=False,
            # prompt_toolkit auto-detects paste (bracketed paste) and won't
            # submit on newline inside a pasted block.
            enable_open_in_editor=False,
        )
        self._state = _CtrlCState.IDLE
        self._running_task: asyncio.Task[Any] | None = None

    # -- public API ---------------------------------------------------------

    async def run(self) -> None:
        """Main REPL loop.  Exits on /exit or double Ctrl+C at idle prompt."""
        self._console.print(
            "[bold cyan]Conductor[/bold cyan] interactive session. "
            "Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit."
        )

        try:
            with patch_stdout():
                while True:
                    try:
                        self._state = _CtrlCState.IDLE
                        text = await self._prompt_session.prompt_async(
                            "conductor> ",
                        )
                    except KeyboardInterrupt:
                        # Ctrl+C while idle — exit
                        self._console.print("\nExiting.")
                        return
                    except EOFError:
                        # Ctrl+D
                        self._console.print("\nExiting.")
                        return

                    text = text.strip()
                    if not text:
                        continue

                    # Slash command?
                    if text.startswith("/"):
                        should_exit = self._handle_slash_command(text)
                        if should_exit:
                            return
                        continue

                    # Regular input — send to placeholder handler
                    await self._handle_input(text)
        finally:
            # Ensure terminal is restored even on unexpected errors
            self._cancel_running_task()

    # -- slash commands -----------------------------------------------------

    def _handle_slash_command(self, text: str) -> bool:
        """Dispatch a slash command.  Returns True if the session should exit."""
        cmd = text.split()[0].lower()

        if cmd == "/help":
            self._print_help()
            return False

        if cmd == "/exit":
            self._console.print("Goodbye.")
            return True

        if cmd == "/status":
            self._console.print("[dim]Status: no agents running (placeholder)[/dim]")
            return False

        self._console.print(
            f"[red]Unknown command:[/red] {cmd}. Type /help for available commands."
        )
        return False

    def _print_help(self) -> None:
        self._console.print("[bold]Available commands:[/bold]")
        for cmd, desc in SLASH_COMMANDS.items():
            self._console.print(f"  [cyan]{cmd:<12}[/cyan] {desc}")

    # -- input handling (placeholder) ---------------------------------------

    async def _handle_input(self, text: str) -> None:
        """Process a user message.  Placeholder: echoes back.

        Wraps the processing in an asyncio.Task so that Ctrl+C during
        processing cancels the task rather than exiting immediately.
        """
        self._state = _CtrlCState.RUNNING
        self._running_task = asyncio.create_task(self._process_message(text))

        try:
            await asyncio.shield(self._wait_for_task())
        except KeyboardInterrupt:
            # First Ctrl+C while running — cancel the task
            self._cancel_running_task()
            self._console.print("\n[yellow]Cancelled.[/yellow]")
        except asyncio.CancelledError:
            self._cancel_running_task()
            self._console.print("\n[yellow]Cancelled.[/yellow]")
        finally:
            self._state = _CtrlCState.IDLE
            self._running_task = None

    async def _wait_for_task(self) -> None:
        """Wait for the running task, converting Ctrl+C to cancellation."""
        if self._running_task is None:
            return
        try:
            await self._running_task
        except asyncio.CancelledError:
            pass

    async def _process_message(self, text: str) -> None:
        """Placeholder message processor.  Will be replaced by SDK call in Phase 19."""
        # Simulate a tiny delay so cancellation can be tested
        await asyncio.sleep(0.05)
        self._console.print(f"[dim](echo)[/dim] {text}")

    # -- helpers ------------------------------------------------------------

    def _cancel_running_task(self) -> None:
        if self._running_task is not None and not self._running_task.done():
            self._running_task.cancel()
