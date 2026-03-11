# Phase 44: TranscriptPane Extensions and State Bridge - Research

**Researched:** 2026-03-12
**Domain:** Textual TUI widget messaging, state.json fan-out, AgentCell lifecycle in TranscriptPane
**Confidence:** HIGH

## Summary

Phase 44 extends `TranscriptPane` to receive `AgentStateUpdated` messages and manage `AgentCell` widgets inline in the conversation transcript. The entire implementation is internal to the existing codebase — no new dependencies are needed. All required APIs (`AgentCell`, `AgentStateUpdated`, `ConductorState`, `AgentStatus`) are already in place from previous phases.

The core challenge is the lifecycle difference from `AgentMonitorPane`: the monitor *removes* panels when agents complete (DONE), while the transcript must *retain* cells permanently after finalization so the conversation record remains intact. A `_agent_cells: dict[str, AgentCell]` registry enables deduplication across repeated state updates.

The second challenge is the message fan-out: `AgentStateUpdated` currently only reaches `AgentMonitorPane` because the watcher's `post_message()` is called on that pane. To satisfy BRDG-01, the `ConductorApp` must also forward (or re-post) the message to `TranscriptPane`.

**Primary recommendation:** Add `on_agent_state_updated` to `TranscriptPane` with a `_agent_cells` dict. Wire fan-out in `ConductorApp.on_agent_state_updated` by querying `TranscriptPane` and calling `post_message`. Use smart scroll (`_maybe_scroll_end`) for new cell mounts.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BRDG-01 | AgentStateUpdated messages from state.json watcher are forwarded to TranscriptPane (not just AgentMonitorPane) | Fan-out pattern via ConductorApp message handler; watcher lives in AgentMonitorPane |
| BRDG-02 | TranscriptPane maintains an _agent_cells registry mapping agent_id to AgentCell for lifecycle management | Dict initialized in TranscriptPane.__init__, populated in on_agent_state_updated |
| ACELL-01 | User sees a labeled AgentCell in the transcript when a sub-agent starts working, showing agent name, role, and task title | mount AgentCell when agent first appears as WORKING |
| ACELL-02 | AgentCell updates in real-time as state.json changes (status transitions: working → waiting → done) | call cell.update_status() on each AgentStateUpdated for known agents |
| ACELL-03 | When an agent completes, its AgentCell shows a completion summary with final status | call cell.finalize() when AgentStatus.DONE detected; cell stays in transcript |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | >=4.0 (installed) | TUI framework, VerticalScroll, post_message, on_mount | Already in pyproject.toml |
| conductor.tui.widgets.transcript | existing | AgentCell, TranscriptPane, _maybe_scroll_end | Phase 43 delivered all widget classes |
| conductor.tui.messages | existing | AgentStateUpdated message type | Already defined with `state: ConductorState` |
| conductor.state.models | existing | AgentStatus enum (WORKING/WAITING/DONE/IDLE) | StrEnum values: "working", "waiting", "done", "idle" |

### No New Dependencies
All required code is already installed. Zero new packages needed.

## Architecture Patterns

### Recommended Project Structure

No new files needed. All changes go into:
```
packages/conductor-core/src/conductor/tui/
├── widgets/transcript.py     # extend TranscriptPane (primary change)
├── app.py                    # add on_agent_state_updated fan-out
└── messages.py               # no change needed
packages/conductor-core/tests/
└── test_tui_transcript_bridge.py   # new test file for Phase 44
```

### Pattern 1: _agent_cells Registry in TranscriptPane.__init__

**What:** A plain dict `_agent_cells: dict[str, AgentCell]` initialized in `__init__` alongside `_resume_mode`.
**When to use:** Required for BRDG-02. Prevents duplicate AgentCells across repeated state updates for the same agent_id.
**Example:**
```python
# In TranscriptPane.__init__
def __init__(self, *, resume_mode: bool = False, **kwargs: object) -> None:
    super().__init__(**kwargs)
    self._resume_mode = resume_mode
    self._agent_cells: dict[str, "AgentCell"] = {}
```

### Pattern 2: on_agent_state_updated in TranscriptPane

**What:** Message handler that mounts new `AgentCell` for first-seen WORKING agents, calls `update_status()` for known agents, and calls `finalize()` when agent reaches DONE.
**When to use:** Core of ACELL-01, ACELL-02, ACELL-03.
**Example:**
```python
async def on_agent_state_updated(self, event: "AgentStateUpdated") -> None:
    from conductor.state.models import AgentStatus

    state = event.state
    tasks = {t.assigned_agent: t for t in state.tasks if t.assigned_agent}
    agents_by_id = {a.id: a for a in state.agents}

    for agent in state.agents:
        task = tasks.get(agent.id)
        task_title = task.title if task else "(unknown task)"

        if agent.id not in self._agent_cells:
            # Only create cell when agent first appears as WORKING
            if agent.status == AgentStatus.WORKING:
                cell = AgentCell(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    role=agent.role,
                    task_title=task_title,
                )
                self._agent_cells[agent.id] = cell
                await self.mount(cell)
                self._maybe_scroll_end()
        else:
            cell = self._agent_cells[agent.id]
            if agent.status == AgentStatus.DONE:
                cell.finalize()
            else:
                cell.update_status(str(agent.status))
```

### Pattern 3: Fan-out in ConductorApp (BRDG-01)

**What:** `ConductorApp` handles `AgentStateUpdated` and forwards it to `TranscriptPane` via `post_message`. The message bubbles from `AgentMonitorPane` up to `App`, which then manually pushes it down to `TranscriptPane`.
**When to use:** This is the only way to route the watcher's message to TranscriptPane — `AgentMonitorPane` owns the watcher and posts the message to itself. Textual messages bubble up, not down.
**Example:**
```python
# In ConductorApp (app.py)
def on_agent_state_updated(self, event: "AgentStateUpdated") -> None:
    """Fan-out: forward to TranscriptPane in addition to AgentMonitorPane."""
    from conductor.tui.widgets.transcript import TranscriptPane
    from conductor.tui.messages import AgentStateUpdated
    try:
        pane = self.query_one(TranscriptPane)
        pane.post_message(AgentStateUpdated(event.state))
    except Exception:
        pass
```

**Important:** The `on_agent_state_updated` in `AgentMonitorPane` still fires (it's on the pane, not stopped). The app handler is additive — it does NOT call `event.stop()`.

### Pattern 4: Smart Scroll for New AgentCells

**What:** Use `_maybe_scroll_end()` (already implemented in TranscriptPane) when mounting new AgentCells. This respects scroll position — only auto-scrolls if user is already at bottom.
**When to use:** ACELL-01 success criterion 5 — scroll position must be preserved when user has scrolled up.

```python
# _maybe_scroll_end is already in TranscriptPane:
def _maybe_scroll_end(self) -> None:
    if self._is_at_bottom:
        self.scroll_end(animate=False)
```

### Anti-Patterns to Avoid

- **Removing AgentCell from transcript on DONE:** AgentMonitorPane removes panels when agents complete. TranscriptPane must NOT remove cells — they are a permanent conversation record. Call `finalize()` instead.
- **Creating AgentCell for IDLE/WAITING agents that never appeared as WORKING:** Only create a cell when `agent.status == AgentStatus.WORKING` and `agent.id not in _agent_cells`. Never retroactively create cells for agents already done.
- **Using `await self.app.query_one(TranscriptPane)` inside AgentMonitorPane:** Don't modify the monitor pane to push to the transcript — put fan-out in `ConductorApp`.
- **Calling `event.stop()` in app's on_agent_state_updated:** The monitor pane must still receive the event. The app handler is purely additive.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Agent-to-cell deduplication | Custom list scan | `dict[str, AgentCell]` keyed by agent_id | O(1) lookup, already decided in STATE.md decisions |
| Scroll position check | Manual scroll offset math | `_is_at_bottom` / `_maybe_scroll_end` | Already implemented in TranscriptPane |
| Widget ID sanitization | Custom regex | `_sanitize_id()` already in transcript.py | Avoids CSS ID collisions, already tested |
| Message routing | Direct method calls across widget boundaries | `post_message(AgentStateUpdated(...))` | Textual's async-safe pattern |

**Key insight:** `AgentMonitorPane.on_agent_state_updated` is the reference implementation. TranscriptPane's handler follows the same diff-against-registry pattern but with `finalize()` instead of `remove()` for DONE agents.

## Common Pitfalls

### Pitfall 1: AgentStateUpdated Never Reaches TranscriptPane
**What goes wrong:** Tests show TranscriptPane handler never firing even though watcher is running.
**Why it happens:** `AgentMonitorPane._watch_state` calls `self.post_message(AgentStateUpdated(...))` — message posts to the pane, bubbles up to app, but does NOT propagate sideways to TranscriptPane.
**How to avoid:** Add `on_agent_state_updated` to `ConductorApp` that forwards the message to `TranscriptPane` via `pane.post_message(...)`.
**Warning signs:** Monitor pane updates but transcript cells never appear.

### Pitfall 2: Duplicate AgentCells on Rapid State Updates
**What goes wrong:** Same agent appears twice in transcript if two state updates arrive before the first `await self.mount(cell)` returns.
**Why it happens:** `agent.id not in self._agent_cells` check passes twice before the dict is updated.
**How to avoid:** Add `self._agent_cells[agent.id] = cell` to the dict BEFORE `await self.mount(cell)`:
```python
cell = AgentCell(...)
self._agent_cells[agent.id] = cell  # register first
await self.mount(cell)              # then mount
```
**Warning signs:** Multiple cells with the same `acell-{id}` appearing.

### Pitfall 3: Creating Cells for Agents That Start as WAITING
**What goes wrong:** An agent in the state might transition directly to WAITING without ever being WORKING in a seen state snapshot.
**Why it happens:** State watcher fires after a write that went IDLE→WAITING without a WORKING intermediate snapshot.
**How to avoid:** Only create a cell if `agent.status == AgentStatus.WORKING` on first encounter. If first encounter is WAITING or DONE, skip creation. The transcript only shows cells for agents it has "witnessed" starting.
**Warning signs:** Cells appearing with wrong initial status, or calls to `update_status("waiting")` on a cell for an agent that was never working.

### Pitfall 4: Scroll Jump When User Has Scrolled Up
**What goes wrong:** New AgentCell mounts always scroll to bottom, disrupting user reading history.
**Why it happens:** Using `self.scroll_end()` directly instead of `_maybe_scroll_end()`.
**How to avoid:** Always use `self._maybe_scroll_end()` when mounting AgentCells. Only `add_user_message` should force-scroll (user's own action).
**Warning signs:** Transcript jumps to bottom whenever an agent update arrives.

### Pitfall 5: AgentStatus String Values vs Enum
**What goes wrong:** `str(agent.status)` returns the StrEnum value (e.g. `"working"`) because `AgentStatus(StrEnum)` uses value-only display. Comparing `agent.status == AgentStatus.WORKING` works correctly because `ConductorState` uses `use_enum_values=True` — `agent.status` is a string after Pydantic deserialization.
**How to avoid:** Use `from conductor.state.models import AgentStatus` and compare `agent.status == AgentStatus.WORKING` (string equality via StrEnum) or `agent.status == "working"` — both work.
**Warning signs:** `if agent.status == AgentStatus.WORKING` never matching.

## Code Examples

Verified patterns from existing codebase:

### AgentMonitorPane.on_agent_state_updated (reference pattern)
```python
# Source: packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py:133
async def on_agent_state_updated(self, event: "AgentStateUpdated") -> None:
    from conductor.state.models import AgentStatus

    state = event.state
    active = {
        a.id: a
        for a in state.agents
        if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)
    }
    tasks = {t.assigned_agent: t for t in state.tasks if t.assigned_agent}

    for panel in list(self.query(AgentPanel)):
        if panel.agent_id not in active:
            await panel.remove()

    existing_ids = {p.agent_id for p in self.query(AgentPanel)}
    for agent_id, agent in active.items():
        task = tasks.get(agent_id)
        task_title = task.title if task else "(unknown task)"
        if agent_id not in existing_ids:
            await self.mount(AgentPanel(...))
        else:
            panel = self.query_one(f"#agent-{agent_id}", AgentPanel)
            panel.update_status(agent.name, str(agent.status), task_title)
```

### Test pattern: post_message + await pilot.pause()
```python
# Source: packages/conductor-core/tests/test_tui_agent_monitor.py:63-69
async with app.run_test() as pilot:
    pane = app.query_one(AgentMonitorPane)
    pane.post_message(AgentStateUpdated(state))
    await pilot.pause()
    panels = pane.query(AgentPanel)
    assert len(panels) == 1
```

### AgentCell constructor (from Phase 43)
```python
# Source: packages/conductor-core/src/conductor/tui/widgets/transcript.py:189
AgentCell(
    agent_id="a1",
    agent_name="Agent 1",
    role="coder",
    task_title="Add auth module",
)
```

### _maybe_scroll_end (smart scroll)
```python
# Source: packages/conductor-core/src/conductor/tui/widgets/transcript.py:361
def _maybe_scroll_end(self) -> None:
    """Scroll to bottom only if the user hasn't scrolled up."""
    if self._is_at_bottom:
        self.scroll_end(animate=False)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `_active_cell` for streaming | `_agent_cells` dict for N concurrent agents | Phase 44 (this phase) | Enables multi-agent transcript |
| AgentStateUpdated only to AgentMonitorPane | Fan-out via ConductorApp.on_agent_state_updated | Phase 44 (this phase) | BRDG-01 compliance |
| AgentMonitorPane removes cells on DONE | TranscriptPane finalizes (keeps) cells on DONE | Phase 44 design | Permanent conversation record |

## Open Questions

1. **What happens if an agent first appears with status DONE (missed WORKING snapshot)?**
   - What we know: State watcher debounces at 200ms — rapid transitions may coalesce
   - What's unclear: Should a DONE-on-first-sight agent get a finalized cell or no cell?
   - Recommendation: Skip creation entirely — no cell for agents never witnessed as WORKING. The transcript only shows live activity.

2. **Should _agent_cells ever be cleared (e.g., on new session)?**
   - What we know: TranscriptPane is re-created on app restart; `_agent_cells` is instance-state
   - What's unclear: Session resume may replay old state.json updates
   - Recommendation: Leave dict as-is for this phase; Phase 46 (polish) can address if needed.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest with pytest-asyncio |
| Config file | `packages/conductor-core/pyproject.toml` (pytest section) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_tui_transcript_bridge.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BRDG-01 | AgentStateUpdated forwarded to TranscriptPane via ConductorApp | unit | `pytest tests/test_tui_transcript_bridge.py::test_state_update_forwarded_to_transcript -x` | Wave 0 |
| BRDG-02 | _agent_cells dict maps agent_id to AgentCell, no duplicates | unit | `pytest tests/test_tui_transcript_bridge.py::test_agent_cells_registry_no_duplicates -x` | Wave 0 |
| ACELL-01 | WORKING agent triggers AgentCell mount in transcript | unit | `pytest tests/test_tui_transcript_bridge.py::test_working_agent_mounts_cell -x` | Wave 0 |
| ACELL-02 | Status transitions update existing cell | unit | `pytest tests/test_tui_transcript_bridge.py::test_status_transition_updates_cell -x` | Wave 0 |
| ACELL-03 | DONE agent finalizes cell (stays in transcript) | unit | `pytest tests/test_tui_transcript_bridge.py::test_done_agent_finalizes_cell -x` | Wave 0 |
| SC-5 | Scroll preserved when user has scrolled up | unit | `pytest tests/test_tui_transcript_bridge.py::test_scroll_preserved_when_scrolled_up -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_tui_transcript_bridge.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui_transcript_bridge.py` — new file covering all Phase 44 requirements
  - Follows existing pattern from `test_tui_agent_monitor.py`:
    - `CONDUCTOR_NO_ANIMATIONS=1` at top
    - `_make_state()` helper for ConductorState construction
    - Inline `TestApp` classes in each test (never in fixtures — Textual contextvars pitfall)
    - `pane.post_message(AgentStateUpdated(state))` + `await pilot.pause()`

*(Existing test infrastructure: pytest + pytest-asyncio already configured; `tests/test_tui_agent_cells.py` confirms pattern works)*

## Sources

### Primary (HIGH confidence)
- `/packages/conductor-core/src/conductor/tui/widgets/transcript.py` — TranscriptPane, AgentCell, OrchestratorStatusCell, _sanitize_id, _maybe_scroll_end
- `/packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py` — AgentMonitorPane reference implementation for on_agent_state_updated pattern
- `/packages/conductor-core/src/conductor/tui/app.py` — ConductorApp, on_mount, existing message handlers, on_stream_done fan-out example
- `/packages/conductor-core/src/conductor/tui/messages.py` — AgentStateUpdated definition
- `/packages/conductor-core/src/conductor/state/models.py` — AgentStatus, AgentRecord, ConductorState, Task
- `/packages/conductor-core/tests/test_tui_agent_monitor.py` — test pattern: _make_state, post_message, pilot.pause
- `/packages/conductor-core/tests/test_tui_agent_cells.py` — Phase 43 test patterns, Static.content API
- `.planning/STATE.md` — accumulated decisions including `_agent_cells dict from Phase 44 start`

### Secondary (MEDIUM confidence)
- `.planning/REQUIREMENTS.md` — BRDG-01, BRDG-02, ACELL-01-03 requirement text
- `.planning/ROADMAP.md` — Phase 44 success criteria verbatim

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries and classes confirmed in source code
- Architecture: HIGH — fan-out pattern visible in app.py (on_stream_done), reference implementation in agent_monitor.py
- Pitfalls: HIGH — pitfall 1 (fan-out) and pitfall 2 (duplicate) confirmed by studying the message bus topology and async mount patterns
- Test patterns: HIGH — copied from working Phase 35/43 test files

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable codebase, no external dependencies)
