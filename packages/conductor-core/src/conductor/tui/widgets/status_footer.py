"""StatusFooter — static docked bar at the bottom showing structural info.

Phase 32: static placeholder text only.
Phase 33: wired to TokensUpdated messages for live model/token display.
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Static


class StatusFooter(Widget):
    """Bottom status bar. Docked via CSS dock: bottom.

    Phase 32 shows placeholder. Phase 33 wires live model/token data.
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

    def compose(self) -> ComposeResult:
        yield Static("Conductor v2.0 | model: — | mode: interactive | tokens: —", classes="footer-left")
        yield Static("Ctrl+C to quit", classes="footer-right")
