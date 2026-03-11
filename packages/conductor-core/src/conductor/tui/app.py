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

logger = logging.getLogger("conductor.tui")


class ConductorApp(App):
    """Textual application root.

    Owns the asyncio event loop. All async subsystems (SDK streaming,
    uvicorn dashboard server, orchestrator delegation) launch as workers
    or asyncio tasks inside on_mount() -- never alongside this app.

    CSS_PATH references the Textual CSS layout file.
    """

    CSS_PATH = Path(__file__).parent / "conductor.tcss"

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

    def compose(self) -> ComposeResult:
        """Phase 32: two-column layout -- TranscriptPane + AgentMonitorPane + CommandInput + StatusFooter."""
        from textual.containers import Horizontal
        from conductor.tui.widgets.transcript import TranscriptPane
        from conductor.tui.widgets.agent_monitor import AgentMonitorPane
        from conductor.tui.widgets.command_input import CommandInput
        from conductor.tui.widgets.status_footer import StatusFooter

        state_path = Path(self._cwd) / ".conductor" / "state.json"
        with Horizontal(id="app-body"):
            yield TranscriptPane(id="transcript")
            yield AgentMonitorPane(state_path=state_path, id="agent-monitor")
        yield CommandInput(id="command-input")
        yield StatusFooter(id="status-footer")

    async def on_user_submitted(self, event: "UserSubmitted") -> None:
        """Route user message to the transcript pane and start streaming."""
        from conductor.tui.widgets.transcript import TranscriptPane
        from conductor.tui.widgets.command_input import CommandInput

        pane = self.query_one(TranscriptPane)
        await pane.add_user_message(event.text)

        # Create streaming AssistantCell
        self._active_cell = await pane.add_assistant_streaming()

        # Disable input during streaming
        self.query_one(CommandInput).disabled = True

        # Start SDK streaming worker
        self._stream_response(event.text)

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
        else:
            footer.session_id = uuid.uuid4().hex[:8]

        logger.debug(
            "ConductorApp mounted. resume_session_id=%s, dashboard_port=%s",
            self._resume_session_id,
            self._dashboard_port,
        )

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

    async def action_quit(self) -> None:
        """Clean exit -- cancels background tasks, disconnects SDK, then exits."""
        await self._disconnect_sdk()
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self.exit()
