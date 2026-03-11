# Phase 43: Agent Cell Widgets - Research

**Researched:** 2026-03-12
**Domain:** Textual widget development — new cell types in transcript.py
**Confidence:** HIGH

## Summary

Phase 43 creates two new Textual widget classes — `AgentCell` and `OrchestratorStatusCell` — that live alongside `UserCell` and `AssistantCell` in `transcript.py`. These are pure widget implementations with no wiring to the app message bus or state.json; that integration is deferred to Phase 44 and 45. The phase is self-contained: read the existing patterns, write the new classes, write the tests.

The project codebase is the authoritative source. All patterns — CSS inline `DEFAULT_CSS`, shimmer animation via `set_interval`, fade-in via `styles.animate("opacity")`, shimmer guard via `_ANIMATIONS`, and test structure via `async def test_...()` with inline `App.run_test()` — are already demonstrated in `transcript.py` and the existing test files. No new dependencies are needed.

**Primary recommendation:** Copy the `AssistantCell` architecture directly for `AgentCell`. Add a labeled header badge with `agent_name`, `role`, and `task_title`. Reuse the shimmer for WORKING status. Add `update_status()` to transition between WORKING/WAITING/DONE display states. Add `finalize()` that is idempotent regardless of whether streaming was ever started. Use a sanitized CSS ID prefix (`acell-<sanitized_id>`) to prevent collisions.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ACELL-04 | Multiple concurrent AgentCells render independently without interfering with each other | CSS ID sanitization (replace non-alphanum with `-`), distinct prefix `acell-` vs `agent-` (agent_monitor), independent shimmer timers per instance, no shared state |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | >=4.0 | Widget base classes, CSS, animations, timers | Already in use — all existing cells use it |
| textual.widget.Widget | - | Base class for all cells | `UserCell`, `AssistantCell` both subclass `Widget` directly |
| textual.widgets.Static | - | Text display within cells | Used for all label/content rendering in existing cells |
| textual.widgets.LoadingIndicator | - | Thinking/pending state | Used in `AssistantCell` for pre-streaming state |
| textual.color.Color | - | Shimmer tint animation | Used in `_SHIMMER_ON`/`_SHIMMER_OFF` pattern |
| textual.timer.Timer | - | Shimmer set_interval ticker | Used in `AssistantCell._shimmer_timer` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| math | stdlib | Sine wave shimmer calculation | `math.sin(2 * math.pi * phase / period)` for smooth pulse |
| re | stdlib | CSS ID sanitization | `re.sub(r"[^a-zA-Z0-9]", "-", agent_id)` |

**Installation:** No new packages required. All dependencies already installed.

## Architecture Patterns

### Where New Code Lives

Both new widget classes go in `transcript.py` alongside existing cells — they are transcript cell types:

```
packages/conductor-core/src/conductor/tui/widgets/
└── transcript.py   ← ADD AgentCell and OrchestratorStatusCell here
```

Tests go in a new file:
```
packages/conductor-core/tests/
└── test_tui_agent_cells.py   ← NEW
```

### Pattern 1: Widget with Labeled Badge Header (AgentCell)

**What:** A `Widget` subclass that shows a multi-part badge label (agent name + role + task title) followed by a status area that transitions between states.

**When to use:** Any new transcript cell type that has persistent identity and lifecycle states.

**Example — mirroring AssistantCell structure:**
```python
# Source: transcript.py (AssistantCell pattern, adapted)
import re

def _sanitize_id(agent_id: str) -> str:
    """Replace non-alphanumeric chars with hyphens for safe CSS IDs."""
    return re.sub(r"[^a-zA-Z0-9]", "-", agent_id).strip("-") or "agent"

class AgentCell(Widget):
    DEFAULT_CSS = """
    AgentCell {
        background: $surface;
        border-left: solid $warning 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    AgentCell .cell-label {
        color: $warning;
        text-style: bold;
    }
    AgentCell .cell-status {
        color: $text-muted;
    }
    """

    def __init__(
        self,
        agent_id: str,
        agent_name: str,
        role: str,
        task_title: str,
    ) -> None:
        safe_id = _sanitize_id(agent_id)
        super().__init__(id=f"acell-{safe_id}")
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._role = role
        self._task_title = task_title
        self._shimmer_timer: Timer | None = None
        self._shimmer_phase: float = 0.0
        self._status = "working"

    def compose(self) -> ComposeResult:
        yield Static(
            f"{self._agent_name} [{self._role}] — {self._task_title}",
            classes="cell-label",
        )
        yield Static("working...", classes="cell-status", id="status-line")

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")
        self._shimmer_forward()

    def update_status(self, new_status: str) -> None:
        """Transition display: working shimmer → waiting → done."""
        self._status = new_status
        try:
            self.query_one("#status-line", Static).update(new_status)
        except Exception:
            pass
        if new_status != "working":
            self._stop_shimmer()

    def finalize(self) -> None:
        """Mark cell as complete — idempotent, safe to call multiple times."""
        self._stop_shimmer()
        self._status = "done"
        try:
            self.query_one("#status-line", Static).update("done")
        except Exception:
            pass

    def _stop_shimmer(self) -> None:
        if self._shimmer_timer is not None:
            self._shimmer_timer.stop()
            self._shimmer_timer = None
        self.styles.tint = _SHIMMER_OFF

    def _shimmer_forward(self) -> None:
        if self._status != "working":
            return
        self._shimmer_phase = 0.0
        self._shimmer_timer = self.set_interval(_SHIMMER_INTERVAL, self._shimmer_tick)

    def _shimmer_tick(self) -> None:
        if self._status != "working":
            self._stop_shimmer()
            return
        self._shimmer_phase += _SHIMMER_INTERVAL
        t = (math.sin(2 * math.pi * self._shimmer_phase / _SHIMMER_PERIOD) + 1) / 2
        alpha = _SHIMMER_ON.a * t
        self.styles.tint = Color(_SHIMMER_ON.r, _SHIMMER_ON.g, _SHIMMER_ON.b, alpha)
```

### Pattern 2: OrchestratorStatusCell (Ephemeral)

**What:** A simpler Widget that displays an orchestrator phase label (e.g., "Orchestrator — delegating") and a description. Supports `update()` and `finalize()` for ephemeral lifecycle.

**When to use:** When the SDK stream signals orchestrator delegation phase (Phase 45 wires this).

```python
# Source: transcript.py (UserCell/AssistantCell pattern, simplified)
class OrchestratorStatusCell(Widget):
    DEFAULT_CSS = """
    OrchestratorStatusCell {
        background: $surface;
        border-left: solid $secondary 40%;
        padding: 0 1;
        margin: 0 0 1 0;
    }
    OrchestratorStatusCell .cell-label {
        color: $secondary;
        text-style: bold;
    }
    OrchestratorStatusCell .cell-body {
        color: $text-muted;
    }
    """

    def __init__(self, label: str, description: str = "") -> None:
        super().__init__()
        self._label = label
        self._description = description
        self._finalized = False

    def compose(self) -> ComposeResult:
        yield Static(self._label, classes="cell-label", id="orch-label")
        yield Static(self._description, classes="cell-body", id="orch-body")

    def on_mount(self) -> None:
        if _ANIMATIONS:
            self.styles.opacity = 0.0
            self.styles.animate("opacity", value=1.0, duration=0.25, easing="out_cubic")

    def update(self, label: str | None = None, description: str | None = None) -> None:
        if self._finalized:
            return
        if label is not None:
            try:
                self.query_one("#orch-label", Static).update(label)
            except Exception:
                pass
        if description is not None:
            try:
                self.query_one("#orch-body", Static).update(description)
            except Exception:
                pass

    def finalize(self) -> None:
        """Mark as complete. Idempotent."""
        self._finalized = True
```

### Pattern 3: CSS ID Sanitization

**What:** Convert arbitrary `agent_id` strings to valid CSS identifiers with a collision-safe prefix.

**Why critical:** `agent_monitor.py` uses `f"agent-{agent_id}"` without sanitization. If `agent_id` contains slashes, colons, or dots (common in UUIDs or generated IDs), the CSS selector `self.query_one(f"#agent-{agent_id}", ...)` raises `InvalidQuery`. Phase 43 must not repeat this mistake.

```python
# Prefix is "acell-" (distinct from agent_monitor's "agent-" prefix)
def _sanitize_id(agent_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "-", agent_id).strip("-") or "agent"

widget_id = f"acell-{_sanitize_id(agent_id)}"
```

**Verification:** The test for ACELL-04 must create two AgentCells with IDs containing dots/slashes to prove sanitization works.

### Anti-Patterns to Avoid

- **Unsanitized widget IDs:** `id=f"agent-{agent_id}"` without `re.sub` — breaks CSS queries when agent_id has special chars. Use `_sanitize_id()` + prefix.
- **Shared timer state:** Timer handles must be per-instance (`self._shimmer_timer`), never class-level. Each AgentCell has its own timer.
- **Blocking finalize:** `finalize()` must not await anything. AssistantCell has `await self._stream.stop()`, but AgentCell has no stream — all cleanup is synchronous.
- **Finalize before mount:** `query_one("#status-line")` raises `NoMatches` before `compose()` runs. Guard with try/except, not existence checks.
- **Missing `_ANIMATIONS` guard in `on_mount`:** Always check `if _ANIMATIONS:` before calling `self.styles.animate()`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Shimmer animation timing | Custom asyncio sleep loop | `self.set_interval(_SHIMMER_INTERVAL, callback)` | Already in AssistantCell — set_interval is non-blocking and cancellable |
| Fade-in on mount | CSS transitions or manual timer | `self.styles.animate("opacity", ...)` | Textual built-in, works with `_ANIMATIONS` guard |
| CSS ID collision | Namespacing by class | Sanitize + distinct prefix (`acell-` vs `agent-`) | Simple, verified pattern |
| Status text update | Widget removal/remounting | `Static.update(new_text)` | Cheaper, already used in AgentPanel.update_status() |

## Common Pitfalls

### Pitfall 1: Shimmer timer not stopped on finalize
**What goes wrong:** `_shimmer_timer.stop()` not called in `finalize()` — timer fires after cell is logically done, calling `self.styles.tint` on a finalized widget. In a long session with N agents completing, N orphaned timers fire forever.
**Why it happens:** `finalize()` is added as an afterthought without auditing all active timers.
**How to avoid:** `_stop_shimmer()` helper — call it from both `update_status()` (when status != working) and `finalize()`. This is idempotent.
**Warning signs:** Test with 3+ AgentCells — after all finalize(), check that no shimmer tints remain non-zero.

### Pitfall 2: `query_one()` raises before compose
**What goes wrong:** Calling `self.query_one("#status-line")` in `__init__` or before `on_mount` raises `NoMatches`. Also happens if `finalize()` is called very early.
**Why it happens:** Textual `compose()` has not yet run — child widgets don't exist yet.
**How to avoid:** Wrap all `query_one()` calls in try/except. This pattern is already used in `AssistantCell.start_streaming()` and `AgentPanel.update_status()`.

### Pitfall 3: CSS ID collision between AgentMonitorPane and TranscriptPane
**What goes wrong:** `AgentMonitorPane` uses `id=f"agent-{agent_id}"` for its panels. If `AgentCell` uses the same scheme (`id=f"agent-{agent_id}"`), Textual's ID uniqueness constraint raises `DuplicateIds` when both panes exist in the same app.
**Why it happens:** Two widget trees try to register the same DOM ID.
**How to avoid:** AgentCell uses prefix `acell-` (not `agent-`). Verified: `AgentMonitorPane` uses `#agent-{id}`, so `#acell-{id}` is distinct.

### Pitfall 4: `update_status()` called after finalize
**What goes wrong:** Phase 44 may call `update_status()` after `finalize()` due to delayed state.json events. If `update_status()` reactivates the shimmer (e.g., status="working"), it creates a zombie timer.
**How to avoid:** `update_status()` should check `self._finalized` (or `self._status == "done"`) and return early if finalized. OrchestratorStatusCell already has this pattern (`if self._finalized: return`).

### Pitfall 5: `asyncio_mode = "auto"` + `run_test()` in fixture
**What goes wrong:** pytest-asyncio + Textual contextvars incompatibility (GitHub #4998). Tests hang or fail with context errors if `run_test()` is inside a pytest fixture.
**Why it happens:** Textual's `run_test()` creates its own event loop context — nesting inside pytest-asyncio fixtures breaks contextvar propagation.
**How to avoid:** Keep `run_test()` inline inside each `async def test_...()` function — never in `@pytest.fixture`. All existing test files follow this pattern.

## Code Examples

### CSS Reuse Pattern (no tcss file needed)

```python
# Source: transcript.py (AssistantCell.DEFAULT_CSS)
# All cell DEFAULT_CSS uses Textual design tokens, not hardcoded colors:
#   $accent     — blue accent (AssistantCell)
#   $primary    — blue primary (UserCell)
#   $warning    — amber/yellow (AgentCell — visually distinct)
#   $secondary  — green/teal (OrchestratorStatusCell — visually distinct)
#   $surface    — base background
#   $text-muted — dim text
# Phase 46 will add visual accent colors — Phase 43 uses standard tokens.
```

### Test structure pattern (from test_tui_agent_monitor.py)

```python
# Source: tests/test_tui_agent_monitor.py
async def test_agent_cell_appears():
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a1",
                agent_name="Alice",
                role="coder",
                task_title="Add auth module",
            )

    app = TestApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AgentCell)
        # assertions...
```

### Defensive finalize (idempotent pattern)

```python
# Source: transcript.py (AssistantCell.finalize) + AgentPanel.update_status
def finalize(self) -> None:
    self._stop_shimmer()  # idempotent — safe if timer is None
    self._status = "done"
    try:
        self.query_one("#status-line", Static).update("done")
    except Exception:
        pass  # widget may not be mounted yet — safe to swallow

def _stop_shimmer(self) -> None:
    if self._shimmer_timer is not None:
        self._shimmer_timer.stop()
        self._shimmer_timer = None
    self.styles.tint = _SHIMMER_OFF  # always safe
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 35 AgentPanel used Collapsible | Phase 43 AgentCell uses Widget directly | Phase 43 design | Transcript cells are not collapsible — simpler, no Collapsible overhead |
| agent_monitor uses `f"agent-{agent_id}"` unsanitized | Phase 43 uses `_sanitize_id()` + `acell-` prefix | Phase 43 design | Prevents DOM ID collisions and InvalidQuery crashes |

**Deprecated/outdated:**
- `Markdown.get_stream()` pattern from AssistantCell: Not needed for AgentCell — agents don't stream tokens into cells. Phase 43 cells only display static status text.

## Open Questions

1. **OrchestratorStatusCell label vs AssistantCell label change**
   - What we know: Phase 45 will change the active AssistantCell's label from "Assistant" to "Orchestrator — delegating"
   - What's unclear: Whether Phase 43 should expose a `set_label()` method on AssistantCell, or whether Phase 45 directly updates the Static widget
   - Recommendation: Phase 43 should NOT modify AssistantCell — leave that to Phase 45. OrchestratorStatusCell is a separate widget class, not a modified AssistantCell.

2. **agent_id uniqueness assumption**
   - What we know: `AgentRecord.id` is set by orchestrator code; format is not constrained in models.py
   - What's unclear: Whether UUIDs, slugs, or dotted names are used in practice
   - Recommendation: Sanitize defensively regardless — `re.sub(r"[^a-zA-Z0-9]", "-", agent_id)` handles all formats. Tests should exercise an ID with dots and slashes.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio >=0.23 |
| Config file | `packages/conductor-core/pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `cd packages/conductor-core && python -m pytest tests/test_tui_agent_cells.py -x` |
| Full suite command | `cd packages/conductor-core && python -m pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACELL-04 (SC1) | AgentCell mounts with name/role/task in labeled header | unit | `pytest tests/test_tui_agent_cells.py::test_agent_cell_header_content -x` | ❌ Wave 0 |
| ACELL-04 (SC2) | AgentCell.update_status() transitions working→waiting→done | unit | `pytest tests/test_tui_agent_cells.py::test_agent_cell_update_status -x` | ❌ Wave 0 |
| ACELL-04 (SC3) | AgentCell.finalize() is idempotent (with and without streaming started) | unit | `pytest tests/test_tui_agent_cells.py::test_agent_cell_finalize_defensive -x` | ❌ Wave 0 |
| ACELL-04 (SC4) | OrchestratorStatusCell can be created, updated, finalized | unit | `pytest tests/test_tui_agent_cells.py::test_orchestrator_status_cell_lifecycle -x` | ❌ Wave 0 |
| ACELL-04 (SC5) | Multiple AgentCells with special-char agent_ids render without CSS ID collision | unit | `pytest tests/test_tui_agent_cells.py::test_multiple_agent_cells_no_id_collision -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && python -m pytest tests/test_tui_agent_cells.py -x`
- **Per wave merge:** `cd packages/conductor-core && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui_agent_cells.py` — covers all 5 success criteria (SC1–SC5)
- [ ] No framework changes needed — existing pytest config covers the new file

## Sources

### Primary (HIGH confidence)
- `transcript.py` (read directly) — AssistantCell, UserCell, shimmer pattern, _ANIMATIONS guard, fade-in animation
- `agent_monitor.py` (read directly) — AgentPanel patterns, CSS ID usage, update_status(), query_one() try/except
- `messages.py` (read directly) — existing message types, AgentStateUpdated shape
- `state/models.py` (read directly) — AgentRecord fields (id, name, role, status), AgentStatus enum values
- `tests/test_tui_streaming.py` (read directly) — test structure, run_test() inline pattern
- `tests/test_tui_animations.py` (read directly) — shimmer/animation test patterns
- `tests/test_tui_agent_monitor.py` (read directly) — multi-agent test patterns, _make_state helper
- `pyproject.toml` (read directly) — textual>=4.0, pytest asyncio_mode=auto, no new deps needed

### Secondary (MEDIUM confidence)
- GitHub textual issue #4998 (referenced in test file comments) — contextvars/pytest-asyncio incompatibility, run_test() must be inline

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use, read directly from code
- Architecture: HIGH — patterns copied from existing cells in same file
- Pitfalls: HIGH — ID collision risk confirmed by reading agent_monitor.py, timer cleanup confirmed from AssistantCell pattern

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable — Textual 4.x API, project-internal patterns)
