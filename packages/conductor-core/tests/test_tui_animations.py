"""Phase 41: Cell fade-in animation tests (VIS-03 and VIS-04).

Tests that UserCell and AssistantCell fade from opacity 0 to 1 on mount,
and that CONDUCTOR_NO_ANIMATIONS=1 disables the animation entirely.

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""

import pytest


async def test_user_cell_fade_in():
    """UserCell fades from opacity 0 to 1 over ~0.25s when mounted."""
    from textual.app import App, ComposeResult

    from conductor.tui.widgets.transcript import UserCell

    class FadeApp(App):
        def compose(self) -> ComposeResult:
            yield UserCell("hello")

    app = FadeApp()
    async with app.run_test() as pilot:
        cell = app.query_one(UserCell)
        await pilot.pause(0.4)
        assert cell.styles.opacity == 1.0, (
            f"UserCell opacity should be 1.0 after fade-in, got {cell.styles.opacity}"
        )


async def test_assistant_cell_fade_in():
    """AssistantCell (static mode) fades from opacity 0 to 1 over ~0.25s when mounted."""
    from textual.app import App, ComposeResult

    from conductor.tui.widgets.transcript import AssistantCell

    class FadeApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell("response text")

    app = FadeApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        await pilot.pause(0.4)
        assert cell.styles.opacity == 1.0, (
            f"AssistantCell opacity should be 1.0 after fade-in, got {cell.styles.opacity}"
        )


async def test_shimmer_unchanged_after_fade_in():
    """AssistantCell shimmer (tint) is unaffected by the opacity fade-in animation."""
    from textual.app import App, ComposeResult
    from textual.color import Color

    from conductor.tui.widgets.transcript import AssistantCell

    class ShimmerFadeApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell()  # streaming mode

    app = ShimmerFadeApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        await cell.start_streaming()
        await pilot.pause(0.2)
        # Shimmer should be active — tint should not be transparent
        tint = cell.styles.tint
        assert tint != Color(0, 0, 0, 0.0), (
            f"Shimmer should be active (tint != transparent), got {tint}"
        )


async def test_no_animations_env_var():
    """When _ANIMATIONS is False, cells appear at full opacity instantly (no animate call)."""
    from textual.app import App, ComposeResult

    import conductor.tui.widgets.transcript as t_mod
    from conductor.tui.widgets.transcript import UserCell

    original = t_mod._ANIMATIONS
    t_mod._ANIMATIONS = False
    try:

        class NoAnimApp(App):
            def compose(self) -> ComposeResult:
                yield UserCell("hello")

        app = NoAnimApp()
        async with app.run_test() as pilot:
            cell = app.query_one(UserCell)
            await pilot.pause()
            assert cell.styles.opacity == 1.0, (
                f"With _ANIMATIONS=False, opacity should be 1.0 immediately, got {cell.styles.opacity}"
            )
    finally:
        t_mod._ANIMATIONS = original


async def test_animations_flag_module_level():
    """_ANIMATIONS is a module-level bool constant in transcript.py."""
    import conductor.tui.widgets.transcript as t_mod

    assert hasattr(t_mod, "_ANIMATIONS"), (
        "transcript module should have _ANIMATIONS attribute"
    )
    assert isinstance(t_mod._ANIMATIONS, bool), (
        f"_ANIMATIONS should be bool, got {type(t_mod._ANIMATIONS)}"
    )
