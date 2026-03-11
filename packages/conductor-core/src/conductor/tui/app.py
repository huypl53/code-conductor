"""ConductorApp -- Textual App root for Conductor v2.0.

Phase 31: Minimal skeleton -- event loop ownership, lifecycle, background task
          reference tracking. No widgets beyond a placeholder label.
Phase 32: Full two-column layout (TranscriptPane, CommandInput, StatusFooter,
          AgentMonitorPane) replaces the placeholder.
Phase 33: SDK streaming integration -- @work coroutine routes tokens to
          AssistantCell, input disable/enable lifecycle, StatusFooter updates.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding

logger = logging.getLogger("conductor.tui")


class ConductorApp(App):
    """Textual application root.

    Owns the asyncio event loop. All async subsystems (SDK streaming,
    uvicorn dashboard server, orchestrator delegation) launch as workers
    or asyncio tasks inside on_mount() -- never alongside this app.

    CSS_PATH references the Textual CSS layout file.
    """

    CSS_PATH = Path(__file__).parent / "conductor.tcss"
    AUTO_FOCUS = "CommandInput Input"  # focus the Input inside CommandInput on screen activation
    BINDINGS = [
        Binding("ctrl+g", "open_editor", "Open in editor", show=False),
    ]

    # Background task reference store (Pitfall 5: GC-collected tasks die silently)
    _background_tasks: set[asyncio.Task[Any]]

    def __init__(
        self,
        resume_session_id: str | None = None,
        dashboard_port: int | None = None,
        cwd: str | None = None,
    ) -> None:
        super().__init__()
        self._resume_session_id = resume_session_id
        self._dashboard_port = dashboard_port
        self._cwd = cwd or os.getcwd()
        self._background_tasks = set()

        # SDK client (lazy-initialized on first message)
        self._sdk_client: Any | None = None
        self._sdk_connected: bool = False

        # Active streaming cell reference
        self._active_cell: Any | None = None  # AssistantCell | None

        # DelegationManager reference (set in _ensure_sdk_connected)
        self._delegation_manager: Any | None = None

    def compose(self) -> ComposeResult:
        """Phase 32: two-column layout -- TranscriptPane + AgentMonitorPane + CommandInput + StatusFooter."""
        from textual.containers import Horizontal
        from conductor.tui.widgets.transcript import TranscriptPane
        from conductor.tui.widgets.agent_monitor import AgentMonitorPane
        from conductor.tui.widgets.command_input import CommandInput
        from conductor.tui.widgets.status_footer import StatusFooter

        state_path = Path(self._cwd) / ".conductor" / "state.json"
        with Horizontal(id="app-body"):
            yield TranscriptPane(
                resume_mode=bool(self._resume_session_id), id="transcript"
            )
            yield AgentMonitorPane(state_path=state_path, id="agent-monitor")
        yield CommandInput(id="command-input")
        yield StatusFooter(id="status-footer")

    async def on_user_submitted(self, event: "UserSubmitted") -> None:
        """Route user message to the transcript pane and start streaming.

        Phase 37: Slash commands are intercepted before the SDK streaming path.
        """
        text = event.text
        if text.startswith("/"):
            await self._handle_slash_command(text)
            return

        from conductor.tui.widgets.transcript import TranscriptPane
        from conductor.tui.widgets.command_input import CommandInput

        pane = self.query_one(TranscriptPane)
        await pane.add_user_message(text)

        # Create streaming AssistantCell
        self._active_cell = await pane.add_assistant_streaming()

        # Disable input during streaming
        self.query_one(CommandInput).disabled = True

        # Start SDK streaming worker
        self._stream_response(text)

    # -- Slash command dispatch (Phase 37) ------------------------------------

    async def _handle_slash_command(self, text: str) -> None:
        """Dispatch a slash command to the appropriate local handler.

        Slash commands never reach the SDK streaming path.
        """
        cmd = text.split()[0].lower()
        from conductor.tui.widgets.transcript import TranscriptPane

        pane = self.query_one(TranscriptPane)

        if cmd == "/help":
            from conductor.cli.chat import SLASH_COMMANDS

            lines = ["**Available commands:**"]
            for c, desc in SLASH_COMMANDS.items():
                lines.append(f"  `{c}` -- {desc}")
            help_text = "\n".join(lines)
            await pane.add_assistant_message(help_text)

        elif cmd == "/exit":
            await self._force_quit()

        elif cmd == "/status":
            if self._delegation_manager is not None:
                await pane.add_assistant_message("No active agents.")
            else:
                await pane.add_assistant_message("No active delegation session.")

        elif cmd == "/summarize":
            # Reuse streaming path with summarize prompt
            await pane.add_user_message(text)
            self._active_cell = await pane.add_assistant_streaming()
            from conductor.tui.widgets.command_input import CommandInput

            self.query_one(CommandInput).disabled = True
            summarize_prompt = (
                "Please provide a concise summary of our conversation so far, "
                "capturing all key decisions, code changes, and context needed "
                "to continue effectively. Format as a brief bullet-point list."
            )
            self._stream_response(summarize_prompt)

        elif cmd == "/resume":
            if self._delegation_manager is not None:
                await self._delegation_manager.resume_delegation()
            else:
                await pane.add_assistant_message(
                    "No delegation session to resume."
                )

        else:
            await pane.add_assistant_message(
                f"Unknown command: `{cmd}`. Type `/help` for available commands."
            )

    def on_stream_done(self, event: "StreamDone") -> None:
        """Re-enable CommandInput and restore focus after streaming completes."""
        from conductor.tui.widgets.command_input import CommandInput
        from textual.widgets import Input

        cmd = self.query_one(CommandInput)
        cmd.disabled = False
        cmd.query_one(Input).focus()

    async def on_mount(self) -> None:
        """Launch all async subsystems on Textual's event loop."""
        from conductor.tui.widgets.status_footer import StatusFooter

        # Set session_id on StatusFooter
        footer = self.query_one(StatusFooter)
        if self._resume_session_id:
            footer.session_id = self._resume_session_id
            # Lock input BEFORE starting replay worker
            from conductor.tui.widgets.command_input import CommandInput
            self.query_one(CommandInput).disabled = True
            self._replay_session()
        else:
            footer.session_id = uuid.uuid4().hex[:8]

        logger.debug(
            "ConductorApp mounted. resume_session_id=%s, dashboard_port=%s",
            self._resume_session_id,
            self._dashboard_port,
        )

        # Phase 37: Start dashboard server if port is set
        if self._dashboard_port is not None:
            await self._start_dashboard()

    # -- Session replay (Phase 38) --------------------------------------------

    @work(exclusive=False, exit_on_error=False)
    async def _replay_session(self) -> None:
        """Replay prior conversation history as immutable cells."""
        from conductor.cli.chat_persistence import ChatHistoryStore
        from conductor.tui.widgets.command_input import CommandInput
        from conductor.tui.widgets.transcript import TranscriptPane
        from textual.widgets import Input

        conductor_dir = Path(self._cwd) / ".conductor"
        session = ChatHistoryStore.load_session(conductor_dir, self._resume_session_id)

        pane = self.query_one(TranscriptPane)
        if session is None:
            await pane.add_assistant_message(
                f"Session `{self._resume_session_id}` not found."
            )
        else:
            for turn in session.get("turns", []):
                if turn.get("role") == "user":
                    await pane.add_user_message(turn["content"])
                else:
                    await pane.add_assistant_message(turn["content"])

        cmd = self.query_one(CommandInput)
        cmd.disabled = False
        cmd.query_one(Input).focus()

    # -- Dashboard server (Phase 37) ------------------------------------------

    async def _start_dashboard(self) -> None:
        """Start the dashboard uvicorn server as a tracked background task."""
        import uvicorn
        from conductor.dashboard.server import create_app

        state_path = Path(self._cwd) / ".conductor" / "state.json"
        dashboard_app = create_app(state_path)
        config = uvicorn.Config(
            dashboard_app,
            host="127.0.0.1",
            port=self._dashboard_port,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        self._track_task(asyncio.create_task(server.serve()))
        logger.info("Dashboard started on port %s", self._dashboard_port)

    # -- SDK connection --------------------------------------------------------

    async def _ensure_sdk_connected(self) -> None:
        """Lazily connect the ClaudeSDKClient on first use."""
        if self._sdk_connected:
            return

        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
        from conductor.cli.delegation import (
            DELEGATION_SYSTEM_PROMPT_ADDENDUM,
            create_delegation_mcp_server,
        )

        # Create delegation MCP server (Phase 21 pattern from chat.py)
        from conductor.cli.delegation import DelegationManager

        delegation_manager = DelegationManager(repo_path=self._cwd)
        delegation_server = create_delegation_mcp_server(delegation_manager)

        options = ClaudeAgentOptions(
            cwd=self._cwd,
            permission_mode="bypassPermissions",
            include_partial_messages=True,
            setting_sources=["project"],
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": DELEGATION_SYSTEM_PROMPT_ADDENDUM,
            },
            mcp_servers={"conductor-delegation": delegation_server},
            allowed_tools=["conductor_delegate"],
        )

        self._delegation_manager = delegation_manager

        self._sdk_client = ClaudeSDKClient(options=options)
        await self._sdk_client.connect()
        self._sdk_connected = True

        # Start the escalation queue watcher for TUI modal flow
        self._start_escalation_watcher()

    async def _disconnect_sdk(self) -> None:
        """Disconnect the SDK client if connected."""
        if self._sdk_client is not None and self._sdk_connected:
            try:
                await self._sdk_client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._sdk_connected = False

    # -- Escalation queue watcher ----------------------------------------------

    def _start_escalation_watcher(self) -> None:
        """Start the escalation queue watcher if delegation has queues."""
        if self._delegation_manager is None:
            return
        human_out = self._delegation_manager.human_out_queue
        human_in = self._delegation_manager.human_in_queue
        if human_out is not None and human_in is not None:
            self._watch_escalations(human_out, human_in)

    @work(exclusive=False, exit_on_error=False)
    async def _watch_escalations(
        self,
        human_out: asyncio.Queue,
        human_in: asyncio.Queue,
    ) -> None:
        """Watch for escalation questions and show approval modals."""
        from conductor.tui.widgets.modals import EscalationModal
        from textual.widgets import Input

        try:
            while True:
                human_query = await human_out.get()
                agent_id = human_query.context.get("agent_id", "") if human_query.context else ""
                reply = await self.push_screen_wait(
                    EscalationModal(
                        question=human_query.question,
                        agent_id=agent_id,
                    )
                )
                await human_in.put(reply)
                # Restore focus to CommandInput after modal dismissal (Pitfall 6)
                try:
                    from conductor.tui.widgets.command_input import CommandInput
                    cmd = self.query_one(CommandInput)
                    cmd.query_one(Input).focus()
                except Exception:
                    pass
        except asyncio.CancelledError:
            pass

    # -- SDK streaming worker --------------------------------------------------

    @work(exclusive=True, exit_on_error=False)
    async def _stream_response(self, text: str) -> None:
        """Run SDK streaming as a Textual managed worker.

        Routes StreamEvent tokens to the active AssistantCell and
        ResultMessage usage to StatusFooter via TokensUpdated.
        """
        from conductor.tui.messages import StreamDone, TokensUpdated
        from conductor.tui.widgets.status_footer import StatusFooter
        from conductor.tui.widgets.transcript import AssistantCell

        cell = self._active_cell
        first_chunk = True

        try:
            await self._ensure_sdk_connected()
            await self._sdk_client.query(text)

            from claude_agent_sdk import ResultMessage
            from claude_agent_sdk.types import StreamEvent

            async for message in self._sdk_client.receive_response():
                if isinstance(message, StreamEvent):
                    event = message.event
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            if chunk and cell is not None:
                                if first_chunk:
                                    await cell.start_streaming()
                                    first_chunk = False
                                await cell.append_token(chunk)

                elif isinstance(message, ResultMessage):
                    if message.usage:
                        # Post directly to footer (messages bubble UP, not DOWN)
                        try:
                            footer = self.query_one(StatusFooter)
                            footer.post_message(TokensUpdated(message.usage))
                        except Exception:
                            pass
                    # Extract session_id if available
                    session_id = getattr(message, "session_id", None)
                    if session_id and session_id != "default":
                        try:
                            footer = self.query_one(StatusFooter)
                            footer.session_id = str(session_id)
                        except Exception:
                            pass

        except Exception as exc:
            # SDK errors show inline error message instead of crashing app
            logger.error("SDK streaming error: %s", exc)
            if cell is not None:
                # If we haven't started streaming yet, start it to show error
                if first_chunk:
                    try:
                        await cell.start_streaming()
                    except Exception:
                        pass
                try:
                    await cell.append_token(f"\n\n**Error:** {exc}")
                except Exception:
                    pass

        finally:
            # Finalize the active cell if it's still streaming
            if cell is not None and cell._is_streaming:
                try:
                    await cell.finalize()
                except Exception:
                    pass
            self._active_cell = None
            self.post_message(StreamDone())

    # -- background task management --------------------------------------------

    def _track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Store a background task reference to prevent GC collection.

        Usage:
            t = self._track_task(asyncio.create_task(my_coro()))
        """
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def action_open_editor(self) -> None:
        """Open current input content in $VISUAL/$EDITOR (vim fallback).

        Plain sync action (no @work) so suspend() runs on the main thread.
        Textual's suspend() calls signal.signal() internally which only works
        from the main thread — @work(thread=True) silently breaks it.
        Uses os.system() per Textual's own docs example for editor launch.
        """
        import shlex
        import tempfile
        from textual.app import SuspendNotSupported
        from textual.widgets import Input
        from conductor.tui.widgets.command_input import CommandInput
        from conductor.tui.messages import EditorContentReady

        # Guard: replay mode or streaming -- input is locked, do nothing
        try:
            cmd_input = self.query_one(CommandInput)
            if cmd_input.disabled:
                return
            current_text = cmd_input.query_one(Input).value
        except Exception:
            current_text = ""

        # POSIX editor selection: $VISUAL > $EDITOR > vim
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vim"

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            prefix="conductor_",
            delete=False,
        ) as f:
            f.write(current_text)
            tmp_path = f.name

        edited_text = current_text  # default: unchanged if editor cancelled

        try:
            try:
                with self.suspend():
                    os.system(f"{shlex.quote(editor)} {shlex.quote(tmp_path)}")
                    # Read INSIDE suspend block -- documented safe pattern
                    with open(tmp_path) as fh:
                        edited_text = fh.read()
            except SuspendNotSupported:
                self.notify(
                    "External editor not supported in this environment",
                    severity="warning",
                )
                return
            except (FileNotFoundError, OSError):
                self.notify(
                    f"Editor not found: {editor}",
                    severity="warning",
                )
                return
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        stripped = edited_text.rstrip("\n")
        # Post message if content changed or is non-empty
        if stripped != current_text or stripped:
            cmd_widget = self.query_one(CommandInput)
            cmd_widget.post_message(EditorContentReady(stripped))

    async def action_quit(self) -> None:
        """Ctrl-C / quit: cancel active stream first, exit on second press."""
        # If actively streaming, cancel the stream instead of exiting
        if self._active_cell is not None and self._active_cell._is_streaming:
            # Cancel the streaming worker
            self.workers.cancel_group(self, "default")
            return

        await self._force_quit()

    async def _force_quit(self) -> None:
        """Unconditional clean exit — disconnects SDK, cancels tasks, exits."""
        await self._disconnect_sdk()
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self.exit()
