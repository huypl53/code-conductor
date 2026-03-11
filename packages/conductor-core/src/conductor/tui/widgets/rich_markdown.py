"""Rich Markdown widget with diff-aware syntax highlighting.

Extends Textual's Markdown widget to add green/red coloring for diff fences.
Textual's built-in HighlightTheme lacks Token.Generic.Inserted/Deleted mappings,
so unified diff fences render without color. This module fixes that via:

- DiffHighlightTheme: Adds green (Inserted) and red (Deleted) mappings
- DiffAwareFence: Uses DiffHighlightTheme for diff/udiff fences only
- RichMarkdown: Markdown subclass that registers DiffAwareFence for fence blocks

Phase 34 — TRNS-03 (syntax highlighting), TRNS-04 (markdown formatting),
TRNS-05 (diff coloring).
"""
from __future__ import annotations

from pygments.token import Token
from textual.content import Content
from textual.highlight import HighlightTheme, highlight
from textual.widgets._markdown import Markdown, MarkdownFence


class DiffHighlightTheme(HighlightTheme):
    """Extends the default theme to color diff additions green and deletions red."""

    STYLES = {
        **HighlightTheme.STYLES,
        Token.Generic.Inserted: "bold green",
        Token.Generic.Deleted: "bold red",
    }


class DiffAwareFence(MarkdownFence):
    """MarkdownFence that uses DiffHighlightTheme for diff/udiff fences."""

    @classmethod
    def highlight(cls, code: str, language: str) -> Content:
        theme = DiffHighlightTheme if language in ("diff", "udiff") else HighlightTheme
        return highlight(code, language=language or None, theme=theme)


class RichMarkdown(Markdown):
    """Markdown widget with diff-aware syntax highlighting.

    Registers DiffAwareFence for fence and code_block tokens so that
    diff fences get green/red coloring while all other code fences
    use the standard HighlightTheme.
    """

    BLOCKS = {
        **Markdown.BLOCKS,
        "fence": DiffAwareFence,
        "code_block": DiffAwareFence,
    }
