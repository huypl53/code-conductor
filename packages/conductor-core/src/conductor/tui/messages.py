"""Custom Textual message types — internal event bus for Conductor TUI.

These message classes prevent circular imports and make the event bus
explicit. All async subsystems post messages here; widgets subscribe
to them.
"""
from textual.message import Message


class TokenChunk(Message):
    """A streaming text token from the SDK."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class ToolActivity(Message):
    """A tool use event formatted as a human-readable activity line."""

    def __init__(self, activity_line: str) -> None:
        self.activity_line = activity_line
        super().__init__()


class StreamDone(Message):
    """Streaming response has completed — active cell becomes immutable."""


class TokensUpdated(Message):
    """SDK result message with token usage data."""

    def __init__(self, usage: dict) -> None:
        self.usage = usage
        super().__init__()


class DelegationStarted(Message):
    """A conductor_delegate tool call has begun."""

    def __init__(self, task_description: str) -> None:
        self.task_description = task_description
        super().__init__()


class DelegationComplete(Message):
    """Delegation finished (success or error)."""

    def __init__(self, summary: str, error: bool = False) -> None:
        self.summary = summary
        self.error = error
        super().__init__()


class StreamingStarted(Message):
    """Signal that an AssistantCell should be created in streaming mode."""


class UserSubmitted(Message):
    """User pressed Enter in CommandInput — text ready for transcript."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()


class AgentStateUpdated(Message):
    """State watcher detected a change in state.json."""

    def __init__(self, state: "ConductorState") -> None:
        self.state = state
        super().__init__()


class EscalationRequest(Message):
    """An agent escalation question ready for the approval modal."""

    def __init__(self, question: str, agent_id: str = "") -> None:
        self.question = question
        self.agent_id = agent_id
        super().__init__()
