"""ConductorApp — Textual App root for Conductor v2.0.

Phase 31: Minimal skeleton — event loop ownership, lifecycle, background task
          reference tracking. No widgets beyond a placeholder label.
Phase 32: Full two-column layout (TranscriptPane, CommandInput, StatusFooter,
          AgentMonitorPane) replaces the placeholder.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult

logger = logging.getLogger("conductor.tui")


class ConductorApp(App):
    """Textual application root.

    Owns the asyncio event loop. All async subsystems (SDK streaming,
    uvicorn dashboard server, orchestrator delegation) launch as workers
    or asyncio tasks inside on_mount() — never alongside this app.

    CSS_PATH references the Textual CSS layout file.
    """

    CSS_PATH = Path(__file__).parent / "conductor.tcss"

    # Background task reference store (Pitfall 5: GC-collected tasks die silently)
    _background_tasks: set[asyncio.Task[Any]]

    def __init__(
        self,
        resume_session_id: str | None = None,
        dashboard_port: int | None = None,
    ) -> None:
        super().__init__()
        self._resume_session_id = resume_session_id
        self._dashboard_port = dashboard_port
        self._background_tasks = set()

    def compose(self) -> ComposeResult:
        """Phase 32: two-column layout — TranscriptPane + AgentMonitorPane + CommandInput + StatusFooter."""
        from textual.containers import Horizontal
        from conductor.tui.widgets.transcript import TranscriptPane
        from conductor.tui.widgets.agent_monitor import AgentMonitorPane
        from conductor.tui.widgets.command_input import CommandInput
        from conductor.tui.widgets.status_footer import StatusFooter

        with Horizontal(id="app-body"):
            yield TranscriptPane(id="transcript")
            yield AgentMonitorPane(id="agent-monitor")
        yield CommandInput(id="command-input")
        yield StatusFooter(id="status-footer")

    async def on_user_submitted(self, event: "UserSubmitted") -> None:
        """Route user message to the transcript pane."""
        from conductor.tui.widgets.transcript import TranscriptPane
        pane = self.query_one(TranscriptPane)
        await pane.add_user_message(event.text)

    async def on_mount(self) -> None:
        """Launch all async subsystems on Textual's event loop.

        Pattern: asyncio.create_task() for raw tasks (stored in
        _background_tasks to prevent GC); self.run_worker() for Textual
        @work coroutines (WorkerManager holds references automatically).
        """
        # Phase 32: mount SDKStreamWorker, StateWatchWorker here
        # Phase 37: mount DashboardWorker here if dashboard_port is set
        logger.debug(
            "ConductorApp mounted. resume_session_id=%s, dashboard_port=%s",
            self._resume_session_id,
            self._dashboard_port,
        )

    def _track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Store a background task reference to prevent GC collection.

        Usage:
            t = self._track_task(asyncio.create_task(my_coro()))
        """
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def action_quit(self) -> None:
        """Clean exit — cancels background tasks, then calls app.exit()."""
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self.exit()
