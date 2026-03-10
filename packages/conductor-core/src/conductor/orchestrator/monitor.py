"""StreamMonitor — processes streaming messages from a sub-agent session."""
from __future__ import annotations

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
