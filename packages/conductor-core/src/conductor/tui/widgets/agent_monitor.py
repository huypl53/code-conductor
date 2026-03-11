"""AgentMonitorPane — right-side placeholder for agent status panels.

Phase 32: static placeholder only.
Phase 35: wired to StateWatchWorker — collapsible per-agent rows.
"""
from __future__ import annotations
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class AgentMonitorPane(VerticalScroll):
    """Right-side panel showing agent status. Placeholder in Phase 32."""

    DEFAULT_CSS = """
    AgentMonitorPane {
        width: 30;
        height: 1fr;
        background: $panel;
        border-left: solid $primary 20%;
        padding: 1 1;
    }
    AgentMonitorPane #monitor-heading {
        color: $text-muted;
        text-style: bold;
        text-align: center;
        width: 1fr;
        padding-bottom: 1;
    }
    AgentMonitorPane #monitor-empty {
        color: $text-muted;
        text-align: center;
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("Agents", id="monitor-heading")
        yield Static("No agents active", id="monitor-empty")
