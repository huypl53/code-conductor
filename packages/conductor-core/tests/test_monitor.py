"""ORCH-03 tests for StreamMonitor message dispatch."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from conductor.orchestrator.monitor import StreamMonitor


class TestOrch03ToolUse:
    """StreamMonitor records tool name from AssistantMessage with ToolUseBlock."""

    def test_tool_name_recorded(self) -> None:
        # Arrange — mock AssistantMessage with ToolUseBlock content
        tool_block = MagicMock()
        tool_block.name = "str_replace_based_edit_tool"
        tool_block.input = {"path": "src/main.py"}

        # Make isinstance(block, ToolUseBlock) return True
        from claude_agent_sdk.types import ToolUseBlock
        tool_block.__class__ = ToolUseBlock

        msg = MagicMock()
        from claude_agent_sdk import AssistantMessage
        msg.__class__ = AssistantMessage
        msg.content = [tool_block]

        monitor = StreamMonitor("task-1")

        # Act
        monitor.process(msg)

        # Assert
        assert "str_replace_based_edit_tool" in monitor.tool_events

    def test_multiple_tool_blocks_all_recorded(self) -> None:
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk.types import ToolUseBlock

        block1 = MagicMock()
        block1.__class__ = ToolUseBlock
        block1.name = "read_file"
        block1.input = {}

        block2 = MagicMock()
        block2.__class__ = ToolUseBlock
        block2.name = "write_file"
        block2.input = {}

        msg = MagicMock()
        msg.__class__ = AssistantMessage
        msg.content = [block1, block2]

        monitor = StreamMonitor("task-2")
        monitor.process(msg)

        assert monitor.tool_events == ["read_file", "write_file"]

    def test_non_tool_content_blocks_ignored(self) -> None:
        from claude_agent_sdk import AssistantMessage

        # A text block that is NOT a ToolUseBlock
        text_block = MagicMock()
        # Don't set __class__ to ToolUseBlock — it remains MagicMock

        msg = MagicMock()
        msg.__class__ = AssistantMessage
        msg.content = [text_block]

        monitor = StreamMonitor("task-3")
        monitor.process(msg)

        assert monitor.tool_events == []


class TestOrch03Progress:
    """StreamMonitor.process(TaskProgressMessage) does not raise."""

    def test_progress_message_no_raise(self) -> None:
        from claude_agent_sdk.types import TaskProgressMessage

        msg = MagicMock()
        msg.__class__ = TaskProgressMessage

        monitor = StreamMonitor("task-1")
        monitor.process(msg)  # must not raise


class TestOrch03Notification:
    """StreamMonitor.process(TaskNotificationMessage) does not raise."""

    def test_notification_message_no_raise(self) -> None:
        from claude_agent_sdk.types import TaskNotificationMessage

        msg = MagicMock()
        msg.__class__ = TaskNotificationMessage

        monitor = StreamMonitor("task-1")
        monitor.process(msg)  # must not raise


class TestOrch03ResultCapture:
    """StreamMonitor.process(ResultMessage) sets monitor.result_text."""

    def test_result_text_captured(self) -> None:
        from claude_agent_sdk import ResultMessage

        msg = MagicMock()
        msg.__class__ = ResultMessage
        msg.result = "Task completed successfully. Created src/auth.py with JWT logic."

        monitor = StreamMonitor("task-1")
        monitor.process(msg)

        assert monitor.result_text == "Task completed successfully. Created src/auth.py with JWT logic."

    def test_result_text_initially_none(self) -> None:
        monitor = StreamMonitor("task-1")
        assert monitor.result_text is None


class TestOrch03UnknownMessage:
    """StreamMonitor.process(unknown) is a no-op — does not raise."""

    def test_unknown_object_no_raise(self) -> None:
        monitor = StreamMonitor("task-1")
        monitor.process(object())  # must not raise

    def test_string_no_raise(self) -> None:
        monitor = StreamMonitor("task-1")
        monitor.process("some random string")  # must not raise

    def test_tool_events_readonly(self) -> None:
        """tool_events property returns a copy, not the internal list."""
        from claude_agent_sdk import AssistantMessage
        from claude_agent_sdk.types import ToolUseBlock

        tool_block = MagicMock()
        tool_block.__class__ = ToolUseBlock
        tool_block.name = "bash"
        tool_block.input = {}

        msg = MagicMock()
        msg.__class__ = AssistantMessage
        msg.content = [tool_block]

        monitor = StreamMonitor("task-1")
        monitor.process(msg)

        events = monitor.tool_events
        events.append("mutated")  # mutate the returned copy
        assert len(monitor.tool_events) == 1  # internal list unaffected
