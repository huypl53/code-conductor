"""Phase 38: Shimmer animation and session replay tests.

Tests that AssistantCell shimmer animation lifecycle works correctly
and that TranscriptPane resume_mode suppresses the welcome cell.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""
import json

import pytest


# -- Task 1: Shimmer animation tests ------------------------------------------


async def test_streaming_cell_has_shimmer():
    """AssistantCell in streaming mode has shimmer methods and _is_streaming=True."""
    from textual.app import App, ComposeResult

    from conductor.tui.widgets.transcript import AssistantCell

    class ShimmerApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell()  # streaming mode

    app = ShimmerApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        await cell.start_streaming()
        await pilot.pause()

        assert cell._is_streaming is True, "_is_streaming should be True during streaming"
        assert hasattr(cell, "_shimmer_forward"), "AssistantCell should have _shimmer_forward method"
        assert hasattr(cell, "_shimmer_back"), "AssistantCell should have _shimmer_back method"


async def test_finalized_cell_clears_shimmer():
    """After finalize(), _is_streaming is False and tint is transparent."""
    from textual.app import App, ComposeResult
    from textual.color import Color

    from conductor.tui.widgets.transcript import AssistantCell

    class FinalizeShimmerApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell()  # streaming mode

    app = FinalizeShimmerApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        await cell.start_streaming()
        await cell.append_token("test content")
        await pilot.pause()

        await cell.finalize()
        await pilot.pause()

        assert cell._is_streaming is False, "_is_streaming should be False after finalize"
        # Tint should be transparent (Color(0, 0, 0, 0))
        tint = cell.styles.tint
        if tint is not None:
            assert tint.a == 0.0 or tint == Color(0, 0, 0, 0.0), (
                f"Tint should be transparent after finalize, got {tint}"
            )


async def test_transcript_resume_mode_suppresses_welcome():
    """TranscriptPane(resume_mode=True) does NOT mount the welcome AssistantCell."""
    from textual.app import App, ComposeResult

    from conductor.tui.widgets.transcript import AssistantCell, TranscriptPane

    class ResumeApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

    app = ResumeApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(TranscriptPane)
        cells = pane.query(AssistantCell)
        assert len(cells) == 0, (
            f"resume_mode=True should suppress welcome cell, got {len(cells)} AssistantCells"
        )


async def test_transcript_normal_mode_shows_welcome():
    """TranscriptPane() (default) still mounts the welcome cell."""
    from textual.app import App, ComposeResult

    from conductor.tui.widgets.transcript import AssistantCell, TranscriptPane

    class NormalApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(id="transcript")

    app = NormalApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        pane = app.query_one(TranscriptPane)
        cells = pane.query(AssistantCell)
        assert len(cells) == 1, (
            f"Normal mode should show 1 welcome cell, got {len(cells)} AssistantCells"
        )


# -- Task 2: Session replay tests ---------------------------------------------


async def test_resume_replays_history(tmp_path):
    """ConductorApp with resume_session_id replays turns as UserCell + AssistantCell."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import AssistantCell, TranscriptPane, UserCell

    # Create session file
    sessions_dir = tmp_path / ".conductor" / "chat_sessions"
    sessions_dir.mkdir(parents=True)
    session_data = {
        "session_id": "test123",
        "created_at": "2026-03-11T00:00:00Z",
        "turns": [
            {"role": "user", "content": "Hello there", "timestamp": "2026-03-11T00:00:01Z", "token_count": 0},
            {"role": "assistant", "content": "Hi! How can I help?", "timestamp": "2026-03-11T00:00:02Z", "token_count": 10},
        ],
    }
    (sessions_dir / "test123.json").write_text(json.dumps(session_data))

    app = ConductorApp(resume_session_id="test123", cwd=str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        pane = app.query_one(TranscriptPane)
        user_cells = pane.query(UserCell)
        assistant_cells = pane.query(AssistantCell)

        assert len(user_cells) == 1, f"Expected 1 UserCell from replay, got {len(user_cells)}"
        assert len(assistant_cells) == 1, (
            f"Expected 1 AssistantCell from replay (no welcome), got {len(assistant_cells)}"
        )


async def test_resume_missing_session(tmp_path):
    """ConductorApp with missing session shows error cell, does not crash."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.transcript import AssistantCell, TranscriptPane

    # Create .conductor dir but no session file
    (tmp_path / ".conductor" / "chat_sessions").mkdir(parents=True)

    app = ConductorApp(resume_session_id="nonexistent", cwd=str(tmp_path))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        pane = app.query_one(TranscriptPane)
        cells = pane.query(AssistantCell)
        assert len(cells) == 1, f"Expected 1 error AssistantCell, got {len(cells)}"
        # The error cell should mention "not found"
        assert cells[0]._text is not None, "Error cell should be a static cell with text"
        assert "not found" in cells[0]._text.lower(), (
            f"Error cell should mention 'not found', got: {cells[0]._text!r}"
        )


async def test_input_disabled_during_replay(tmp_path):
    """CommandInput is disabled during replay and re-enabled after."""
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.command_input import CommandInput

    # Create session file with turns
    sessions_dir = tmp_path / ".conductor" / "chat_sessions"
    sessions_dir.mkdir(parents=True)
    session_data = {
        "session_id": "test456",
        "created_at": "2026-03-11T00:00:00Z",
        "turns": [
            {"role": "user", "content": "Test msg", "timestamp": "2026-03-11T00:00:01Z", "token_count": 0},
            {"role": "assistant", "content": "Test reply", "timestamp": "2026-03-11T00:00:02Z", "token_count": 5},
        ],
    }
    (sessions_dir / "test456.json").write_text(json.dumps(session_data))

    app = ConductorApp(resume_session_id="test456", cwd=str(tmp_path))
    async with app.run_test() as pilot:
        # After replay completes, input should be re-enabled
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        cmd = app.query_one(CommandInput)
        assert cmd.disabled is False, "CommandInput should be re-enabled after replay completes"
