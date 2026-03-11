"""Phase 34: Rich output tests — syntax highlighting, markdown formatting, diff colors.

Tests that RichMarkdown provides:
- TRNS-03: Code fences render with syntax highlight spans
- TRNS-04: Markdown elements render as correct Textual widget types
- TRNS-05: Diff fences render with green/red colored spans

IMPORTANT: Keep run_test() inline in each test function -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)
"""
import pytest


async def test_code_fence_has_spans():
    """TRNS-03: Code fence with language renders with syntax highlight spans."""
    from textual.app import App, ComposeResult
    from textual.widgets._markdown import MarkdownFence

    from conductor.tui.widgets.rich_markdown import RichMarkdown

    CODE_MD = "```python\ndef hello():\n    pass\n```\n"

    class CodeApp(App):
        def compose(self) -> ComposeResult:
            yield RichMarkdown(CODE_MD)

    app = CodeApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        fences = app.query(MarkdownFence)
        assert len(fences) >= 1, "Expected at least one MarkdownFence"
        # The highlighted content should have spans (syntax coloring, not plain text)
        assert len(fences[0]._highlighted_code.spans) > 0, (
            "Expected syntax highlight spans in code fence"
        )


async def test_markdown_elements():
    """TRNS-04: Markdown with heading, bold, list, blockquote renders correct widget types."""
    from textual.app import App, ComposeResult
    from textual.widgets._markdown import (
        MarkdownBlockQuote,
        MarkdownBulletList,
        MarkdownH1,
    )

    from conductor.tui.widgets.rich_markdown import RichMarkdown

    MARKDOWN = """\
# Heading One

**Bold text** here.

- Item one
- Item two

> A blockquote
"""

    class MdApp(App):
        def compose(self) -> ComposeResult:
            yield RichMarkdown(MARKDOWN)

    app = MdApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        md = app.query_one(RichMarkdown)
        assert md.query(MarkdownH1), "Expected MarkdownH1 for heading"
        assert md.query(MarkdownBulletList), "Expected MarkdownBulletList for bullet list"
        assert md.query(MarkdownBlockQuote), "Expected MarkdownBlockQuote for blockquote"


async def test_diff_fence_colors():
    """TRNS-05: Diff fence with +/- lines has colored spans for insertions/deletions."""
    from textual.app import App, ComposeResult

    from conductor.tui.widgets.rich_markdown import DiffAwareFence, RichMarkdown

    DIFF_MD = "```diff\n-old line\n+new line\n```\n"

    class DiffApp(App):
        def compose(self) -> ComposeResult:
            yield RichMarkdown(DIFF_MD)

    app = DiffApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        fences = app.query(DiffAwareFence)
        assert len(fences) >= 1, "Expected at least one DiffAwareFence"
        spans = fences[0]._highlighted_code.spans
        assert len(spans) > 0, "Expected colored spans in diff fence"
        # Check that spans contain green/red styling for insertions/deletions
        styles = {str(s.style) for s in spans}
        assert any("green" in s for s in styles), (
            f"Expected green spans for + lines, got styles: {styles}"
        )
        assert any("red" in s for s in styles), (
            f"Expected red spans for - lines, got styles: {styles}"
        )
