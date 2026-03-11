# Phase 40: Borderless Design - Research

**Researched:** 2026-03-11
**Domain:** Textual CSS specificity, border removal, widget DEFAULT_CSS auditing
**Confidence:** HIGH

---

## Summary

Phase 40 is a CSS-only change. No Python logic modifications are required. The goal is to strip visible box borders from all structural layout containers (Screen, #app-body, CommandInput) and replace the thick border on cell widgets (UserCell, AssistantCell) with a subtle left accent line. AgentMonitorPane's `border-left` stays as a functional column divider; modal overlays stay unchanged.

The primary challenge is CSS specificity. Each widget's `DEFAULT_CSS` must be read before writing overrides in `conductor.tcss`. A type-level rule `CommandInput { border: none; }` wins over `DEFAULT_CSS` because `conductor.tcss` (App CSS_PATH) has higher specificity than any widget's built-in CSS. However, when two rules are at the same level, the more-specific compound selector wins. The safe approach is to mirror the specificity of the DEFAULT_CSS declaration being overridden.

The second concern is `border: none` vs `border: hidden`. `none` collapses border space to zero. `hidden` renders a transparent border that still occupies space, leaving a gap where the border was. Use `none` everywhere borders are being removed; use `hidden` only if deliberate space-preservation is wanted (not needed here).

**Primary recommendation:** Audit each widget's exact `DEFAULT_CSS` border declaration, mirror its specificity in `conductor.tcss`, use `border: none` to collapse and `border-left: thick $primary` (or similar) to add the subtle accent line.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VIS-01 | Screen, #app-body, and CommandInput area have no visible box borders | `conductor.tcss`: `Screen { border: none; }`, `#app-body` has no border today (confirmed), `CommandInput DEFAULT_CSS` has `border-top: solid $primary 30%` — override with `CommandInput { border: none; }` in tcss or remove from DEFAULT_CSS |
| VIS-02 | UserCell and AssistantCell have a subtle left accent line instead of thick box border | Both widgets currently use `border-left: thick $primary` / `border-left: thick $accent` — replace with `border-left: solid $primary 40%` / `border-left: solid $accent 40%` (or `vkey`/`tall` style) |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `textual` | `8.1.1` | CSS engine, widget DEFAULT_CSS cascade | Only TUI framework in use |

### No new dependencies

All changes are in existing `conductor.tcss` and widget `DEFAULT_CSS` strings. No packages to add.

---

## Architecture Patterns

### CSS Cascade Order (Textual)

Textual applies CSS in this order, lowest to highest specificity:

```
Widget DEFAULT_CSS           (lowest)
App CSS_PATH (conductor.tcss)
App CSS class variable
Inline styles (self.styles.*)  (highest)
```

A rule in `conductor.tcss` always beats the same selector in a widget's `DEFAULT_CSS`. This means:

- To override `CommandInput { border-top: ... }` in `CommandInput.DEFAULT_CSS`, write `CommandInput { border: none; }` in `conductor.tcss`. This wins.
- To override `CommandInput Input { border: none; }` in `CommandInput.DEFAULT_CSS`, write `CommandInput Input { border: none; }` in `conductor.tcss` (same specificity — `conductor.tcss` wins because it is evaluated later in the cascade).

### Recommended Project Structure

All changes land in two files only:

```
conductor/tui/
├── conductor.tcss          # MODIFIED — borderless Screen, remove CommandInput border-top
└── widgets/
    └── transcript.py       # MODIFIED — DEFAULT_CSS: replace thick border-left with subtle line
```

`CommandInput.DEFAULT_CSS` border-top can be removed directly from `command_input.py` (simpler) OR overridden via `conductor.tcss` (consistent with CSS-only approach). Direct removal is cleaner; either is correct.

### Pattern 1: Remove Border from Structural Containers

**What:** Set `border: none` on the container in `conductor.tcss`.

**When to use:** For layout-level widgets where the border is decorative chrome, not a semantic marker.

**Containers to change:**

```css
/* conductor.tcss */

Screen {
    layers: base overlay;
    /* REMOVE: background: $surface; */
    /* background removal optional — see VIS-01 note on alt-screen feel */
}

/* #app-body has no border in current conductor.tcss — already borderless.
   No change needed here. */

CommandInput {
    height: 3;
    padding: 0 1;
    background: $panel;
    border: none;   /* overrides border-top: solid $primary 30% in DEFAULT_CSS */
}
```

**Key fact about #app-body:** Inspecting the current `conductor.tcss`, `#app-body` has no `border` property at all. Textual containers (`Horizontal`) have no default border in their `DEFAULT_CSS`. This requirement is already satisfied — no tcss change needed for `#app-body`.

**Key fact about Screen:** The current `conductor.tcss` has `background: $surface` on `Screen`. Removing or keeping this is a visual choice — it does not affect borders. The requirement is "no visible box borders" not "transparent background." `Screen` has no `border` in its DEFAULT_CSS. No border change needed for Screen.

**Key fact about CommandInput:** `DEFAULT_CSS` in `command_input.py` line 65: `border-top: solid $primary 30%;`. This is the only visible structural border to remove. Either:
- Remove the line from `DEFAULT_CSS` in `command_input.py`, or
- Add `CommandInput { border: none; }` to `conductor.tcss`

Direct removal from `DEFAULT_CSS` is preferred (less specificity reasoning required).

### Pattern 2: Replace Thick Border-Left with Subtle Accent Line

**What:** Change the cell widget `border-left` from `thick` style to `solid` with a reduced opacity color.

**Current state in `transcript.py`:**

```python
# UserCell DEFAULT_CSS (line 22-31):
UserCell {
    background: $primary 10%;
    border-left: thick $primary;    # <-- thick, full-opacity
    padding: 0 1;
    margin: 0 0 1 0;
}

# AssistantCell DEFAULT_CSS (line 52-62):
AssistantCell {
    background: $surface;
    border-left: thick $accent;     # <-- thick, full-opacity
    padding: 0 1;
    margin: 0 0 1 0;
}
```

**Target state (VIS-02):** Replace `thick` with `solid` (thinner) and reduce color opacity:

```python
# UserCell DEFAULT_CSS:
UserCell {
    background: $primary 10%;
    border-left: solid $primary 40%;   # subtle: thinner style + 40% opacity
    padding: 0 1;
    margin: 0 0 1 0;
}

# AssistantCell DEFAULT_CSS:
AssistantCell {
    background: $surface;
    border-left: solid $accent 40%;    # subtle: thinner style + 40% opacity
    padding: 0 1;
    margin: 0 0 1 0;
}
```

**Textual border styles:** Valid values (verified from `VALID_BORDER`): `none`, `hidden`, `blank`, `round`, `solid`, `double`, `dashed`, `heavy`, `inner`, `outer`, `hkey`, `vkey`, `tall`, `wide`, `panel`, `ascii`, `thick`. The `thick` value is a Textual-specific style that renders thicker than `solid`. Replacing `thick` with `solid` makes the accent line visually thinner.

**Alternative:** Change in `conductor.tcss` instead of `DEFAULT_CSS` — requires compound selectors:
```css
/* conductor.tcss alternative — matches DEFAULT_CSS specificity */
UserCell {
    border-left: solid $primary 40%;
}
AssistantCell {
    border-left: solid $accent 40%;
}
```
Both approaches work. Editing `DEFAULT_CSS` directly in `transcript.py` keeps the canonical style co-located with the widget.

### Pattern 3: AgentMonitorPane — Retain border-left (No Change)

**Current `AgentMonitorPane.DEFAULT_CSS` (line 69-76):**

```css
AgentMonitorPane {
    width: 30;
    height: 1fr;
    background: $panel;
    border-left: solid $primary 20%;   # <-- functional column separator
    padding: 1 1;
}
```

This `border-left` is already subtle (`solid` style, `20%` opacity). It serves as the visual column divider between TranscriptPane and AgentMonitorPane. Per VIS-03, this is intentionally retained. No change needed.

### Pattern 4: Modals — Retain Borders (No Change)

All three modal widgets in `modals.py` use `border: solid $primary` on their `#dialog` container:

```css
/* FileApprovalModal, CommandApprovalModal, EscalationModal — all identical pattern */
#dialog {
    border: solid $primary;
    background: $surface;
    ...
}
```

These borders are intentional overlay chrome. Per success criterion 4, no change is made to modals.

### Anti-Patterns to Avoid

- **Using `border: hidden` instead of `border: none`:** `hidden` renders a zero-color border that still occupies layout space (leaves a gap). Use `none` to collapse the space entirely.
- **Writing a type selector in tcss when the DEFAULT_CSS uses a compound selector:** If the DEFAULT_CSS rule is `CommandInput Input { border: none; }` and the tcss rule is just `Input { border: none; }`, the compound selector wins within the same specificity tier. Mirror the DEFAULT_CSS selector shape.
- **Removing `border-left` from cell widgets entirely:** The cell `border-left` communicates message role (user vs assistant). Removing it entirely makes the transcript visually ambiguous. Change the style (`thick` to `solid`) and opacity, not the presence.
- **Modifying StatusFooter borders:** `StatusFooter.DEFAULT_CSS` has no `border` property at all — only `dock: bottom`, `height: 1`, `background: $primary`. No change needed; any accidental addition would be wrong.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Thinner left accent line | Custom widget with `compose()` that draws a `Static` as a left bar | `border-left: solid $accent 40%` in CSS | Textual's border system handles this natively with zero widget code |
| Borderless container | Wrapper widget with zero-width edge | `border: none` in CSS | CSS `none` collapses space; no wrapper needed |
| Color opacity on border | Hard-code a hex color at 40% opacity | Textual CSS color variable `$accent 40%` | `$accent 40%` auto-adapts to theme; hex values break theme switching |

---

## Common Pitfalls

### Pitfall 1: `border: none` on CommandInput Does Not Remove All Sides

**What goes wrong:** `CommandInput { border: none; }` in `conductor.tcss` overrides the `DEFAULT_CSS` rule `CommandInput { border-top: solid $primary 30%; }`. But if `Input.DEFAULT_CSS` (Textual's built-in `Input` widget) also has border declarations, those may remain visible as lines around the inner input field.

**Why it happens:** The inner `Input` widget has its own `DEFAULT_CSS` with `border: tall $accent`. The `CommandInput.DEFAULT_CSS` already overrides this with `CommandInput Input { border: none; }` (line 68). This rule is already correct and will not be affected by removing the `border-top` from CommandInput itself.

**How to avoid:** Verify the full border removal with `textual console` CSS inspector. The two rules are independent: outer `CommandInput` border (removed) and inner `Input` border (already `none` in DEFAULT_CSS).

**Warning signs:** A single-pixel line appears at the top or bottom of the input area after removing the `border-top`.

### Pitfall 2: `thick` is Not `bold` — It Renders as a Two-Cell-Wide Border

**What goes wrong:** Replacing `border-left: thick $primary` with `border-left: solid $primary 40%` changes the visual width. `thick` in Textual renders as a two-cell-wide border (uses block characters). `solid` renders as a one-cell-wide border (single line character). The padding computation does not change — `padding: 0 1` is unaffected — but the visual indentation of cell content will shift by 1 cell when switching from `thick` to `solid`.

**Why it happens:** Textual's `thick` border style uses different Unicode box-drawing characters than `solid`. The layout engine always reserves 1 cell for any non-`none` border, regardless of visual thickness. The content position is the same.

**How to avoid:** Visually inspect after change. The 1-cell content position is preserved. The visual line will appear thinner, which is the desired outcome.

### Pitfall 3: CSS Specificity Fight When Using tcss Override for Cell Borders

**What goes wrong:** Adding `UserCell { border-left: solid $primary 40%; }` to `conductor.tcss` to override the DEFAULT_CSS should work (tcss beats DEFAULT_CSS). But if there are later inline style assignments (`self.styles.border_left = ...`) elsewhere in the Python code, the inline style wins over tcss.

**Why it happens:** Inline styles have the highest specificity in Textual's cascade.

**How to avoid:** Grep for `styles.border` in the transcript.py file before finalizing the approach. Current code has no such inline assignments — the border is purely static CSS. Editing DEFAULT_CSS directly in `transcript.py` is the cleanest approach and avoids this concern entirely.

**Warning signs:** Border style reverts to `thick` after page refresh or cell mount.

### Pitfall 4: Screen Background Confusion with Border Removal

**What goes wrong:** `conductor.tcss` has `background: $surface` on `Screen`. This sets the entire terminal background to the theme's `$surface` color. Removing it is desirable for an alt-screen "native terminal" feel, but it is orthogonal to border removal. Conflating the two causes scope creep.

**Why it happens:** The phase description mentions "no visible box borders on structural containers" and "content flows naturally with minimal chrome." Removing the Screen background feels related but is a separate concern.

**How to avoid:** Phase 40 addresses borders only. Removing `background: $surface` from Screen is an independent decision. If desired, it can be done, but it is not required by VIS-01 or VIS-02. Research scope excludes it.

---

## Code Examples

### Complete tcss delta for VIS-01

```css
/* conductor.tcss — Phase 40 additions */

/* VIS-01: Remove CommandInput separator border.
   DEFAULT_CSS has: CommandInput { border-top: solid $primary 30%; }
   conductor.tcss wins over DEFAULT_CSS. */
CommandInput {
    border: none;
}

/* Screen already has no border — no change needed.
   #app-body (Horizontal) has no border — no change needed. */
```

### Complete DEFAULT_CSS delta for VIS-02

In `transcript.py`, change the two `border-left` declarations:

```python
# UserCell — before:
border-left: thick $primary;
# UserCell — after:
border-left: solid $primary 40%;

# AssistantCell — before:
border-left: thick $accent;
# AssistantCell — after:
border-left: solid $accent 40%;
```

### Full widget audit summary

| Widget | File | Current border | Phase 40 action |
|--------|------|---------------|-----------------|
| `Screen` | conductor.tcss | none | No change (no border exists) |
| `Horizontal #app-body` | conductor.tcss | none | No change (no border exists) |
| `CommandInput` | command_input.py | `border-top: solid $primary 30%` | Remove this line from DEFAULT_CSS |
| `CommandInput Input` | command_input.py | `border: none` | No change (already none) |
| `UserCell` | transcript.py | `border-left: thick $primary` | Change to `border-left: solid $primary 40%` |
| `AssistantCell` | transcript.py | `border-left: thick $accent` | Change to `border-left: solid $accent 40%` |
| `TranscriptPane` | transcript.py | none | No change |
| `AgentMonitorPane` | agent_monitor.py | `border-left: solid $primary 20%` | No change (functional divider, per VIS-03) |
| `StatusFooter` | status_footer.py | none | No change |
| `FileApprovalModal #dialog` | modals.py | `border: solid $primary` | No change (modal overlay, per success criterion 4) |
| `CommandApprovalModal #dialog` | modals.py | `border: solid $primary` | No change |
| `EscalationModal #dialog` | modals.py | `border: solid $primary` | No change |

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|------------------|-------|
| `thick` border-left on cells | `solid` border-left at reduced opacity | `thick` was v0 default; `solid` + opacity is the minimal-chrome convention |
| `border: hidden` for invisible borders | `border: none` | `hidden` preserves space; `none` collapses it |

---

## Open Questions

1. **Opacity value for cell accent lines**
   - What we know: `solid $primary 40%` and `solid $accent 40%` are syntactically valid Textual CSS.
   - What's unclear: The exact visual weight depends on the active terminal theme. `40%` is a reasonable starting point; `30%` or `50%` may look better in practice.
   - Recommendation: Use `40%` as default; adjust visually after first render. No code logic depends on this value.

2. **Whether to remove `background: $surface` from Screen**
   - What we know: This background is unrelated to borders. Removing it would make the Screen transparent to the terminal background.
   - What's unclear: Whether this is in scope for Phase 40 or a separate concern.
   - Recommendation: Out of scope for Phase 40. VIS-01 and VIS-02 do not require it.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio 0.23 |
| Config file | `packages/conductor-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_tui_borderless.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VIS-01 | CommandInput has no border (no `border-top`) | unit (Pilot CSS inspection) | `uv run pytest tests/test_tui_borderless.py::test_command_input_has_no_border -x` | Wave 0 |
| VIS-01 | Screen and #app-body have no border | unit (Pilot CSS inspection) | `uv run pytest tests/test_tui_borderless.py::test_screen_and_app_body_no_border -x` | Wave 0 |
| VIS-02 | UserCell has `border-left: solid` (not `thick`) | unit (DEFAULT_CSS string inspection) | `uv run pytest tests/test_tui_borderless.py::test_user_cell_subtle_border -x` | Wave 0 |
| VIS-02 | AssistantCell has `border-left: solid` (not `thick`) | unit (DEFAULT_CSS string inspection) | `uv run pytest tests/test_tui_borderless.py::test_assistant_cell_subtle_border -x` | Wave 0 |
| VIS-03 (implicit) | AgentMonitorPane retains border-left | unit (DEFAULT_CSS string inspection) | `uv run pytest tests/test_tui_borderless.py::test_agent_monitor_retains_border_left -x` | Wave 0 |
| VIS-04 (implicit) | Modal #dialog retains border | unit (DEFAULT_CSS string inspection) | `uv run pytest tests/test_tui_borderless.py::test_modal_dialogs_retain_border -x` | Wave 0 |

### Test Approach

Textual provides `app.run_test()` + `pilot` for unit tests. Inspecting CSS properties on live widgets uses `widget.styles.border_top`, `widget.styles.border_left`, etc. Inspecting DEFAULT_CSS strings directly (without mounting) is simpler for static CSS checks:

```python
# Pattern: inspect DEFAULT_CSS string directly — no app mount needed
def test_user_cell_subtle_border():
    from conductor.tui.widgets.transcript import UserCell
    css = UserCell.DEFAULT_CSS
    assert "thick" not in css, "UserCell should not use 'thick' border-left"
    assert "border-left" in css, "UserCell should still have a border-left accent line"

# Pattern: mount and inspect computed styles via Pilot
async def test_command_input_has_no_border():
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.command_input import CommandInput

    class TestApp(App):
        CSS_PATH = Path(...) / "conductor.tcss"
        def compose(self) -> ComposeResult:
            yield CommandInput()

    app = TestApp()
    async with app.run_test() as pilot:
        widget = app.query_one(CommandInput)
        # border_top returns (style, color) tuple; style "none" or ("", Color(0,0,0,0))
        top = widget.styles.border_top
        assert top[0] in ("none", ""), f"CommandInput border-top should be none, got {top}"
```

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_tui_borderless.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_tui_borderless.py` — all VIS-01 and VIS-02 tests (new file, does not yet exist)

None of the existing test files cover border styling. The test infrastructure (pytest, pytest-asyncio, `app.run_test()`) is already installed and configured.

---

## Sources

### Primary (HIGH confidence)

- Direct code inspection of `conductor.tcss`, `app.py`, `transcript.py`, `command_input.py`, `status_footer.py`, `agent_monitor.py`, `modals.py` — border declarations audited line by line
- `.planning/research/STACK.md` — `VALID_BORDER` constants, `border: none` vs `border: hidden` semantics, CSS specificity cascade order
- `.planning/research/PITFALLS.md` — Pitfall 5: compound selector specificity fights with DEFAULT_CSS

### Secondary (MEDIUM confidence)

- `.planning/research/ARCHITECTURE.md` — CSS cascade section, borderless design pattern, modal vs layout border distinction

### Tertiary (LOW confidence)

- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; Textual 8.1.1 CSS is the only engine
- Architecture: HIGH — all widget DEFAULT_CSS declarations audited directly from source files; cascade rules verified from project research docs
- Pitfalls: HIGH — specificity pitfall documented with exact line references in existing DEFAULT_CSS strings

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (CSS-only; stable until Textual major version change)
