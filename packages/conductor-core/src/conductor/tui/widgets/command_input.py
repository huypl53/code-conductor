"""CommandInput — single-line input bar that posts UserSubmitted on Enter."""
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input
from conductor.tui.messages import UserSubmitted


class CommandInput(Widget):
    """Input bar at the bottom of the screen.

    On Enter: posts UserSubmitted(text) to the app message bus, then clears.
    Phase 37 will add slash command autocomplete popup.
    """

    DEFAULT_CSS = """
    CommandInput {
        height: 3;
        padding: 0 1;
        background: $panel;
        border-top: solid $primary 30%;
    }
    CommandInput Input {
        background: $panel;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Type a message... (Enter to send, Ctrl+C to quit)")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """User pressed Enter — post message to app bus, clear input."""
        text = event.value.strip()
        if not text:
            return
        self.post_message(UserSubmitted(text))
        event.input.clear()
        # Stop event from bubbling further — CommandInput owns this submission
        event.stop()
