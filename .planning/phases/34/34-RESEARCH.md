# Phase 34: Rich Output - Research

**Researched:** 2026-03-11
**Domain:** Textual Markdown widget, Pygments syntax highlighting, diff rendering
**Confidence:** HIGH

## Summary

Phase 34 has three requirements: code block syntax highlighting (TRNS-03), markdown formatting (TRNS-04), and diff rendering with green/red lines (TRNS-05). The good news is that two of the three are largely free: Textual's `Markdown` widget already provides syntax highlighting for code fences via Pygments and already renders headings, bold, lists, and blockquotes correctly. The project is already using `MarkdownStream` from Phase 33, so the streaming infrastructure is in place.

The only requirement that needs real work is TRNS-05 (diff rendering). Pygments has a `diff` lexer that correctly identifies `Token.Generic.Inserted` and `Token.Generic.Deleted` tokens, but Textual's built-in `HighlightTheme.STYLES` dict does not map these token types — so ```` ```diff ```` fences render without color. The fix is a one-file extension: subclass `HighlightTheme` to add green/red mappings, subclass `MarkdownFence` to use the extended theme, and register it in a subclassed `Markdown` widget via the `BLOCKS` override.

**Primary recommendation:** Subclass Textual's `Markdown` widget into a `RichMarkdown` widget that registers a `DiffAwareFence` in its `BLOCKS` dict. `DiffAwareFence` overrides `highlight()` to use a `DiffHighlightTheme` that adds `Token.Generic.Inserted → green` and `Token.Generic.Deleted → red`. Replace `Markdown("")` in `AssistantCell.start_streaming()` with `RichMarkdown("")`. TRNS-03 and TRNS-04 become verifiable via CSS inspection tests with zero code changes.

## Standard Stack

### Core (already installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | 8.1.1 | Markdown widget, MarkdownStream, MarkdownFence | Already in use |
| pygments | bundled with textual | Syntax highlighting lexers | Used internally by textual.highlight |
| markdown-it-py | bundled with textual | Markdown parsing | Used by Textual's Markdown widget |

### No New Dependencies
Phase 34 requires zero new packages. All capabilities exist in the installed Textual 8.1.1.

## Architecture Patterns

### What Textual's Markdown Widget Already Provides

Verified directly from source at `.venv/lib/python3.13/site-packages/textual/widgets/_markdown.py`:

| Markdown Element | Widget Class | Styling |
|-----------------|--------------|---------|
| H1 | `MarkdownH1` | `$markdown-h1-color`, `$markdown-h1-text-style` (bold by default) |
| H2-H6 | `MarkdownH2`-`MarkdownH6` | Themed colors, various text styles |
| Paragraphs | `MarkdownParagraph` | Standard text |
| Bold (`**text**`) | inline `.strong` span | `text-style: bold` |
| Italic (`*text*`) | inline `.em` span | `text-style: italic` |
| Inline code (`` `code` ``) | inline `.code_inline` span | `background: $warning 10%` |
| Bullet lists | `MarkdownBulletList` + `MarkdownBullet` | Unicode bullets (•, ▪, ‣...), proper indentation |
| Ordered lists | `MarkdownOrderedList` | Numbered with alignment |
| Block quotes | `MarkdownBlockQuote` | `border-left: outer $text-primary 50%`, boosted background |
| Code fences | `MarkdownFence` | Syntax highlighted via Pygments, dark background |
| Tables | `MarkdownTable` | Grid layout with header/cell styling |
| Horizontal rules | `MarkdownHorizontalRule` | Bottom border |

**Conclusion for TRNS-04:** All required markdown elements (headings, bold, lists, blockquotes) are rendered with proper visual formatting by the base `Markdown` widget. TRNS-04 is satisfied by the existing Phase 33 implementation — no code changes needed, only verification tests.

### How Code Block Syntax Highlighting Works (TRNS-03)

Verified from `_markdown.py` lines 875-907 and `highlight.py`:

```python
# Source: .venv/.../textual/widgets/_markdown.py line 885-887
@classmethod
def highlight(cls, code: str, language: str) -> Content:
    return highlight(code, language=language or None)
```

- `token.info` = the language identifier after the fence opening (e.g., `python` from ` ```python`)
- `MarkdownFence.__init__` stores `self.lexer = token.info` and calls `self.highlight(code, lexer)`
- `textual.highlight.highlight()` uses `pygments.lexers.get_lexer_by_name(language)` with fallback to plain text
- Highlighting produces a `Content` object with `Span` objects carrying `HighlightTheme` style strings

**Conclusion for TRNS-03:** Syntax highlighting works out of the box for any language Pygments knows. The existing `AssistantCell` uses `Markdown("")` — once tokens with ` ```python` fences stream in, they will be syntax highlighted automatically. TRNS-03 is satisfied by the existing implementation. Only verification tests needed.

### The Diff Gap (TRNS-05)

Verified from `highlight.py` lines 16-52 and Pygments diff lexer test:

```python
# Source: .venv/.../textual/highlight.py — HighlightTheme.STYLES dict
# PRESENT:
Token.Generic.Strong: "bold",
Token.Generic.Emph: "italic",
Token.Generic.Error: "$text-error on $error-muted",
Token.Generic.Heading: "$text-primary underline",
Token.Generic.Subheading: "$text-primary",
# ABSENT (the gap):
# Token.Generic.Inserted — not mapped → falls through with no color
# Token.Generic.Deleted  — not mapped → falls through with no color
```

Pygments diff lexer tokenization (verified by running it):
```
Token.Generic.Deleted  → "--- a/file.py" and "-old line"
Token.Generic.Inserted → "+++ b/file.py" and "+new line"
Token.Generic.Subheading → "@@ -1,3 +1,3 @@"
Token.Text             → " context line"
```

The `Token.Generic.Subheading` IS in the theme (renders as `$text-primary`) so hunk headers get color. But `Inserted` and `Deleted` lines get no color styling — they render as plain white/foreground text.

### Pattern: Subclassing MarkdownFence for Diff Colors

The correct extension pattern:

```python
# Source: pattern derived from .venv/.../textual/widgets/_markdown.py
# and .venv/.../textual/highlight.py

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
        return highlight(code, language=language or None, theme=DiffHighlightTheme)


class RichMarkdown(Markdown):
    """Markdown widget with diff-aware syntax highlighting."""

    BLOCKS = {
        **Markdown.BLOCKS,
        "fence": DiffAwareFence,
        "code_block": DiffAwareFence,
    }
```

Then in `AssistantCell.start_streaming()`:
```python
# Change:
self._markdown = Markdown("")
# To:
from conductor.tui.widgets.rich_markdown import RichMarkdown
self._markdown = RichMarkdown("")
```

### Recommended File Structure

```
packages/conductor-core/src/conductor/tui/widgets/
├── transcript.py          # Existing — change Markdown → RichMarkdown import
├── rich_markdown.py       # NEW — DiffHighlightTheme, DiffAwareFence, RichMarkdown
└── ...
```

### Anti-Patterns to Avoid

- **Monkey-patching `HighlightTheme.STYLES`:** Global mutation affects all Textual code blocks, not just diff fences. Use subclassing.
- **Subclassing `Markdown` without extending `BLOCKS`:** Python dict inheritance means `BLOCKS` is a class variable shared from the parent unless explicitly overridden with `{**Markdown.BLOCKS, ...}`.
- **Passing `theme=DiffHighlightTheme` for all fences:** Only diff/udiff fences benefit. Non-diff code uses the default theme fine.
- **Using `rich.syntax.Syntax` directly:** Textual 8.x uses `Content`-based rendering, not `rich.syntax.Syntax`. Don't mix the two systems.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown parsing | Custom parser | Textual Markdown widget | Already integrated, GFM-like parser |
| Syntax highlighting | Custom tokenizer | Pygments via textual.highlight | 300+ languages, already wired into MarkdownFence |
| Diff tokenization | Regex line scanning | Pygments `diff` lexer | Handles all unified diff edge cases |
| Streaming markdown | Manual widget updates | MarkdownStream.write() | Already implemented in Phase 33 |

## Common Pitfalls

### Pitfall 1: Thinking TRNS-04 Needs Code
**What goes wrong:** Writing a custom markdown renderer when Textual already handles headings, bold, lists, blockquotes.
**Why it happens:** Not reading the source before coding.
**How to avoid:** Verify by running a test that streams markdown with headings/bold/lists and asserts the widget tree contains `MarkdownH1`, `MarkdownBulletList`, etc.
**Warning signs:** Writing CSS for `.markdown-heading` when `MarkdownH1` DEFAULT_CSS already exists.

### Pitfall 2: DiffAwareFence Applies Wrong Theme to Non-Diff Fences
**What goes wrong:** If `DiffAwareFence` is used for ALL fences, the theme runs for Python/JS/etc. fences too — unnecessary but harmless since non-diff tokens like `Token.Keyword` still resolve correctly. However, it's cleaner to apply `DiffHighlightTheme` only when `language == "diff"` or `"udiff"`.
**How to avoid:** Override `highlight()` conditionally:
```python
@classmethod
def highlight(cls, code: str, language: str) -> Content:
    theme = DiffHighlightTheme if language in ("diff", "udiff") else HighlightTheme
    return highlight(code, language=language or None, theme=theme)
```
**Warning signs:** Non-diff code blocks rendering slightly differently.

### Pitfall 3: MarkdownStream Token Boundaries Break Code Fences
**What goes wrong:** Tokens streaming in mid-fence (e.g., ` ```py` arrives as one chunk, `thon` as the next) causes the Markdown widget to try parsing incomplete fences.
**Why it happens:** MarkdownStream accumulates fragments and re-renders the full accumulated markdown on each write — not a true incremental parser.
**How to avoid:** This is already handled by `MarkdownStream._run()` which calls `self.markdown_widget.append(new_markdown)` with the full accumulated string, not just the delta. The Markdown widget re-parses from scratch on each append call. No special handling needed.
**Warning signs:** Code blocks appearing as plain text during streaming.

### Pitfall 4: Testing MarkdownFence Highlighting Requires Mounted App
**What goes wrong:** Calling `MarkdownFence.highlight()` directly works, but asserting the rendered widget content requires the widget to be mounted in an App and rendered.
**How to avoid:** Use `run_test()` pilot pattern (same as Phase 33 tests), then query `MarkdownFence` and inspect its `_highlighted_code` content object spans.
**Warning signs:** Tests pass but don't actually verify colors.

## Code Examples

### Creating RichMarkdown Widget
```python
# Source: derived from .venv/.../textual/widgets/_markdown.py class Markdown
# and .venv/.../textual/highlight.py class HighlightTheme

from pygments.token import Token
from textual.content import Content
from textual.highlight import HighlightTheme, highlight
from textual.widgets._markdown import Markdown, MarkdownFence


class DiffHighlightTheme(HighlightTheme):
    STYLES = {
        **HighlightTheme.STYLES,
        Token.Generic.Inserted: "bold green",
        Token.Generic.Deleted: "bold red",
    }


class DiffAwareFence(MarkdownFence):
    @classmethod
    def highlight(cls, code: str, language: str) -> Content:
        theme = DiffHighlightTheme if language in ("diff", "udiff") else HighlightTheme
        return highlight(code, language=language or None, theme=theme)


class RichMarkdown(Markdown):
    BLOCKS = {
        **Markdown.BLOCKS,
        "fence": DiffAwareFence,
        "code_block": DiffAwareFence,
    }
```

### Wiring RichMarkdown into AssistantCell
```python
# Source: packages/conductor-core/src/conductor/tui/widgets/transcript.py
# Change start_streaming() method:

async def start_streaming(self) -> None:
    try:
        indicator = self.query_one(LoadingIndicator)
        await indicator.remove()
    except Exception:
        pass
    from conductor.tui.widgets.rich_markdown import RichMarkdown
    self._markdown = RichMarkdown("")
    await self.mount(self._markdown)
    self._stream = Markdown.get_stream(self._markdown)
```

### Test Pattern: Verify Syntax Highlighting
```python
# Source: pattern from test_tui_streaming.py
async def test_code_fence_syntax_highlighting():
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AssistantCell

    class CodeApp(App):
        def compose(self) -> ComposeResult:
            yield AssistantCell()

    app = CodeApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AssistantCell)
        await cell.start_streaming()
        await cell.append_token("```python\ndef hello():\n    pass\n```\n")
        await cell.finalize()
        await pilot.pause()

        from textual.widgets._markdown import MarkdownFence
        fences = cell.query(MarkdownFence)
        assert len(fences) == 1
        # The highlighted content has spans (not plain text)
        assert len(fences[0]._highlighted_code.spans) > 0
```

### Test Pattern: Verify Diff Colors
```python
async def test_diff_fence_has_green_red_spans():
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.rich_markdown import DiffAwareFence, RichMarkdown

    DIFF = "```diff\n-old line\n+new line\n```\n"

    class DiffApp(App):
        def compose(self) -> ComposeResult:
            yield RichMarkdown(DIFF)

    app = DiffApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        fence = app.query_one(DiffAwareFence)
        spans = fence._highlighted_code.spans
        styles = {str(s.style) for s in spans}
        assert any("green" in s for s in styles), "Expected green spans for + lines"
        assert any("red" in s for s in styles), "Expected red spans for - lines"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Rich `Syntax` widget for code blocks | Textual `MarkdownFence` with `textual.highlight` | Textual 0.47+ | Content-based rendering, theme-aware colors |
| Manual diff parsing with ANSI codes | Pygments `diff` lexer | Always available | Handles all unified diff edge cases |
| `MarkdownStream.append()` | `MarkdownStream.write()` | Textual 8.x | Confirmed in Phase 33 |

**Deprecated/outdated:**
- Using `rich.syntax.Syntax` directly in Textual 8.x: Textual migrated to `Content`-based rendering, not Rich renderables.

## Open Questions

1. **Do diff spans survive MarkdownStream accumulation during streaming?**
   - What we know: MarkdownStream re-renders the full accumulated text on each write via `markdown.append()`, which calls `_build_from_source()` which re-parses from scratch.
   - What's unclear: A code fence mid-stream (fence open token received, code body not yet received) will parse as plain text until the closing backticks arrive.
   - Recommendation: This is inherent to incremental markdown streaming. Acceptable UX — the code block will "pop" into highlighted form when the closing fence arrives. No workaround needed; document this behavior.

2. **CSS color variable availability: `"bold green"` vs `"bold $text-success"`?**
   - What we know: `HighlightTheme.STYLES` already uses both raw colors (`"bold"`) and CSS variables (`"$text-accent"`).
   - What's unclear: Whether `"green"` and `"red"` as raw color names resolve correctly in all Textual themes.
   - Recommendation: Use `"$text-success"` for green and `"$text-error"` for red to respect the app's theme. Verify in tests.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `packages/conductor-core/pyproject.toml` |
| Quick run command | `uv run pytest tests/test_tui_rich_output.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRNS-03 | Code fence with language renders with syntax color spans | unit | `uv run pytest tests/test_tui_rich_output.py::test_code_fence_has_spans -x` | ❌ Wave 0 |
| TRNS-04 | Markdown with heading/bold/list renders correct widget types | unit | `uv run pytest tests/test_tui_rich_output.py::test_markdown_elements -x` | ❌ Wave 0 |
| TRNS-05 | Diff fence with +/- lines has green/red color spans | unit | `uv run pytest tests/test_tui_rich_output.py::test_diff_fence_colors -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_tui_rich_output.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui_rich_output.py` — covers TRNS-03, TRNS-04, TRNS-05
- [ ] `packages/conductor-core/src/conductor/tui/widgets/rich_markdown.py` — DiffHighlightTheme, DiffAwareFence, RichMarkdown

*(Existing test infrastructure (pytest-asyncio, run_test pilot pattern) covers all phase requirements — only new test file and new widget file needed)*

## Sources

### Primary (HIGH confidence)
- `.venv/lib/python3.13/site-packages/textual/widgets/_markdown.py` — MarkdownFence.highlight(), BLOCKS dict, all widget CSS, MarkdownStream source
- `.venv/lib/python3.13/site-packages/textual/highlight.py` — HighlightTheme.STYLES dict, highlight() function
- Runtime verification: `python3 -c "from pygments.lexers import get_lexer_by_name; l = get_lexer_by_name('diff'); ..."` — confirmed diff lexer token types
- Runtime verification: `textual.__version__ == "8.1.1"` — confirmed installed version

### Secondary (MEDIUM confidence)
- [Textual Markdown widget docs](https://textual.textualize.io/widgets/markdown/) — confirmed Markdown widget feature set, MarkdownStream description

### Tertiary (LOW confidence)
- None needed — all critical findings verified directly from source code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified from installed package source
- Architecture: HIGH — verified from source code, runtime tested
- Pitfalls: HIGH — identified from direct source inspection and Pygments runtime test
- Open questions: MEDIUM — behavioral edge case, not blocking

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (Textual stable release cycle — 30 days safe)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRNS-03 | Code blocks in responses render with syntax highlighting | MarkdownFence.highlight() + Pygments already handles this. Requires only test verification + RichMarkdown wiring. |
| TRNS-04 | Markdown in responses renders with proper formatting (headings, bold, links, lists, blockquotes) | Fully handled by base Markdown widget. MarkdownH1-H6, MarkdownBulletList, MarkdownBlockQuote all have DEFAULT_CSS. Zero code changes needed — only tests. |
| TRNS-05 | File diffs render with syntax-highlighted additions/deletions | Pygments diff lexer tokenizes +/- lines but Textual's HighlightTheme lacks Generic.Inserted/Deleted mappings. Fix via DiffHighlightTheme + DiffAwareFence subclass registered in RichMarkdown.BLOCKS. |
</phase_requirements>
