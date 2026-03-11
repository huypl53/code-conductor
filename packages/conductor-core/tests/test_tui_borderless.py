"""Phase 40: Borderless design — VIS-01 and VIS-02 CSS regression tests."""
from conductor.tui.widgets.transcript import UserCell, AssistantCell
from conductor.tui.widgets.command_input import CommandInput
from conductor.tui.widgets.agent_monitor import AgentMonitorPane
from conductor.tui.widgets.modals import (
    CommandApprovalModal,
    EscalationModal,
    FileApprovalModal,
)


def test_command_input_no_border_top():
    """VIS-01: CommandInput has no border-top separator."""
    assert "border-top" not in CommandInput.DEFAULT_CSS


def test_user_cell_subtle_border():
    """VIS-02: UserCell has a subtle solid accent line, not thick."""
    css = UserCell.DEFAULT_CSS
    assert "thick" not in css
    assert "border-left" in css
    assert "solid" in css


def test_assistant_cell_subtle_border():
    """VIS-02: AssistantCell has a subtle solid accent line, not thick."""
    css = AssistantCell.DEFAULT_CSS
    assert "thick" not in css
    assert "border-left" in css
    assert "solid" in css


def test_agent_monitor_retains_border_left():
    """Guard: AgentMonitorPane column separator is unchanged."""
    css = AgentMonitorPane.DEFAULT_CSS
    assert "border-left" in css
    assert "solid $primary 20%" in css


def test_modal_dialogs_retain_border():
    """Guard: All three modal #dialog borders are unchanged."""
    assert "border: solid $primary" in FileApprovalModal.DEFAULT_CSS
    assert "border: solid $primary" in CommandApprovalModal.DEFAULT_CSS
    assert "border: solid $primary" in EscalationModal.DEFAULT_CSS
