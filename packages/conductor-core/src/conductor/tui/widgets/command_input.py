"""CommandInput — single-line input bar that posts UserSubmitted on Enter.

Phase 37: Adds SlashAutocomplete widget for slash command discovery.
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input
from conductor.tui.messages import UserSubmitted, EditorContentReady


class SlashAutocomplete:
    """Lazy wrapper — actual class is built on first import to avoid
    top-level textual_autocomplete import (keeps prompt_toolkit isolation).
    """
    pass


# Replace the placeholder with the real implementation
def _build_slash_autocomplete():
    """Build the real SlashAutocomplete class using textual_autocomplete."""
    from textual_autocomplete import AutoComplete, DropdownItem, TargetState

    class _SlashAutocomplete(AutoComplete):
        """Autocomplete that activates only when input starts with '/'."""

        def get_candidates(self, target_state: TargetState) -> list[DropdownItem]:
            from conductor.cli.chat import SLASH_COMMANDS
            return [
                DropdownItem(cmd, prefix=desc)
                for cmd, desc in SLASH_COMMANDS.items()
            ]

        def get_search_string(self, target_state: TargetState) -> str:
            """Search only the text after '/'."""
            if not target_state.text.startswith("/"):
                return "\x00"  # no-match sentinel — hides all candidates
            return target_state.text[1:]  # text after the slash

        def apply_completion(self, value: str, state: TargetState) -> None:
            """Replace input value with the selected command."""
            target = self.target
            target.value = value
            target.cursor_position = len(value)

    return _SlashAutocomplete


# Build the real class at module level
SlashAutocomplete = _build_slash_autocomplete()


class CommandInput(Widget):
    """Input bar at the bottom of the screen.

    On Enter: posts UserSubmitted(text) to the app message bus, then clears.
    Phase 37: SlashAutocomplete widget provides slash command discovery.
    """

    DEFAULT_CSS = """
    CommandInput {
        height: 3;
        padding: 0 1;
        background: $panel;
    }
    CommandInput Input {
        background: $panel;
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        inp = Input(placeholder="Type a message... (/ for commands)")
        yield inp
        yield SlashAutocomplete(inp)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """User pressed Enter — post message to app bus, clear input."""
        text = event.value.strip()
        if not text:
            return
        self.post_message(UserSubmitted(text))
        event.input.clear()
        # Stop event from bubbling further — CommandInput owns this submission
        event.stop()

    def on_editor_content_ready(self, event: EditorContentReady) -> None:
        """Fill the Input with text returned from the external editor."""
        inp = self.query_one(Input)
        inp.value = event.text
        inp.cursor_position = len(event.text)
        inp.focus()
        event.stop()
