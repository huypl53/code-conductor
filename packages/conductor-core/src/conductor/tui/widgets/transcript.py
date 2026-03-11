"""TranscriptPane — scrollable conversation history with UserCell and AssistantCell."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static
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
    """A single assistant message turn. Lighter background than UserCell."""

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

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        yield Static("Conductor", classes="cell-label")
        yield Static(self._text)


class TranscriptPane(VerticalScroll):
    """Scrollable vertical container for conversation cells.

    Receives UserSubmitted messages from CommandInput (via app message bus)
    and mounts a new UserCell. AssistantCell creation comes in Phase 33.
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
