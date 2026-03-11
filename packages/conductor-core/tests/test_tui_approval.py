"""Phase 36: Approval Modal tests.

Tests for FileApprovalModal, CommandApprovalModal, and EscalationModal.
All three are ModalScreen subclasses that dismiss with typed return values.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""

import pytest

from textual.app import App, ComposeResult
from textual.widgets import Input


class ModalTestApp(App):
    """Minimal app for modal testing -- no widgets needed."""

    def compose(self) -> ComposeResult:
        return iter([])


# -- FileApprovalModal -------------------------------------------------------


async def test_file_approval_approve():
    """Clicking #approve on FileApprovalModal dismisses with True."""
    from conductor.tui.widgets.modals import FileApprovalModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[bool] = []

        async def show_modal():
            result = await app.push_screen_wait(
                FileApprovalModal("/path/to/file.py")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()
        await pilot.click("#approve")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] is True


async def test_file_approval_deny():
    """Clicking #deny on FileApprovalModal dismisses with False."""
    from conductor.tui.widgets.modals import FileApprovalModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[bool] = []

        async def show_modal():
            result = await app.push_screen_wait(
                FileApprovalModal("/path/to/file.py")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()
        await pilot.click("#deny")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] is False


async def test_file_approval_escape():
    """Pressing Escape on FileApprovalModal dismisses with False."""
    from conductor.tui.widgets.modals import FileApprovalModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[bool] = []

        async def show_modal():
            result = await app.push_screen_wait(
                FileApprovalModal("/path/to/file.py")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] is False


# -- CommandApprovalModal ----------------------------------------------------


async def test_command_approval_approve():
    """Clicking #approve on CommandApprovalModal dismisses with True."""
    from conductor.tui.widgets.modals import CommandApprovalModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[bool] = []

        async def show_modal():
            result = await app.push_screen_wait(
                CommandApprovalModal("rm -rf /tmp/build")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()
        await pilot.click("#approve")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] is True


async def test_command_approval_deny():
    """Clicking #deny on CommandApprovalModal dismisses with False."""
    from conductor.tui.widgets.modals import CommandApprovalModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[bool] = []

        async def show_modal():
            result = await app.push_screen_wait(
                CommandApprovalModal("rm -rf /tmp/build")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()
        await pilot.click("#deny")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] is False


# -- EscalationModal ---------------------------------------------------------


async def test_escalation_modal_submit():
    """EscalationModal shows agent prefix + question; clicking #submit returns reply."""
    from conductor.tui.widgets.modals import EscalationModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[str] = []

        async def show_modal():
            result = await app.push_screen_wait(
                EscalationModal("What should I do?", agent_id="agent-1")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()

        # Type a reply into the Input widget
        reply_input = app.query_one("#reply-input", Input)
        reply_input.value = "test reply"

        await pilot.click("#submit")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] == "test reply"


async def test_escalation_modal_input_submitted():
    """Pressing Enter in the reply input dismisses with the typed value."""
    from conductor.tui.widgets.modals import EscalationModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[str] = []

        async def show_modal():
            result = await app.push_screen_wait(
                EscalationModal("What should I do?", agent_id="agent-1")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()

        # Set value and press Enter
        reply_input = app.query_one("#reply-input", Input)
        reply_input.value = "enter reply"
        await pilot.press("enter")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] == "enter reply"


async def test_escalation_modal_empty_reply_defaults():
    """Empty reply text returns 'proceed' (not empty string)."""
    from conductor.tui.widgets.modals import EscalationModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[str] = []

        async def show_modal():
            result = await app.push_screen_wait(
                EscalationModal("What should I do?")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()
        # Click submit with empty input
        await pilot.click("#submit")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] == "proceed"


async def test_escalation_escape():
    """Pressing Escape on EscalationModal dismisses with 'proceed'."""
    from conductor.tui.widgets.modals import EscalationModal

    app = ModalTestApp()
    async with app.run_test() as pilot:
        result_container: list[str] = []

        async def show_modal():
            result = await app.push_screen_wait(
                EscalationModal("What should I do?")
            )
            result_container.append(result)

        app.call_later(show_modal)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] == "proceed"
