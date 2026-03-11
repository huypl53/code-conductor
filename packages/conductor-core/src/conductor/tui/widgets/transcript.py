"""TranscriptPane — scrollable conversation history with UserCell and AssistantCell."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import LoadingIndicator, Markdown, Static
from textual.widget import Widget


class UserCell(Widget):
    """A single user message turn. Visually distinct from AssistantCell."""

    DEFAULT_CSS = """
    UserCell {
        background: $primary 10%;
        border-left: thick $primary;
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
        border-left: thick $accent;
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

    def compose(self) -> ComposeResult:
        yield Static("Conductor", classes="cell-label")
        if self._text is not None:
            # Static mode — render text immediately
            yield Static(self._text)
        else:
            # Streaming mode — show thinking indicator
            yield LoadingIndicator()

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

    async def append_token(self, chunk: str) -> None:
        """Route a token chunk into the MarkdownStream."""
        if self._stream is not None:
            await self._stream.write(chunk)

    async def finalize(self) -> None:
        """Stop the stream and make the cell immutable."""
        if self._stream is not None:
            await self._stream.stop()
            self._stream = None
        self._is_streaming = False


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

    def on_mount(self) -> None:
        """Mount a welcome cell so the pane is not blank on first launch."""
        self.mount(
            AssistantCell(
                "Welcome to Conductor. Type a message below to begin."
            )
        )

    async def add_user_message(self, text: str) -> None:
        """Mount a UserCell and scroll to bottom."""
        cell = UserCell(text)
        await self.mount(cell)
        self.scroll_end(animate=False)

    async def add_assistant_message(self, text: str) -> AssistantCell:
        """Mount a static AssistantCell with pre-set text content."""
        cell = AssistantCell(text)
        await self.mount(cell)
        self.scroll_end(animate=False)
        return cell

    async def add_assistant_streaming(self) -> AssistantCell:
        """Mount a streaming AssistantCell (thinking state) and return it."""
        cell = AssistantCell()
        await self.mount(cell)
        self.scroll_end(animate=False)
        return cell
