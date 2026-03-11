# Phase 46: Visual Polish and Verification — Research

**Researched:** 2026-03-12
**Domain:** Textual TUI — CSS theming, inline delegation event cells, shimmer timer cleanup, completion summary display
**Confidence:** HIGH

## Summary

Phase 46 is a polish and verification pass that closes four success criteria across the v2.2 milestone. No new requirements are introduced; all work is incremental changes to existing widgets in `transcript.py` and their test files.

The four success criteria map cleanly to four independent implementation areas: (1) CSS accent color changes on `AgentCell` and `OrchestratorStatusCell` — currently using `$warning` and `$secondary` which overlap with `AssistantCell`'s `$accent`; Phase 46 assigns dedicated distinct tokens or custom tints; (2) an inline delegation event cell appears in the transcript immediately before sub-agent cells to orient the user at the transition point between stream and state-driven phases — this was already scaffolded by `OrchestratorStatusCell` in Phase 45 and needs a visual tweak; (3) agent completion cells must include a final task summary extracted from the `Task.outputs` dict or a fallback when no structured output exists; and (4) shimmer timer cleanup must be verified to be leak-free under 3+ concurrent agents.

The codebase is small and well-structured. All changes happen in `transcript.py` (widget CSS and `finalize()` method on `AgentCell`) with no changes required to `app.py` or `messages.py`. The only validation work is verifying the shimmer timer leak at finalize time, which the existing `_stop_shimmer()` helper already handles correctly — the test just needs to exercise it with 3+ concurrent cells.

**Primary recommendation:** Make `AgentCell` use `$success` (green) and `OrchestratorStatusCell` use `$warning` (amber) for borders and label color — swapping them from their current assignments to maximize contrast. Extend `AgentCell.finalize()` to accept an optional `summary: str` parameter. Update `TranscriptPane.on_agent_state_updated` to pass `task.outputs.get("summary", "")` when DONE. Write one new test file covering all four criteria.

## Standard Stack

### Core (already installed — no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `textual` | >=4.0 | Widget CSS (`DEFAULT_CSS`), design tokens, `set_interval`, timer lifecycle | All TUI cells built on it — `$success`, `$warning`, `$accent`, `$secondary` are standard Textual tokens |
| `textual.color.Color` | installed | `_SHIMMER_OFF` reset after finalize | Already used in shimmer implementation |
| `textual.timer.Timer` | installed | Shimmer tick scheduling | `_shimmer_timer: Timer | None` per cell |

### No New Installations Required

## Architecture Patterns

### Files Touched

```
packages/conductor-core/src/conductor/tui/widgets/
└── transcript.py   — CSS token changes on AgentCell and OrchestratorStatusCell;
                      finalize(summary=) param extension; on_agent_state_updated
                      passes summary to finalize()

packages/conductor-core/tests/
└── test_tui_visual_polish.py   — NEW: covers all 4 success criteria
```

No changes to `app.py`, `messages.py`, `conductor.tcss`, or any other file.

### Pattern 1: Textual Design Tokens for Distinct Cell Colors

**What:** Each transcript cell type uses a Textual CSS design token (`$accent`, `$primary`, `$warning`, `$secondary`, `$success`, `$error`) for its border and label color in `DEFAULT_CSS`. Tokens map to Textual's built-in theme colors.

**Current state (after Phases 43-45):**

| Cell Type | Border Token | Label Token |
|-----------|-------------|-------------|
| `UserCell` | `$primary` | `$primary` |
| `AssistantCell` | `$accent` | `$accent` |
| `AgentCell` | `$warning` | `$warning` |
| `OrchestratorStatusCell` | `$secondary` | `$secondary` |

**Problem:** `$warning` (amber/yellow) and `$secondary` (green/teal) do differentiate from `$accent` (blue) visually, but `$warning` on `AgentCell` and `$secondary` on `OrchestratorStatusCell` may feel inverted in semantic meaning — orchestrator is a high-level phase marker, agent is a worker. Visual polish means confirming or swapping these assignments so the color semantics make sense.

**Approach:** Success Criterion 1 says "visually distinct CSS accent colors that differentiate them from AssistantCell". The current implementation already achieves this (different tokens). Phase 46's task is to verify the token choices read correctly and document them. If the tokens need updating, change the `DEFAULT_CSS` string in each class — no other file is affected.

**Example — AgentCell CSS pattern:**
```python
# Source: transcript.py AgentCell.DEFAULT_CSS (current)
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
```

**To change to `$success` (if preferred), only the token string changes:**
```python
border-left: solid $success 40%;
# and
color: $success;
```

**Note:** Textual's standard tokens are: `$accent` (blue), `$primary` (blue variant), `$secondary` (purple/teal depending on theme), `$success` (green), `$warning` (amber), `$error` (red). The exact rendered hue depends on the active Textual theme (dark/light). Tests that assert on color values will fail across theme switches — assert on structural content, not color values.

### Pattern 2: Inline Delegation Event Cell — OrchestratorStatusCell Already Exists

**What:** Success Criterion 2 requires a "brief inline delegation event cell in the transcript before sub-agent cells." This cell is `OrchestratorStatusCell` which Phase 45 already wires. The SC asks for verification that it appears correctly and orients the user.

**What Phase 46 actually needs to do:**
- Verify the existing `OrchestratorStatusCell` mount order in `TranscriptPane` is correct (delegation cell appears before `AgentCell`s)
- The `OrchestratorStatusCell` already shows "Orchestrator — delegating" + task description
- No structural changes needed unless the content format needs tweaking

**Mount order guarantee:** `DelegationStarted` is posted on `content_block_stop` for `conductor_delegate` (Phase 45). `AgentStateUpdated` fires only when state.json changes after `handle_delegate()` creates agents. This means `OrchestratorStatusCell` will always mount before `AgentCell`s — the timing is inherently correct.

**If label/description format needs polish:** Modify the `OrchestratorStatusCell` constructor call inside `TranscriptPane.on_delegation_started`. Example:
```python
# Current (transcript.py):
cell = OrchestratorStatusCell(
    label="Orchestrator \u2014 delegating",
    description=event.task_description,
)
```

### Pattern 3: Agent Completion Summary in finalize()

**What:** Success Criterion 3 requires AgentCell to show "the final task summary" when an agent completes. Currently `finalize()` sets status to "done" with no content.

**Where the summary data lives:** `Task.outputs: dict[str, Any]` in the state model. After orchestrator completes an agent's task, it sets `task.status = TaskStatus.COMPLETED`. The `outputs` dict may contain a summary key set by the orchestrator, or it may be empty. The `AgentRecord` does not store a summary field directly.

**Resolution:** Extend `AgentCell.finalize()` to accept an optional `summary: str` parameter. When provided, update the `cell-status` Static with the summary text. Update `TranscriptPane.on_agent_state_updated` to extract the summary from the associated `Task.outputs` when agent status is DONE.

**Extended finalize signature:**
```python
# In AgentCell (transcript.py):
def finalize(self, summary: str = "") -> None:
    """Mark cell as complete — idempotent, safe to call before or after mount."""
    self._stop_shimmer()
    self._status = "done"
    status_text = f"done — {summary}" if summary else "done"
    try:
        self.query_one(".cell-status", Static).update(status_text)
    except Exception:
        pass
```

**In TranscriptPane.on_agent_state_updated:**
```python
# Source: transcript.py on_agent_state_updated (current)
if agent.status == AgentStatus.DONE:
    # Find associated task to get summary
    task = tasks.get(agent.id)
    summary = ""
    if task is not None:
        summary = task.outputs.get("summary", "") if isinstance(task.outputs, dict) else ""
    cell.finalize(summary=summary)
```

**Fallback:** If `task.outputs` has no `"summary"` key (most agents don't set it), `finalize()` shows "done" — same as current behavior. No regressions.

### Pattern 4: Shimmer Timer Cleanup Verification — 3+ Concurrent Agents

**What:** Success Criterion 4 requires validation that shimmer timers are cleaned up after all agents complete in a 3+ concurrent agent scenario.

**Current implementation:** `AgentCell._stop_shimmer()` stops and nils the timer:
```python
# transcript.py (current)
def _stop_shimmer(self) -> None:
    if self._shimmer_timer is not None:
        self._shimmer_timer.stop()
        self._shimmer_timer = None
    try:
        self.styles.tint = _SHIMMER_OFF
    except Exception:
        pass
```

`finalize()` calls `_stop_shimmer()` unconditionally. This is already correct.

**What needs testing (not fixing):** Write a test that creates 3 AgentCells with `CONDUCTOR_NO_ANIMATIONS=1`, lets them shimmer (ANIMATIONS=0 means no shimmer is started because `_shimmer_forward` checks `_status != "working"` after `on_mount`... actually wait — with `_ANIMATIONS=0`, `on_mount` skips `self.styles.animate()` for opacity but `_shimmer_forward()` is still called from `on_mount`. The shimmer is separate from animations).

**Clarification on `_ANIMATIONS` flag:** The `_ANIMATIONS` flag (`CONDUCTOR_NO_ANIMATIONS=1`) gates ONLY the opacity fade-in animation (`self.styles.animate("opacity"...)`). The shimmer timer (`set_interval`) is always started in `on_mount` regardless of `_ANIMATIONS`. This means:
- In CI with `CONDUCTOR_NO_ANIMATIONS=1`: shimmer timers ARE created
- They must be stopped in `finalize()` — `_stop_shimmer()` handles this

**Verified from source:** `on_mount` in `AgentCell`:
```python
def on_mount(self) -> None:
    if _ANIMATIONS:  # gates opacity fade-in only
        self.styles.opacity = 0.0
        self.styles.animate(...)
    self._shimmer_forward()  # always called — starts timer
```

**Test to write:**
```python
async def test_shimmer_timers_cleaned_on_finalize_3_agents():
    # Mount 3 AgentCells in working state
    # Verify each has _shimmer_timer != None after mount
    # Call finalize() on each
    # Verify each has _shimmer_timer == None after finalize
```

### Anti-Patterns to Avoid

- **Using hardcoded hex colors in DEFAULT_CSS:** Always use Textual design tokens (`$success`, `$warning`, etc.) — they respect theme switching. Hardcoded colors break in light mode.
- **Asserting CSS color values in tests:** Tests cannot reliably check rendered color token values across Textual versions/themes. Assert on text content, not visual properties.
- **Adding a `.cell-summary` child widget to AgentCell:** Avoid DOM changes; reuse `.cell-status` Static by updating its text in `finalize()`. Adding a new child requires compose() changes and breaks existing tests that assert on child count.
- **Calling `_shimmer_forward()` multiple times:** `_shimmer_forward` starts a new timer without checking if one already exists. Always guard with `_status == "working"` check (already done) and only call from `on_mount()`.
- **Storing task.outputs summary per agent in a registry:** The summary is transient — once displayed in `finalize()`, it's in the widget. No need to persist it beyond the finalize call.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Color differentiation | Custom ANSI escape codes or hex colors | Textual design tokens (`$success`, `$warning`) | Tokens are theme-aware and future-proof |
| Shimmer leak detection | Custom timer audit loop | `assert cell._shimmer_timer is None` after `finalize()` | `_stop_shimmer()` already handles this — just test it |
| Task summary storage | New message type or registry | `Task.outputs.get("summary", "")` from existing state | `Task.outputs` dict already exists in state model |
| Completion cell | New widget class | Extend `AgentCell.finalize(summary=)` parameter | The cell is already in DOM — just update its status text |

## Common Pitfalls

### Pitfall 1: Shimmer Timer Starts in on_mount, Not Conditional on _ANIMATIONS
**What goes wrong:** Developer sets `CONDUCTOR_NO_ANIMATIONS=1` expecting no timers — but shimmer timers still start because `_ANIMATIONS` only gates opacity fade-in, not `_shimmer_forward()`.
**Why it happens:** The two animation systems (opacity fade + shimmer pulse) are independent. `_ANIMATIONS` is named "animations" but only gates the CSS animate call.
**How to avoid:** Set `CONDUCTOR_NO_ANIMATIONS=1` in tests for deterministic opacity assertions, but still call `finalize()` and assert `_shimmer_timer is None` regardless.
**Warning signs:** Test passes because timer starts but `stop()` is not called — only caught with explicit `_shimmer_timer is None` assertion after finalize.

### Pitfall 2: Task.outputs May Not Contain "summary" Key
**What goes wrong:** `task.outputs["summary"]` raises `KeyError`; alternative `task.outputs.get("summary")` returns `None` then `f"done — {None}"` shows "done — None" in the UI.
**Why it happens:** The orchestrator `_make_complete_task_fn` in `orchestrator.py` does not write to `task.outputs` — it only sets `task.status = TaskStatus.COMPLETED`. The `outputs` dict defaults to `{}`.
**How to avoid:** Always use `.get("summary", "")` and treat empty string as "no summary available." Only show summary text if non-empty:
```python
summary = task.outputs.get("summary", "") if isinstance(task.outputs, dict) else ""
status_text = f"done — {summary}" if summary else "done"
```
**Warning signs:** "done — None" or "done — " appearing in the cell status line.

### Pitfall 3: finalize() Called Before on_mount — query_one Raises
**What goes wrong:** `finalize()` called before the cell is mounted (early finalization race) raises `NoMatches` on `query_one(".cell-status", Static)`.
**Why it happens:** State.json watcher fires DONE before the cell has been added to DOM, or `_agent_cells` registration allows finalize before mount.
**How to avoid:** Existing `try/except Exception: pass` guard in `finalize()` already handles this — it's defensive by design (confirmed in Phase 43 research). Verify the test for early finalize still passes after adding the summary parameter.

### Pitfall 4: update_status() Called on Done Cell Reactivates Shimmer
**What goes wrong:** State.json can send a spurious WORKING update after DONE (race with watcher). If `update_status("working")` is called after `finalize()`, it re-enables the shimmer.
**Why it happens:** `update_status()` currently checks `if self._status == "done": return` — this guard is present in the code. Verify it is there.
**How to avoid:** The guard `if self._status == "done": return` at the top of `update_status()` must remain. It is already in the implementation.

### Pitfall 5: Inline Delegation Cell Mount Order Depends on Event Timing
**What goes wrong:** AgentCell appears before OrchestratorStatusCell if `AgentStateUpdated` somehow fires before `DelegationStarted` is processed.
**Why it happens:** Both are posted asynchronously. `DelegationStarted` is posted in `_stream_response` worker on `content_block_stop`. `AgentStateUpdated` fires from `AgentMonitorPane._watch_state` which polls state.json after `handle_delegate()` creates agents.
**Actual risk level:** LOW — agents are not created until `handle_delegate()` completes, which happens after the entire `conductor_delegate` tool-use block ends (after `content_block_stop`). `DelegationStarted` fires on `content_block_stop`. State.json is written by the orchestrator process asynchronously after delegation runs. The typical gap is 1-10 seconds. Mount order is correct in practice.
**How to verify:** Add a test that posts `DelegationStarted` then `AgentStateUpdated` and checks `OrchestratorStatusCell` appears first in the DOM.

## Code Examples

### AgentCell with Summary in finalize()
```python
# transcript.py — AgentCell.finalize() extended with summary parameter
def finalize(self, summary: str = "") -> None:
    """Mark cell as complete — idempotent, safe to call before or after mount."""
    self._stop_shimmer()
    self._status = "done"
    status_text = f"done \u2014 {summary}" if summary else "done"
    try:
        self.query_one(".cell-status", Static).update(status_text)
    except Exception:
        pass
```

### TranscriptPane.on_agent_state_updated — summary extraction
```python
# transcript.py — on_agent_state_updated, DONE branch updated
if agent.status == AgentStatus.DONE:
    task = tasks.get(agent.id)
    summary = ""
    if task is not None and isinstance(task.outputs, dict):
        summary = task.outputs.get("summary", "")
    cell.finalize(summary=summary)
```

### AgentCell CSS with distinct token
```python
# transcript.py — AgentCell.DEFAULT_CSS (current uses $warning)
# Phase 46 verifies this is distinct from AssistantCell ($accent = blue)
# $warning = amber/yellow, $success = green, $secondary = purple/teal
DEFAULT_CSS = """
AgentCell {
    background: $surface;
    border-left: solid $warning 40%;   # amber — distinct from blue $accent
    padding: 0 1;
    margin: 0 0 1 0;
}
AgentCell .cell-label {
    color: $warning;
    text-style: bold;
}
"""
```

### Test: Shimmer Timers Cleaned on finalize (3 agents)
```python
# tests/test_tui_visual_polish.py
import os
os.environ["CONDUCTOR_NO_ANIMATIONS"] = "1"

async def test_shimmer_timers_cleaned_on_finalize_3_agents():
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            for i in range(3):
                yield AgentCell(
                    agent_id=f"a{i}",
                    agent_name=f"Agent-{i}",
                    role="coder",
                    task_title=f"Task {i}",
                )

    app = TestApp()
    async with app.run_test() as pilot:
        cells = list(app.query(AgentCell))
        assert len(cells) == 3

        # Finalize all agents
        for cell in cells:
            cell.finalize()

        await pilot.pause()

        # Verify all shimmer timers are cleaned up
        for cell in cells:
            assert cell._shimmer_timer is None, (
                f"Shimmer timer not cleaned for {cell._agent_id}"
            )
            assert cell._status == "done"
```

### Test: AgentCell finalize shows summary
```python
async def test_agent_cell_finalize_shows_summary():
    from textual.app import App, ComposeResult
    from textual.widgets import Static
    from conductor.tui.widgets.transcript import AgentCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a1",
                agent_name="Alice",
                role="coder",
                task_title="Add auth",
            )

    app = TestApp()
    async with app.run_test() as pilot:
        cell = app.query_one(AgentCell)
        cell.finalize(summary="Implemented JWT auth with refresh tokens")
        await pilot.pause()
        status = cell.query_one(".cell-status", Static)
        assert "Implemented JWT auth" in str(status.content)
```

### Test: OrchestratorStatusCell appears before AgentCell in DOM
```python
async def test_delegation_cell_appears_before_agent_cells():
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import (
        TranscriptPane, OrchestratorStatusCell, AgentCell,
    )
    from conductor.tui.messages import DelegationStarted, AgentStateUpdated

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

        def on_agent_state_updated(self, event):
            from conductor.tui.messages import AgentStateUpdated
            pane = self.query_one(TranscriptPane)
            pane.post_message(AgentStateUpdated(event.state))

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)

        # Post delegation started first
        pane.post_message(DelegationStarted("Build auth module"))
        await pilot.pause()
        await pilot.pause()

        # Then post agent state update
        from tests.test_tui_transcript_bridge import _make_state
        state = _make_state(
            agents=[{"id": "a1", "name": "Alice", "role": "coder", "status": "working"}],
            tasks=[{"id": "t1", "title": "Auth", "description": "Implement auth", "assigned_agent": "a1"}],
        )
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()
        await pilot.pause()

        # Check DOM order: OrchestratorStatusCell before AgentCell
        children = list(pane.children)
        orch_idx = next(
            (i for i, c in enumerate(children) if isinstance(c, OrchestratorStatusCell)),
            None,
        )
        agent_idx = next(
            (i for i, c in enumerate(children) if isinstance(c, AgentCell)),
            None,
        )
        assert orch_idx is not None and agent_idx is not None
        assert orch_idx < agent_idx, (
            f"OrchestratorStatusCell (idx={orch_idx}) should appear before "
            f"AgentCell (idx={agent_idx})"
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| AgentCell finalize() shows only "done" | finalize(summary=) shows "done — {task summary}" | Phase 46 | Completion summary visible without side panel |
| OrchestratorStatusCell uses `$secondary` | Phase 46 verifies/adjusts token for max contrast | Phase 46 CSS-only | Visual distinction confirmed |
| 3-agent shimmer test absent | Explicit 3+ agent shimmer cleanup test added | Phase 46 | Validates timer lifecycle at scale |

**Deprecated/outdated:**
- None — Phase 46 has no deprecations. It is additive polish only.

## Open Questions

1. **Task.outputs["summary"] — does any orchestrator code write it?**
   - What we know: `Task.outputs: dict[str, Any]` defaults to `{}`. The `_make_complete_task_fn` in `orchestrator.py` does NOT write to `outputs` — it only sets `task.status = COMPLETED`. The DelegationManager `handle_delegate()` returns a summary string but does not write it to state.json.
   - What's unclear: Whether Phase 46 should teach the orchestrator to write a summary into `task.outputs["summary"]`, or whether the TUI should display a fallback.
   - Recommendation: For Phase 46, use fallback-only approach: `task.outputs.get("summary", "")`. If empty, show "done". The orchestrator writing a summary is a deeper change for a future phase. Completing SC-3 means the AgentCell CAN show a summary when data is present, not that data must always be present.

2. **CSS token choices — `$warning` vs `$success` for AgentCell**
   - What we know: `$warning` is currently assigned to AgentCell (amber), `$secondary` to OrchestratorStatusCell. Both are visually distinct from `$accent` (blue) used by AssistantCell.
   - What's unclear: Whether the current token choices (amber for agent, teal for orchestrator) are semantically correct, or should be swapped.
   - Recommendation: Keep current assignments. The visual distinction already exists. Phase 46 documents and verifies — does not mandate token swaps unless a visual review reveals a problem. SC-1 only requires "visually distinct from AssistantCell" which is already true.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + Textual test harness |
| Config file | `packages/conductor-core/pyproject.toml` (`asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest packages/conductor-core/tests/test_tui_visual_polish.py -x` |
| Full suite command | `uv run pytest packages/conductor-core/tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SC-1 | AgentCell and OrchestratorStatusCell have distinct CSS tokens from AssistantCell | unit | `uv run pytest tests/test_tui_visual_polish.py::test_cell_css_tokens_distinct -x` | ❌ Wave 0 |
| SC-2 | OrchestratorStatusCell appears in DOM before AgentCell after delegation | unit | `uv run pytest tests/test_tui_visual_polish.py::test_delegation_cell_before_agent_cells -x` | ❌ Wave 0 |
| SC-3 | AgentCell finalize() shows task summary when available | unit | `uv run pytest tests/test_tui_visual_polish.py::test_agent_cell_finalize_shows_summary -x` | ❌ Wave 0 |
| SC-4 | 3+ concurrent AgentCells have shimmer timers cleaned up after all finalize | unit | `uv run pytest tests/test_tui_visual_polish.py::test_shimmer_timers_cleaned_on_finalize_3_agents -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest packages/conductor-core/tests/test_tui_visual_polish.py -x`
- **Per wave merge:** `uv run pytest packages/conductor-core/tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `packages/conductor-core/tests/test_tui_visual_polish.py` — covers SC-1 through SC-4

*(Existing test infrastructure covers this. Only the new test file is missing.)*

## Sources

### Primary (HIGH confidence)
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/widgets/transcript.py` — `AgentCell`, `OrchestratorStatusCell`, `AssistantCell` implementations; `DEFAULT_CSS` tokens; `_stop_shimmer()`, `finalize()`, `_shimmer_forward()`, `on_mount()` — read directly
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/state/models.py` — `Task.outputs: dict[str, Any]`, `AgentRecord`, `AgentStatus.DONE` — read directly
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/messages.py` — `DelegationStarted`, `DelegationComplete` — read directly
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/app.py` — `_stream_response` worker, `on_agent_state_updated` fan-out — read directly
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — `_make_complete_task_fn` (confirms `task.outputs` is not written by orchestrator) — read directly
- `.planning/STATE.md` — Phase 46 known blocker: scroll under N concurrent agents not profiled
- `.planning/phases/43-agent-cell-widgets/43-RESEARCH.md` — shimmer timer pattern, `_ANIMATIONS` flag semantics
- `.planning/phases/45-sdk-stream-interception-and-orchestrator-status/45-RESEARCH.md` — `OrchestratorStatusCell` lifecycle, `DelegationStarted` message structure

### Secondary (MEDIUM confidence)
- `tests/test_tui_agent_cells.py` — `finalize()` test patterns, CONDUCTOR_NO_ANIMATIONS=1 usage
- `tests/test_tui_transcript_bridge.py` — `_make_state()` helper, AgentStateUpdated test patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; all APIs read directly from source
- Architecture: HIGH — all four success criteria map to concrete, isolated code changes in `transcript.py`
- Pitfalls: HIGH — timer cleanup path read directly; `Task.outputs` emptiness confirmed by reading orchestrator source; CSS token distinctness verified against existing DEFAULT_CSS

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable — Textual 4.x API, internal project code)
