"""Interactive chat TUI for conductor.

Provides a REPL-style chat interface using prompt_toolkit for async input,
in-memory history, multi-line paste support, and slash command dispatch.

Phase 19 adds:
- CHAT-02: Streaming token display via ClaudeSDKClient
- CHAT-06: Human-readable tool activity lines
- CHAT-07: Working indicator (spinner) before first token
- CHAT-08: Context utilization warning with /summarize option
- SESS-05: Crash-safe chat history persistence

Phase 20 adds:
- SESS-04: Session resumption with interactive session picker

Phase 21 adds:
- DELG-01..04: Smart delegation via Delegate MCP tool
- SESS-03: /status shows active sub-agents
"""

from __future__ import annotations

import asyncio
import enum
import os
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console

from conductor.cli.chat_persistence import ChatHistoryStore
from conductor.cli.stream_display import (
    ContextTracker,
    format_tool_activity,
)

# ---------------------------------------------------------------------------
# Slash-command registry
# ---------------------------------------------------------------------------

SLASH_COMMANDS: dict[str, str] = {
    "/help": "Show all available slash commands",
    "/exit": "Exit the chat session and restore terminal",
    "/status": "Show active sub-agents (ID, task, elapsed time)",
    "/summarize": "Summarize conversation to free context space",
    "/resume": "Resume interrupted delegation from state.json",
}


# ---------------------------------------------------------------------------
# Ctrl+C state machine
# ---------------------------------------------------------------------------


class _CtrlCState(enum.Enum):
    """Tracks whether the user is idle at the prompt or a task is running."""

    IDLE = "idle"
    RUNNING = "running"


# ---------------------------------------------------------------------------
# Session picker (SESS-04)
# ---------------------------------------------------------------------------


def pick_session(cwd: str | None = None, console: Console | None = None) -> str | None:
    """Show a numbered list of recent sessions and let the user pick one.

    Returns the selected session_id, or None if no sessions or cancelled.
    """
    _console = console or Console(force_terminal=True)
    working_dir = cwd or os.getcwd()
    conductor_dir = Path(working_dir) / ".conductor"

    sessions = ChatHistoryStore.load_sessions(conductor_dir)
    if not sessions:
        _console.print("[yellow]No previous sessions found.[/yellow]")
        return None

    # Show last 10 sessions
    recent = sessions[:10]

    _console.print("[bold]Recent sessions:[/bold]")
    _console.print()

    for i, s in enumerate(recent, 1):
        ts = s["created_at"]
        # Truncate ISO timestamp to readable form
        if "T" in ts:
            ts = ts.replace("T", " ")[:19]
        first_prompt = s.get("first_prompt", "")
        if len(first_prompt) > 60:
            first_prompt = first_prompt[:57] + "..."
        if not first_prompt:
            first_prompt = "(empty session)"
        turn_count = s.get("turn_count", 0)
        _console.print(
            f"  [cyan]{i:>2}.[/cyan] {ts}  "
            f"[dim]({turn_count} turn{'s' if turn_count != 1 else ''})[/dim]  "
            f"{first_prompt}"
        )

    _console.print()

    try:
        choice = input("Select session number (or Enter to cancel): ").strip()
    except (KeyboardInterrupt, EOFError):
        _console.print()
        return None

    if not choice:
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(recent):
            return recent[idx]["session_id"]
        _console.print("[red]Invalid selection.[/red]")
        return None
    except ValueError:
        _console.print("[red]Invalid selection.[/red]")
        return None


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------


class ChatSession:
    """Interactive chat REPL powered by prompt_toolkit.

    Lifecycle::

        session = ChatSession()
        await session.run()   # blocks until /exit or double Ctrl+C
    """

    def __init__(
        self,
        console: Console | None = None,
        cwd: str | None = None,
        resume_session_id: str | None = None,
    ) -> None:
        # force_terminal=True so Rich ANSI output works inside patch_stdout()
        self._console = console or Console(force_terminal=True)
        self._history = InMemoryHistory()

        # Vim mode + Ctrl+G to open $EDITOR (like Claude Code)
        kb = KeyBindings()

        @kb.add("c-g")
        def _open_editor(event: Any) -> None:
            """Open current input in $EDITOR via Ctrl+G."""
            event.current_buffer.open_in_editor()

        self._prompt_session: PromptSession[str] = PromptSession(
            history=self._history,
            multiline=False,
            vi_mode=True,
            enable_open_in_editor=True,
            key_bindings=kb,
        )
        self._state = _CtrlCState.IDLE
        self._running_task: asyncio.Task[Any] | None = None

        # SDK client (lazy-initialized on first message)
        self._sdk_client: Any | None = None
        self._sdk_connected = False
        self._cwd = cwd or os.getcwd()
        self._resume_session_id = resume_session_id

        # Context tracking (CHAT-08)
        self._context_tracker = ContextTracker()

        # Delegation manager (Phase 21: DELG-01..04, SESS-03)
        # Phase 22: Wire escalation input via prompt_toolkit prompt_async
        from conductor.cli.delegation import DelegationManager

        self._delegation_manager = DelegationManager(
            console=self._console,
            repo_path=self._cwd,
            input_fn=self._escalation_input,
        )

        # Chat history persistence (SESS-05 / SESS-04)
        self._conductor_dir = Path(self._cwd) / ".conductor"
        self._conductor_dir.mkdir(parents=True, exist_ok=True)
        self._history_store = ChatHistoryStore(
            self._conductor_dir,
            resume_id=resume_session_id,
        )

    # -- public API ---------------------------------------------------------

    async def run(self) -> None:
        """Main REPL loop.  Exits on /exit or double Ctrl+C at idle prompt."""
        self._console.print(
            "[bold cyan]Conductor[/bold cyan] interactive session. "
            "Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit."
        )

        # SESS-04: Replay prior conversation history when resuming
        if self._resume_session_id is not None:
            self._replay_history()

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
                        should_exit = await self._handle_slash_command(text)
                        if should_exit:
                            return
                        continue

                    # Regular input — send to SDK
                    await self._handle_input(text)
        finally:
            # Ensure terminal is restored even on unexpected errors
            self._cancel_running_task()
            await self._disconnect_sdk()

    # -- slash commands -----------------------------------------------------

    async def _handle_slash_command(self, text: str) -> bool:
        """Dispatch a slash command.  Returns True if the session should exit."""
        cmd = text.split()[0].lower()

        if cmd == "/help":
            self._print_help()
            return False

        if cmd == "/exit":
            self._console.print("Goodbye.")
            return True

        if cmd == "/status":
            self._delegation_manager.print_status()
            return False

        if cmd == "/summarize":
            await self._handle_summarize()
            return False

        if cmd == "/resume":
            await self._delegation_manager.resume_delegation()
            return False

        self._console.print(
            f"[red]Unknown command:[/red] {cmd}. Type /help for available commands."
        )
        return False

    def _print_help(self) -> None:
        self._console.print("[bold]Available commands:[/bold]")
        for cmd, desc in SLASH_COMMANDS.items():
            self._console.print(f"  [cyan]{cmd:<12}[/cyan] {desc}")

    # -- SDK connection -----------------------------------------------------

    async def _ensure_sdk_connected(self) -> None:
        """Lazily connect the ClaudeSDKClient on first use."""
        if self._sdk_connected:
            return

        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

        from conductor.cli.delegation import (
            DELEGATION_SYSTEM_PROMPT_ADDENDUM,
            create_delegation_mcp_server,
        )

        # Phase 21: Create delegation MCP server with the Delegate tool
        delegation_server = create_delegation_mcp_server(
            self._delegation_manager
        )

        options = ClaudeAgentOptions(
            cwd=self._cwd,
            permission_mode="bypassPermissions",
            include_partial_messages=True,
            resume=self._resume_session_id,
            setting_sources=["project"],
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": DELEGATION_SYSTEM_PROMPT_ADDENDUM,
            },
            mcp_servers={"conductor-delegation": delegation_server},
            allowed_tools=["conductor_delegate"],
        )

        self._sdk_client = ClaudeSDKClient(options=options)
        await self._sdk_client.connect()
        self._sdk_connected = True

    async def _disconnect_sdk(self) -> None:
        """Disconnect the SDK client if connected."""
        if self._sdk_client is not None and self._sdk_connected:
            try:
                await self._sdk_client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._sdk_connected = False

    # -- input handling -----------------------------------------------------

    async def _handle_input(self, text: str) -> None:
        """Process a user message via the Claude SDK.

        Wraps the processing in an asyncio.Task so that Ctrl+C during
        processing cancels the task rather than exiting immediately.
        """
        self._state = _CtrlCState.RUNNING
        self._running_task = asyncio.create_task(self._process_message(text))

        try:
            await asyncio.shield(self._wait_for_task())
        except KeyboardInterrupt:
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
        """Send a message to the Claude SDK and stream the response.

        Implements:
        - CHAT-07: Working indicator before first token
        - CHAT-02: Incremental token streaming
        - CHAT-06: Human-readable tool activity lines
        - CHAT-08: Context usage warning
        - SESS-05: Chat history persistence
        """
        from claude_agent_sdk import (
            AssistantMessage,
            ResultMessage,
            SystemMessage,
        )
        from claude_agent_sdk.types import StreamEvent, TextBlock, ToolUseBlock

        # Persist user turn
        self._history_store.save_turn("user", text)

        # Connect SDK if needed
        try:
            await self._ensure_sdk_connected()
        except Exception as exc:  # noqa: BLE001
            self._console.print(f"[red]Failed to connect to Claude: {exc}[/red]")
            return

        # Send the query
        await self._sdk_client.query(text)

        # CHAT-07: Show working indicator
        self._console.print("[dim]Thinking...[/dim]", end="")
        first_token_received = False
        response_text_parts: list[str] = []
        total_tokens = 0

        # Stream response messages
        async for message in self._sdk_client.receive_response():
            if isinstance(message, StreamEvent):
                # Handle partial streaming events (CHAT-02)
                event = message.event
                event_type = event.get("type", "")

                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    delta_type = delta.get("type", "")

                    if delta_type == "text_delta":
                        chunk = delta.get("text", "")
                        if chunk:
                            if not first_token_received:
                                # Clear the "Thinking..." indicator
                                self._console.print(
                                    "\r" + " " * 20 + "\r", end=""
                                )
                                first_token_received = True
                            self._console.print(chunk, end="")
                            response_text_parts.append(chunk)

            elif isinstance(message, AssistantMessage):
                # Full message blocks (when partial streaming is not active,
                # or final consolidated message)
                for block in message.content:
                    if isinstance(block, TextBlock):
                        if not first_token_received:
                            self._console.print(
                                "\r" + " " * 20 + "\r", end=""
                            )
                            first_token_received = True
                        self._console.print(block.text, end="")
                        response_text_parts.append(block.text)

                    elif isinstance(block, ToolUseBlock):
                        # CHAT-06: Human-readable tool activity line
                        activity = format_tool_activity(
                            block.name, block.input
                        )
                        if activity:
                            if not first_token_received:
                                self._console.print(
                                    "\r" + " " * 20 + "\r", end=""
                                )
                                first_token_received = True
                            self._console.print(
                                f"\n[dim italic]{activity}[/dim italic]"
                            )

            elif isinstance(message, SystemMessage):
                # System messages (task progress, etc.) — no-op for now
                pass

            elif isinstance(message, ResultMessage):
                # Final result — extract usage for context tracking
                if message.usage:
                    self._context_tracker.update(message.usage)
                    total_tokens = message.usage.get(
                        "input_tokens", 0
                    ) + message.usage.get("output_tokens", 0)

        # End the streamed output with a newline
        if first_token_received:
            self._console.print()
        else:
            # No tokens received — clear the spinner
            self._console.print("\r" + " " * 20 + "\r", end="")
            self._console.print("[dim](No response)[/dim]")

        # SESS-05: Persist assistant turn
        response_content = "".join(response_text_parts)
        self._history_store.save_turn(
            "assistant", response_content, token_count=total_tokens
        )

        # CHAT-08: Context utilization warning
        if self._context_tracker.should_warn():
            pct = int(self._context_tracker.utilization * 100)
            self._console.print(
                f"\n[bold yellow]Warning:[/bold yellow] Context is ~{pct}% full. "
                "Use [bold]/summarize[/bold] to compress the conversation and "
                "continue with more room."
            )

    # -- /summarize ---------------------------------------------------------

    async def _handle_summarize(self) -> None:
        """Ask the SDK to summarize the conversation to free context."""
        if not self._sdk_connected or self._sdk_client is None:
            self._console.print(
                "[dim]No active conversation to summarize.[/dim]"
            )
            return

        self._console.print("[dim]Summarizing conversation...[/dim]")

        try:
            from claude_agent_sdk import ResultMessage
            from claude_agent_sdk.types import StreamEvent, TextBlock

            summarize_prompt = (
                "Please provide a concise summary of our conversation so far, "
                "capturing all key decisions, code changes, and context needed "
                "to continue effectively. Format as a brief bullet-point list."
            )
            await self._sdk_client.query(summarize_prompt)

            summary_parts: list[str] = []
            async for message in self._sdk_client.receive_response():
                if isinstance(message, StreamEvent):
                    event = message.event
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            if chunk:
                                self._console.print(chunk, end="")
                                summary_parts.append(chunk)
                elif isinstance(message, ResultMessage):
                    if message.usage:
                        self._context_tracker.update(message.usage)
                    break

            self._console.print()
            self._context_tracker.reset_warning()
            self._console.print(
                "[green]Context summarized. You can continue the conversation.[/green]"
            )

            # Persist summary turn
            summary = "".join(summary_parts)
            self._history_store.save_turn(
                "assistant", f"[Summary] {summary}", token_count=0
            )

        except Exception as exc:  # noqa: BLE001
            self._console.print(f"[red]Summarization failed: {exc}[/red]")

    # -- session resumption (SESS-04) --------------------------------------

    def _replay_history(self) -> None:
        """Display all prior turns from a resumed session."""
        session_data = ChatHistoryStore.load_session(
            self._conductor_dir, self._resume_session_id
        )
        if session_data is None:
            self._console.print(
                f"[yellow]Session '{self._resume_session_id}' not found.[/yellow]"
            )
            return

        turns = session_data.get("turns", [])
        if not turns:
            self._console.print("[dim]No conversation history to restore.[/dim]")
            return

        self._console.print(
            f"[dim]Resuming session {self._resume_session_id} "
            f"({len(turns)} turn{'s' if len(turns) != 1 else ''})...[/dim]"
        )
        self._console.print()

        for turn in turns:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            if role == "user":
                self._console.print(f"[bold green]You:[/bold green] {content}")
            elif role == "assistant":
                self._console.print(f"[bold cyan]Assistant:[/bold cyan] {content}")
            else:
                self._console.print(f"[dim]{role}: {content}[/dim]")

        self._console.print()
        self._console.print("[dim]--- End of history ---[/dim]")
        self._console.print()

    # -- Phase 22: escalation input ----------------------------------------

    async def _escalation_input(self, prompt_text: str = "  Reply> ") -> str:
        """Collect user input for a sub-agent escalation question.

        Uses the prompt_toolkit PromptSession to collect input asynchronously,
        which works correctly within the patch_stdout() context.
        """
        return await self._prompt_session.prompt_async(prompt_text)

    # -- helpers ------------------------------------------------------------

    def _cancel_running_task(self) -> None:
        if self._running_task is not None and not self._running_task.done():
            self._running_task.cancel()
