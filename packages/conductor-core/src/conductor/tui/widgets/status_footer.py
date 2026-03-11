"""StatusFooter — reactive docked bar showing model, mode, tokens, and session.

Phase 32: static placeholder text only.
Phase 33: wired to TokensUpdated messages for live model/token display.
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from conductor.tui.messages import TokensUpdated


class StatusFooter(Widget):
    """Bottom status bar with reactive model/mode/tokens/session display.

    Docked via CSS dock: bottom.
    """

    DEFAULT_CSS = """
    StatusFooter {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
        layout: horizontal;
    }
    StatusFooter .footer-left {
        width: 1fr;
        color: $text;
    }
    StatusFooter .footer-right {
        color: $text-muted;
        text-align: right;
    }
    """

    model_name: reactive[str] = reactive("--")
    mode: reactive[str] = reactive("interactive")
    token_count: reactive[int] = reactive(0)
    session_id: reactive[str] = reactive("--")

    def compose(self) -> ComposeResult:
        yield Static("", id="status-left", classes="footer-left")
        yield Static("Ctrl+C to quit", classes="footer-right")

    def on_mount(self) -> None:
        """Set initial display content from reactive defaults."""
        self._refresh_display()

    def watch_model_name(self, value: str) -> None:
        self._refresh_display()

    def watch_mode(self, value: str) -> None:
        self._refresh_display()

    def watch_token_count(self, value: int) -> None:
        self._refresh_display()

    def watch_session_id(self, value: str) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        """Update the left label with current reactive values."""
        label = (
            f"model: {self.model_name} | mode: {self.mode} "
            f"| tokens: {self.token_count} | session: {self.session_id}"
        )
        try:
            self.query_one("#status-left", Static).update(label)
        except Exception:
            pass  # Widget not yet mounted

    def on_tokens_updated(self, event: TokensUpdated) -> None:
        """Handle TokensUpdated message — sum input + output tokens."""
        usage = event.usage
        total = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        self.token_count = total
