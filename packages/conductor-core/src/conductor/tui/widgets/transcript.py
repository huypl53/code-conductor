"""TranscriptPane — scrollable conversation history with UserCell and AssistantCell."""
from __future__ import annotations
import math
import os
import re
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import VerticalScroll
from textual.timer import Timer
from textual.widgets import LoadingIndicator, Markdown, Static
from textual.widget import Widget

# Shimmer animation tint targets
_SHIMMER_ON = Color(150, 150, 255, 0.12)
_SHIMMER_OFF = Color(0, 0, 0, 0.0)
_SHIMMER_INTERVAL = 1.0 / 15  # ~15 fps
_SHIMMER_PERIOD = 1.4  # full cycle duration in seconds

# Fade-in animation guard — read once at import time.
# Set CONDUCTOR_NO_ANIMATIONS=1 to disable for CI/SSH environments.
_ANIMATIONS = os.environ.get("CONDUCTOR_NO_ANIMATIONS", "") not in ("1", "true", "yes")


class UserCell(Widget):
    """A single user message turn. Visually distinct from AssistantCell."""

    DEFAULT_CSS = """
    UserCell {
        background: $primary 10%;
        border-left: solid $primary 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    UserCell .cell-label {
        color: $primary;
        text-style: bold;
    }
    """

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static("You", classes="cell-label")
        yield Static(self._text)

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")


class AssistantCell(Widget):
    """A single assistant message turn with optional streaming lifecycle.

    Two modes:
    - Static: AssistantCell("some text") — renders text immediately (Phase 32 compat).
    - Streaming: AssistantCell() — shows LoadingIndicator, then transitions to
      Markdown via start_streaming() / append_token() / finalize().
    """

    DEFAULT_CSS = """
    AssistantCell {
        background: $surface;
        border-left: solid $accent 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    AssistantCell .cell-label {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, text: str | None = None) -> None:
        super().__init__()
        self._text = text
        self._is_streaming: bool = text is None
        self._stream = None  # MarkdownStream | None
        self._markdown: Markdown | None = None
        self._shimmer_timer: Timer | None = None
        self._shimmer_phase: float = 0.0

    def compose(self) -> ComposeResult:
        yield Static("Assistant", classes="cell-label")
        if self._text is not None:
            # Static mode — render text immediately
            yield Static(self._text)
        else:
            # Streaming mode — show thinking indicator
            yield LoadingIndicator()

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")

    async def start_streaming(self) -> None:
        """Transition from thinking to streaming: remove LoadingIndicator, mount Markdown."""
        try:
            indicator = self.query_one(LoadingIndicator)
            await indicator.remove()
        except Exception:
            pass
        from conductor.tui.widgets.rich_markdown import RichMarkdown
        self._markdown = RichMarkdown("")
        await self.mount(self._markdown)
        self._stream = Markdown.get_stream(self._markdown)
        self._shimmer_forward()

    async def append_token(self, chunk: str) -> None:
        """Route a token chunk into the MarkdownStream."""
        if self._stream is not None:
            await self._stream.write(chunk)

    async def finalize(self) -> None:
        """Stop the stream and make the cell immutable."""
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None
        # Stop shimmer before clearing streaming flag
        if self._shimmer_timer is not None:
            self._shimmer_timer.stop()
            self._shimmer_timer = None
        self.styles.tint = _SHIMMER_OFF
        self._is_streaming = False

    def _shimmer_forward(self) -> None:
        """Start the shimmer ping-pong animation via set_interval."""
        if not self._is_streaming:
            return
        self._shimmer_phase = 0.0
        self._shimmer_timer = self.set_interval(
            _SHIMMER_INTERVAL, self._shimmer_tick
        )

    def _shimmer_tick(self) -> None:
        """Update tint based on sine wave phase (called by timer)."""
        if not self._is_streaming:
            if self._shimmer_timer is not None:
                self._shimmer_timer.stop()
                self._shimmer_timer = None
            self.styles.tint = _SHIMMER_OFF
            return
        self._shimmer_phase += _SHIMMER_INTERVAL
        # Sine wave: 0..1..0 over _SHIMMER_PERIOD
        t = (math.sin(2 * math.pi * self._shimmer_phase / _SHIMMER_PERIOD) + 1) / 2
        alpha = _SHIMMER_ON.a * t
        self.styles.tint = Color(_SHIMMER_ON.r, _SHIMMER_ON.g, _SHIMMER_ON.b, alpha)

    def _shimmer_back(self) -> None:
        """Compatibility stub — shimmer uses set_interval, not ping-pong callbacks."""
        pass


def _sanitize_id(agent_id: str) -> str:
    """Replace non-alphanumeric chars with hyphens for safe CSS IDs.

    Example: "agent.uuid/1:2" -> "agent-uuid-1-2"
    Prefix "acell-" is distinct from agent_monitor.py's "agent-" prefix.
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", agent_id).strip("-") or "agent"


class AgentCell(Widget):
    """A single agent task turn with status lifecycle.

    Displays agent name, role, and task title in a labeled badge header.
    Supports status transitions: working (shimmer) -> waiting -> done.
    """

    DEFAULT_CSS = """
    AgentCell {
        background: $surface;
        border-left: solid $warning 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    AgentCell .cell-label {
        color: $warning;
        text-style: bold;
    }
    AgentCell .cell-status {
        color: $text-muted;
    }
    """

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        role: str,
        task_title: str,
    ) -> None:
        safe_id = _sanitize_id(agent_id)
        super().__init__(id=f"acell-{safe_id}")
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._role = role
        self._task_title = task_title
        self._shimmer_timer: Timer | None = None
        self._shimmer_phase: float = 0.0
        self._status = "working"

    def compose(self) -> ComposeResult:
        yield Static(
            f"{self._agent_name} [{self._role}] \u2014 {self._task_title}",
            classes="cell-label",
        )
        yield Static("working...", classes="cell-status")

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")
        self._shimmer_forward()

    def update_status(self, new_status: str) -> None:
        """Transition display: working shimmer -> waiting -> done."""
        if self._status == "done":
            return
        self._status = new_status
        try:
            self.query_one(".cell-status", Static).update(new_status)
        except Exception:
            pass
        if new_status != "working":
            self._stop_shimmer()

    def finalize(self, summary: str = "") -> None:
        """Mark cell as complete — idempotent, safe to call before or after mount.

        Args:
            summary: Optional task summary text. When provided, cell-status shows
                     "done — {summary}". When empty, shows just "done".
        """
        self._stop_shimmer()
        self._status = "done"
        status_text = f"done \u2014 {summary}" if summary else "done"
        try:
            self.query_one(".cell-status", Static).update(status_text)
        except Exception:
            pass

    def _stop_shimmer(self) -> None:
        """Stop the shimmer timer if running. Idempotent."""
        if self._shimmer_timer is not None:
            self._shimmer_timer.stop()
            self._shimmer_timer = None
        try:
            self.styles.tint = _SHIMMER_OFF
        except Exception:
            pass

    def _shimmer_forward(self) -> None:
        """Start the shimmer pulse animation via set_interval."""
        if self._status != "working":
            return
        self._shimmer_phase = 0.0
        self._shimmer_timer = self.set_interval(_SHIMMER_INTERVAL, self._shimmer_tick)

    def _shimmer_tick(self) -> None:
        """Update tint based on sine wave phase (called by timer)."""
        if self._status != "working":
            self._stop_shimmer()
            return
        self._shimmer_phase += _SHIMMER_INTERVAL
        t = (math.sin(2 * math.pi * self._shimmer_phase / _SHIMMER_PERIOD) + 1) / 2
        alpha = _SHIMMER_ON.a * t
        self.styles.tint = Color(_SHIMMER_ON.r, _SHIMMER_ON.g, _SHIMMER_ON.b, alpha)


class OrchestratorStatusCell(Widget):
    """An ephemeral orchestrator phase status cell.

    Displays a phase label (e.g., "Orchestrator — delegating") and a description.
    Supports update() and finalize() for lifecycle management.
    Once finalized, further updates are no-ops.
    """

    DEFAULT_CSS = """
    OrchestratorStatusCell {
        background: $surface;
        border-left: solid $secondary 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    OrchestratorStatusCell .cell-label {
        color: $secondary;
        text-style: bold;
    }
    OrchestratorStatusCell .cell-body {
        color: $text-muted;
    }
    """

    def __init__(self, label: str, description: str = "") -> None:
        super().__init__()
        self._label = label
        self._description = description
        self._finalized = False

    def compose(self) -> ComposeResult:
        yield Static(self._label, classes="cell-label", id="orch-label")
        yield Static(self._description, classes="cell-body", id="orch-body")

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")

    def update(self, label: str | None = None, description: str | None = None) -> None:
        """Update label and/or description. No-op if finalized."""
        if self._finalized:
            return
        if label is not None:
            try:
                self.query_one("#orch-label", Static).update(label)
            except Exception:
                pass
        if description is not None:
            try:
                self.query_one("#orch-body", Static).update(description)
            except Exception:
                pass

    def finalize(self) -> None:
        """Mark as complete. Idempotent."""
        self._finalized = True


class TranscriptPane(VerticalScroll):
    """Scrollable vertical container for conversation cells.

    Receives UserSubmitted messages from CommandInput (via app message bus)
    and mounts a new UserCell. AssistantCell creation comes via StreamingStarted.
    """

    DEFAULT_CSS = """
    TranscriptPane {
        width: 1fr;
        height: 1fr;
        padding: 1 2;
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, *, resume_mode: bool = False, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._resume_mode = resume_mode
        self._agent_cells: dict[str, "AgentCell"] = {}
        self._orch_status_cell: "OrchestratorStatusCell | None" = None

    def on_mount(self) -> None:
        """Mount a welcome cell so the pane is not blank on first launch."""
        if not self._resume_mode:
            self.mount(
                AssistantCell(
                    "Welcome to Conductor. Type a message below to begin."
                )
            )

    @property
    def _is_at_bottom(self) -> bool:
        """Check if the user is scrolled to (or near) the bottom."""
        return self.scroll_offset.y >= self.max_scroll_y - 2

    def _maybe_scroll_end(self) -> None:
        """Scroll to bottom only if the user hasn't scrolled up."""
        if self._is_at_bottom:
            self.scroll_end(animate=False)

    async def add_user_message(self, text: str) -> None:
        """Mount a UserCell and scroll to bottom."""
        cell = UserCell(text)
        await self.mount(cell)
        self.scroll_end(animate=False)  # always scroll on user's own message

    async def add_assistant_message(self, text: str) -> AssistantCell:
        """Mount a static AssistantCell with pre-set text content."""
        cell = AssistantCell(text)
        await self.mount(cell)
        self._maybe_scroll_end()
        return cell

    async def add_assistant_streaming(self) -> AssistantCell:
        """Mount a streaming AssistantCell (thinking state) and return it."""
        cell = AssistantCell()
        await self.mount(cell)
        self.scroll_end(animate=False)  # always scroll when stream starts
        return cell

    async def on_delegation_started(self, event: "DelegationStarted") -> None:
        """ORCH-02: Mount an OrchestratorStatusCell when conductor_delegate fires.

        Creates and mounts an OrchestratorStatusCell with the task description
        from the DelegationStarted message. Stores reference in _orch_status_cell.
        """
        from conductor.tui.messages import DelegationStarted  # noqa: F401 (import for type annotation)

        cell = OrchestratorStatusCell(
            label="Orchestrator \u2014 delegating",
            description=event.task_description,
        )
        self._orch_status_cell = cell
        await self.mount(cell)
        self._maybe_scroll_end()

    async def on_agent_state_updated(self, event: "AgentStateUpdated") -> None:
        """Handle AgentStateUpdated: mount/update/finalize AgentCells in transcript."""
        from conductor.state.models import AgentStatus

        state = event.state
        tasks = {t.assigned_agent: t for t in state.tasks if t.assigned_agent}

        for agent in state.agents:
            task = tasks.get(agent.id)
            task_title = task.title if task else "(unknown task)"

            if agent.id not in self._agent_cells:
                if agent.status == AgentStatus.WORKING:
                    cell = AgentCell(
                        agent_id=agent.id,
                        agent_name=agent.name,
                        role=agent.role,
                        task_title=task_title,
                    )
                    self._agent_cells[agent.id] = cell  # register BEFORE mount (pitfall)
                    await self.mount(cell)
                    self._maybe_scroll_end()
            else:
                cell = self._agent_cells[agent.id]
                if agent.status == AgentStatus.DONE:
                    summary = ""
                    if task is not None and isinstance(task.outputs, dict):
                        summary = task.outputs.get("summary", "")
                    cell.finalize(summary=summary)
                else:
                    cell.update_status(str(agent.status))
