"""Streaming display helpers for the interactive chat TUI.

Provides:
- Tool activity line formatting (CHAT-06)
- Context usage tracking and warnings (CHAT-08)
"""

from __future__ import annotations

from typing import Any

# Claude model context windows (tokens).  We track total usage and warn at ~75%.
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-5-20250514": 200_000,
    "claude-opus-4-20250514": 200_000,
    "claude-opus-4-1-20250805": 200_000,
    "claude-sonnet-4-5": 200_000,
    "default": 200_000,
}

CONTEXT_WARNING_THRESHOLD = 0.75


def format_tool_activity(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    """Return a human-readable status line for a tool invocation.

    Returns None for tool names we don't want to display.
    """
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        return f"Reading {_short_path(path)}..."

    if tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"Editing {_short_path(path)}..."

    if tool_name == "Write":
        path = tool_input.get("file_path", "")
        return f"Writing {_short_path(path)}..."

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        # Truncate long commands
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        return f"Running: {cmd}"

    if tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"Searching: {pattern}"

    if tool_name == "Grep":
        pattern = tool_input.get("pattern", "")
        return f"Grep: {pattern}"

    if tool_name in ("MultiEdit",):
        path = tool_input.get("file_path", "")
        return f"Editing {_short_path(path)}..."

    # Generic fallback for unknown tools
    return f"Using tool: {tool_name}"


def _short_path(path: str) -> str:
    """Shorten a file path for display — keep last 2 components."""
    if not path:
        return "<unknown>"
    parts = path.replace("\\", "/").split("/")
    if len(parts) <= 2:
        return path
    return "/".join(parts[-2:])


class ContextTracker:
    """Track cumulative token usage and warn when approaching context limits.

    The tracker accumulates usage from ResultMessage.usage dicts and
    compares against the model's context window.
    """

    def __init__(self, model: str = "default") -> None:
        self._context_window = MODEL_CONTEXT_WINDOWS.get(
            model, MODEL_CONTEXT_WINDOWS["default"]
        )
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._warned = False

    def update(self, usage: dict[str, Any] | None) -> None:
        """Update token counts from a ResultMessage.usage dict."""
        if usage is None:
            return
        self._total_input_tokens = usage.get("input_tokens", self._total_input_tokens)
        self._total_output_tokens += usage.get("output_tokens", 0)

    @property
    def input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def output_tokens(self) -> int:
        return self._total_output_tokens

    @property
    def utilization(self) -> float:
        """Approximate context utilization as a fraction (0.0 - 1.0)."""
        if self._context_window == 0:
            return 0.0
        # Input tokens represent the current context size
        return self._total_input_tokens / self._context_window

    def should_warn(self) -> bool:
        """Return True once when utilization crosses the warning threshold."""
        if self._warned:
            return False
        if self.utilization >= CONTEXT_WARNING_THRESHOLD:
            self._warned = True
            return True
        return False

    def reset_warning(self) -> None:
        """Allow the warning to fire again (e.g. after summarization)."""
        self._warned = False
