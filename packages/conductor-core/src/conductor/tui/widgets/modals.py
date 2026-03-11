"""Phase 36: Approval modal widgets.

Three ModalScreen subclasses for surfacing agent approval requests
and escalation questions to the user:

- FileApprovalModal(ModalScreen[bool]): file write approval
- CommandApprovalModal(ModalScreen[bool]): command execution approval
- EscalationModal(ModalScreen[str]): escalation question with reply input
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label


class FileApprovalModal(ModalScreen[bool]):
    """Modal for file write approval. Returns True=approve, False=deny."""

    DEFAULT_CSS = """
    FileApprovalModal {
        align: center middle;
    }
    FileApprovalModal #dialog {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    FileApprovalModal .buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self._file_path = file_path

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(f"Approve write to:\n{self._file_path}", id="question")
            with Grid(classes="buttons"):
                yield Button("Approve", variant="success", id="approve")
                yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")

    def action_cancel(self) -> None:
        self.dismiss(False)


class CommandApprovalModal(ModalScreen[bool]):
    """Modal for command execution approval. Returns True=approve, False=deny."""

    DEFAULT_CSS = """
    CommandApprovalModal {
        align: center middle;
    }
    CommandApprovalModal #dialog {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    CommandApprovalModal .buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, command: str) -> None:
        super().__init__()
        self._command = command

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(
                f"Approve command execution?\n{self._command}", id="question"
            )
            with Grid(classes="buttons"):
                yield Button("Approve", variant="success", id="approve")
                yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")

    def action_cancel(self) -> None:
        self.dismiss(False)


class EscalationModal(ModalScreen[str]):
    """Modal for sub-agent escalation questions. Returns reply text."""

    DEFAULT_CSS = """
    EscalationModal {
        align: center middle;
    }
    EscalationModal #dialog {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, question: str, agent_id: str = "") -> None:
        super().__init__()
        self._question = question
        self._agent_id = agent_id

    def compose(self) -> ComposeResult:
        prefix = f"[{self._agent_id}] " if self._agent_id else ""
        with Grid(id="dialog"):
            yield Label(f"{prefix}{self._question}", id="question")
            yield Input(placeholder="Your reply...", id="reply-input")
            yield Button("Submit", variant="primary", id="submit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        reply = self.query_one("#reply-input", Input).value.strip()
        self.dismiss(reply or "proceed")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or "proceed")

    def action_cancel(self) -> None:
        self.dismiss("proceed")
