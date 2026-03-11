"""TranscriptPane — scrollable conversation history with UserCell and AssistantCell."""
from __future__ import annotations
import math
import os
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
