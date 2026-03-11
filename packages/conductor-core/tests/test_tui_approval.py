"""Phase 36: Approval Modal tests.

Tests for FileApprovalModal, CommandApprovalModal, and EscalationModal.
All three are ModalScreen subclasses that dismiss with typed return values.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)

Test pattern: push_screen() with a callback to capture the dismiss result,
since push_screen_wait() requires a worker context.
Use app.screen to query widgets on the currently active (modal) screen.
"""

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

        app.push_screen(
            FileApprovalModal("/path/to/file.py"),
            callback=lambda r: result_container.append(r),
        )
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

        app.push_screen(
            FileApprovalModal("/path/to/file.py"),
            callback=lambda r: result_container.append(r),
        )
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

        app.push_screen(
            FileApprovalModal("/path/to/file.py"),
            callback=lambda r: result_container.append(r),
        )
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

        app.push_screen(
            CommandApprovalModal("rm -rf /tmp/build"),
            callback=lambda r: result_container.append(r),
        )
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

        app.push_screen(
            CommandApprovalModal("rm -rf /tmp/build"),
            callback=lambda r: result_container.append(r),
        )
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

        app.push_screen(
            EscalationModal("What should I do?", agent_id="agent-1"),
            callback=lambda r: result_container.append(r),
        )
        await pilot.pause()

        # Type a reply into the Input widget on the active (modal) screen
        reply_input = app.screen.query_one("#reply-input", Input)
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

        app.push_screen(
            EscalationModal("What should I do?", agent_id="agent-1"),
            callback=lambda r: result_container.append(r),
        )
        await pilot.pause()

        # Set value and press Enter
        reply_input = app.screen.query_one("#reply-input", Input)
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

        app.push_screen(
            EscalationModal("What should I do?"),
            callback=lambda r: result_container.append(r),
        )
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

        app.push_screen(
            EscalationModal("What should I do?"),
            callback=lambda r: result_container.append(r),
        )
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert len(result_container) == 1
        assert result_container[0] == "proceed"


# -- Integration: escalation queue -> modal -> reply -------------------------


async def test_escalation_queue_shows_modal(tmp_path):
    """Putting a HumanQuery on human_out triggers EscalationModal; reply reaches human_in."""
    import asyncio
    from conductor.tui.app import ConductorApp
    from conductor.orchestrator.escalation import HumanQuery

    app = ConductorApp(cwd=str(tmp_path))
    async with app.run_test() as pilot:
        human_out: asyncio.Queue = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()

        # Start the watcher worker
        app._watch_escalations(human_out, human_in)
        await pilot.pause()

        # Put a HumanQuery on the queue
        await human_out.put(
            HumanQuery(question="Delete prod DB?", context={"agent_id": "agent-42"})
        )
        await pilot.pause()
        await pilot.pause()

        # Modal should be on the screen stack
        assert len(app.screen_stack) > 1

        # Type a reply and submit
        reply_input = app.screen.query_one("#reply-input", Input)
        reply_input.value = "yes delete it"
        await pilot.click("#submit")
        await pilot.pause()
        await pilot.pause()

        # Reply should have reached human_in
        reply = human_in.get_nowait()
        assert reply == "yes delete it"


async def test_modal_dismisses_and_input_refocuses(tmp_path):
    """After modal dismissal, CommandInput's inner Input widget has focus."""
    import asyncio
    from conductor.tui.app import ConductorApp
    from conductor.orchestrator.escalation import HumanQuery

    app = ConductorApp(cwd=str(tmp_path))
    async with app.run_test() as pilot:
        human_out: asyncio.Queue = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()

        # Start the watcher worker
        app._watch_escalations(human_out, human_in)
        await pilot.pause()

        # Put a HumanQuery on the queue
        await human_out.put(
            HumanQuery(question="Should I proceed?", context={"agent_id": "agent-7"})
        )
        await pilot.pause()
        await pilot.pause()

        # Submit the modal
        reply_input = app.screen.query_one("#reply-input", Input)
        reply_input.value = "go ahead"
        await pilot.click("#submit")
        await pilot.pause()
        await pilot.pause()

        # Modal should be dismissed (back to single screen)
        assert len(app.screen_stack) == 1

        # CommandInput's inner Input should have focus
        from conductor.tui.widgets.command_input import CommandInput
        cmd_input = app.query_one(CommandInput).query_one(Input)
        assert cmd_input.has_focus
