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
        await pilot.pause()

        md = cell.query_one(Markdown)
        # Markdown widget should contain the streamed text
        assert "Hello" in md._markdown_content or "Hello" in str(md.render())


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
        app.post_message(TokensUpdated({"input_tokens": 100, "output_tokens": 50}))
        await pilot.pause()

        assert footer.token_count == 150, f"Expected 150, got {footer.token_count}"
        left_label = footer.query_one("#status-left", Static)
        assert "tokens: 150" in left_label.renderable, f"Expected 'tokens: 150' in label"


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
        assert "session: abc-123" in left_label.renderable, f"Expected 'session: abc-123' in label"
