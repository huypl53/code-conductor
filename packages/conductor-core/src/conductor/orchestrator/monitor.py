"""StreamMonitor — processes streaming messages from a sub-agent session."""
from __future__ import annotations

import json
import logging
import re

from claude_agent_sdk import (  # noqa: F401
    AssistantMessage,
    ResultMessage,
    SystemMessage,
)
from claude_agent_sdk.types import (
    TaskNotificationMessage,
    TaskProgressMessage,
    ToolUseBlock,
)

from conductor.orchestrator.models import AgentReport

logger = logging.getLogger("conductor.orchestrator")

# Regex to match a fenced ```json ... ``` block (non-greedy, DOTALL)
_FENCED_JSON_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def parse_agent_report(text: str) -> AgentReport | None:
    """Extract a structured AgentReport from agent output text.

    Searches for a fenced ```json ... ``` block containing a valid AgentReport
    JSON object. Returns None on any failure (no block found, parse error,
    validation error) so that callers can fall back to freeform behavior.

    Args:
        text: The full result text from a sub-agent session.

    Returns:
        An :class:`AgentReport` if a valid JSON status block is found,
        or ``None`` for freeform fallback.
    """
    if not text:
        return None

    # Try fenced JSON block first
    match = _FENCED_JSON_RE.search(text)
    if match:
        json_str = match.group(1).strip()
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None
        # Must have a "status" key to be an AgentReport
        if not isinstance(data, dict) or "status" not in data:
            return None
        try:
            return AgentReport.model_validate(data)
        except Exception:  # noqa: BLE001
            return None

    return None


class StreamMonitor:
    """Lightweight message processor for sub-agent streaming sessions.

    Processes-and-discards streamed messages, keeping only state change events
    and the final result_text. Does NOT hold a reference to StateManager —
    state writes happen in the orchestrator (Plan 02).
    """

    def __init__(self, task_id: str) -> None:
        self._task_id = task_id
        self._result_text: str | None = None
        self._tool_events: list[str] = []

    def process(self, message: object) -> None:
        """Dispatch a single streamed message to the appropriate handler."""
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    self._tool_events.append(block.name)
        elif isinstance(message, TaskProgressMessage):
            # Phase 5: minimal; Phase 9/10 will use this for dashboard
            pass
        elif isinstance(message, TaskNotificationMessage):
            # Sub-task (Claude Code Task tool) completion — not session end
            pass
        elif isinstance(message, ResultMessage):
            self._result_text = message.result
        # Unknown message types are silently ignored (no-op)

    @property
    def result_text(self) -> str | None:
        """Final result text from ResultMessage, or None if not yet received."""
        return self._result_text

    @property
    def tool_events(self) -> list[str]:
        """Read-only copy of recorded tool names in invocation order."""
        return list(self._tool_events)
