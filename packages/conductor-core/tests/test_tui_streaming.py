"""Phase 33: Streaming widget lifecycle tests.

Tests that AssistantCell supports streaming mode (thinking -> streaming -> finalized)
and that StatusFooter displays reactive model/mode/tokens/session data.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""
import pytest


async def test_thinking_indicator_appears():
    """Streaming AssistantCell shows LoadingIndicator before any tokens arrive."""
    from textual.app import App, ComposeResult
    from textual.widgets import LoadingIndicator

    from conductor.tui.widgets.transcript import AssistantCell

    class ThinkingApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell()  # streaming mode: no text arg

    app = ThinkingApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        indicators = cell.query(LoadingIndicator)
        assert len(indicators) == 1, "LoadingIndicator should be visible in thinking state"


async def test_token_chunk_routes_to_cell():
    """After start_streaming(), append_token() feeds text into the Markdown widget."""
    from textual.app import App, ComposeResult
    from textual.widgets import Markdown

    from conductor.tui.widgets.transcript import AssistantCell

    class StreamApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell()  # streaming mode

    app = StreamApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        await cell.start_streaming()
        await cell.append_token("Hello")
        # Stop the stream so content is flushed to the Markdown widget
        await cell.finalize()
        await pilot.pause()

        md = cell.query_one(Markdown)
        # After finalize, the accumulated markdown content should contain "Hello"
        assert "Hello" in md._markdown, f"Expected 'Hello' in markdown, got: {md._markdown!r}"


async def test_stream_done_finalizes():
    """After finalize(), _is_streaming is False and _stream is None."""
    from textual.app import App, ComposeResult

    from conductor.tui.widgets.transcript import AssistantCell

    class FinalizeApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell()  # streaming mode

    app = FinalizeApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        await cell.start_streaming()
        await cell.append_token("some text")
        await cell.finalize()
        await pilot.pause()

        assert cell._is_streaming is False, "_is_streaming should be False after finalize"
        assert cell._stream is None, "_stream should be None after finalize"


async def test_status_footer_token_update():
    """TokensUpdated message updates footer's token_count reactive and display."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    from conductor.tui.messages import TokensUpdated
    from conductor.tui.widgets.status_footer import StatusFooter

    class FooterApp(App):
        def compose(self) -> ComposeResult:
            yield StatusFooter()

    app = FooterApp()
    async with app.run_test() as pilot:
        footer = app.query_one(StatusFooter)
        footer.post_message(TokensUpdated({"input_tokens": 100, "output_tokens": 50}))
        await pilot.pause()

        assert footer.token_count == 150, f"Expected 150, got {footer.token_count}"
        left_label = footer.query_one("#status-left", Static)
        label_text = str(left_label._Static__content)
        assert "tokens: 150" in label_text, f"Expected 'tokens: 150' in label, got: {label_text!r}"


async def test_status_footer_session_id():
    """Setting session_id reactive updates the left label."""
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    from conductor.tui.widgets.status_footer import StatusFooter

    class SessionApp(App):
        def compose(self) -> ComposeResult:
            yield StatusFooter()

    app = SessionApp()
    async with app.run_test() as pilot:
        footer = app.query_one(StatusFooter)
        footer.session_id = "abc-123"
        await pilot.pause()

        left_label = footer.query_one("#status-left", Static)
        label_text = str(left_label._Static__content)
        assert "session: abc-123" in label_text, f"Expected 'session: abc-123' in label, got: {label_text!r}"


async def test_submit_creates_streaming_cell():
    """UserSubmitted creates UserCell + streaming AssistantCell and disables CommandInput."""
    from textual.widgets import Input

    from conductor.tui.app import ConductorApp
    from conductor.tui.messages import UserSubmitted
    from conductor.tui.widgets.command_input import CommandInput
    from conductor.tui.widgets.transcript import AssistantCell, TranscriptPane, UserCell

    app = ConductorApp()
    async with app.run_test() as pilot:
        # Post a UserSubmitted message (simulates user typing + Enter)
        app.post_message(UserSubmitted("hello"))
        await pilot.pause()
        await pilot.pause()  # extra pause for mount

        pane = app.query_one(TranscriptPane)
        user_cells = pane.query(UserCell)
        assistant_cells = pane.query(AssistantCell)

        # Should have the welcome AssistantCell + new UserCell + new streaming AssistantCell
        assert len(user_cells) >= 1, f"Expected at least 1 UserCell, got {len(user_cells)}"
        assert len(assistant_cells) >= 2, (
            f"Expected at least 2 AssistantCells (welcome + streaming), got {len(assistant_cells)}"
        )

        # CommandInput should be disabled during streaming
        cmd = app.query_one(CommandInput)
        assert cmd.disabled is True, "CommandInput should be disabled during streaming"


async def test_input_disabled_during_streaming():
    """StreamDone re-enables CommandInput after streaming completes."""
    from textual.widgets import Input

    from conductor.tui.app import ConductorApp
    from conductor.tui.messages import StreamDone
    from conductor.tui.widgets.command_input import CommandInput

    app = ConductorApp()
    async with app.run_test() as pilot:
        cmd = app.query_one(CommandInput)
        # Manually disable (simulating streaming in progress)
        cmd.disabled = True
        await pilot.pause()
        assert cmd.disabled is True, "CommandInput should start disabled for this test"

        # Post StreamDone to re-enable
        app.post_message(StreamDone())
        await pilot.pause()

        assert cmd.disabled is False, "CommandInput should be re-enabled after StreamDone"
