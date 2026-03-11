# Phase 35: Agent Monitoring - Research

**Researched:** 2026-03-11
**Domain:** Textual TUI — file watching, collapsible widgets, reactive agent status panels
**Confidence:** HIGH

## Summary

Phase 35 wires the existing `AgentMonitorPane` placeholder into a live, reactive panel that shows per-agent status sourced from `state.json`. The data model is fully defined: `AgentRecord` (id, name, role, status, current_task_id) and `Task` (id, title, description, status, assigned_agent) live in `ConductorState`. The file-watching pattern is already proven in `dashboard/watcher.py` using `watchfiles.awatch` on the parent directory — Phase 35 reuses this exact approach as a `@work` Textual worker inside `AgentMonitorPane`.

Textual 8.1.1 (installed) ships `Collapsible` with `collapsed: reactive(True)` and children passed at construction. Dynamic agent panels are mounted/removed via `await self.mount()` / `await widget.remove()` in response to state changes. Tool activity tracking currently lives only in `StreamMonitor._tool_events` (a list of SDK tool names per agent task session). There is no live streaming feed of tool activity to the TUI — Phase 35 must decide how to surface it: either via state.json writes by the orchestrator, or via a secondary Textual message bus path from `DelegationManager`.

**Primary recommendation:** Implement `StateWatchWorker` as a `@work(exclusive=True)` coroutine inside `AgentMonitorPane` that watches `.conductor/state.json` using `watchfiles.awatch` (directory-level watch, same as dashboard watcher), reads the new state via `asyncio.to_thread`, diffs agent list, then posts a custom `AgentStateUpdated` message to trigger panel mount/update/remove. Use one `AgentPanel(Collapsible)` widget per active agent. Tool activity for AGNT-03 should be implemented as a `Static` log list inside each panel — populated by adding lines when agent task status changes (file, edit, command names), not real-time streaming.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AGNT-01 | User sees inline collapsible panels for each active agent showing name, task, and status | `Collapsible` widget verified in Textual 8.1.1; `AgentRecord.name`, `AgentRecord.role`, `AgentRecord.status`, joined with `Task.title`/`Task.description` via `assigned_agent` field |
| AGNT-02 | Agent panels update in real-time as state.json changes (wired to file watcher) | `watchfiles.awatch` pattern proven in `dashboard/watcher.py`; must watch parent directory due to inode-swap atomic writes; `asyncio.to_thread` for non-blocking read |
| AGNT-03 | User can expand an agent panel to see streaming tool activity and output | `StreamMonitor._tool_events` holds SDK tool names per session; no live feed to TUI yet — simplest path: log status-change lines (task assigned, task completed, tool event count) inside expanded panel; or wire a new `ToolActivity` message from orchestrator path |
| AGNT-04 | Agent panels appear when delegation starts and collapse/archive when agents complete | Mount `AgentPanel` on WORKING/WAITING agents; move to "archived" section or call `await widget.remove()` when agent status becomes DONE |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | 8.1.1 (installed) | UI framework, widget tree, event loop | Project standard since Phase 31 |
| watchfiles | 1.1.1 (installed) | Async file watching via `awatch` | Already used in `dashboard/watcher.py` for state.json |
| pydantic | 2.x (installed) | `ConductorState` / `AgentRecord` deserialization | Project standard |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio.to_thread | stdlib | Non-blocking file read inside worker | Avoid blocking Textual event loop during JSON parse |
| `textual.widgets.Collapsible` | 8.1.1 | Expandable per-agent panel | One instance per active agent |
| `textual.reactive` | 8.1.1 | Reactive attributes on `AgentPanel` (status label, elapsed) | Auto-repaint when status changes |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `watchfiles.awatch` | `asyncio.get_event_loop().add_reader` + inotify | awatch already handles inode-swap edge case; no reason to hand-roll |
| `Collapsible` | Custom `Widget` with `display: none` toggle | Collapsible is built-in, tested, has `Toggled`/`Expanded`/`Collapsed` events |
| `@work` coroutine for file watching | `set_interval` polling | `awatch` is event-driven, zero CPU when idle; polling adds latency |

**Installation:** All dependencies already installed.

## Architecture Patterns

### Recommended Project Structure

No new files needed beyond:
```
packages/conductor-core/src/conductor/tui/
├── widgets/
│   └── agent_monitor.py    # Replace placeholder — StateWatchWorker + AgentPanel
├── messages.py              # Add AgentStateUpdated message
└── tests/
    └── test_tui_agent_monitor.py   # NEW
```

### Pattern 1: StateWatchWorker via @work

**What:** `AgentMonitorPane` launches a `@work(exclusive=True, exit_on_error=False)` coroutine on mount that runs the `awatch` loop and posts `AgentStateUpdated` messages when state changes.

**When to use:** Whenever a background async loop must post UI updates — same pattern as `_stream_response` in `app.py`.

**Example:**
```python
# Source: dashboard/watcher.py + app.py @work pattern
from textual import work
from watchfiles import awatch

class AgentMonitorPane(VerticalScroll):
    @work(exclusive=True, exit_on_error=False)
    async def _watch_state(self, state_path: Path) -> None:
        from conductor.dashboard.events import classify_delta
        from conductor.state.manager import StateManager
        prev = None
        async for changes in awatch(str(state_path.parent), debounce=200):
            changed_names = {Path(p).name for _, p in changes}
            if state_path.name not in changed_names:
                continue
            try:
                new_state = await asyncio.to_thread(
                    StateManager(state_path).read_state
                )
            except Exception:
                continue
            self.post_message(AgentStateUpdated(new_state))
            prev = new_state
```

### Pattern 2: AgentPanel as Collapsible

**What:** `AgentPanel` subclasses `Collapsible`, title shows agent name + status. Expanded content shows task title + tool activity log.

**When to use:** Each active `AgentRecord` in state gets one `AgentPanel`.

**Example:**
```python
# Source: Collapsible API verified from textual 8.1.1 source
class AgentPanel(Collapsible):
    status: reactive[str] = reactive("working")

    def __init__(self, agent: AgentRecord, task_title: str) -> None:
        super().__init__(
            title=f"{agent.name} — {agent.status}",
            collapsed=True,
        )
        self._agent_id = agent.id
        self._task_title = task_title
        self._activity_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static(self._task_title, id="panel-task")
        yield Static("", id="panel-activity")

    def update_status(self, agent: AgentRecord, task_title: str) -> None:
        self.title = f"{agent.name} — {agent.status}"
        self.query_one("#panel-task", Static).update(task_title)
```

### Pattern 3: Mount/Remove on State Delta

**What:** `on_agent_state_updated` handler diffs current panels against new state, mounts new panels for new agents, updates existing, removes panels for DONE agents (or moves to archived Static).

**When to use:** In `AgentMonitorPane.on_agent_state_updated`.

**Example:**
```python
def on_agent_state_updated(self, event: AgentStateUpdated) -> None:
    state = event.state
    active = {
        a.id: a for a in state.agents
        if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)
    }
    # task lookup
    tasks = {t.assigned_agent: t for t in state.tasks if t.assigned_agent}

    # Remove panels for completed agents
    for panel in self.query(AgentPanel):
        if panel.agent_id not in active:
            panel.remove()  # returns AwaitRemove; use self.call_later or await

    # Mount new panels or update existing
    existing_ids = {p.agent_id for p in self.query(AgentPanel)}
    for agent_id, agent in active.items():
        task = tasks.get(agent_id)
        task_title = task.title if task else "(unknown task)"
        if agent_id not in existing_ids:
            self.mount(AgentPanel(agent, task_title))
        else:
            panel = self.query_one(f"#agent-{agent_id}", AgentPanel)
            panel.update_status(agent, task_title)
```

### Anti-Patterns to Avoid

- **Direct `widget.remove()` in message handler without `call_later`:** `remove()` returns an `AwaitRemove` object; inside a sync handler you must call `self.app.call_later(panel.remove)` or make the handler `async def`.
- **Watching state.json path directly (not parent dir):** `StateManager` uses `os.replace` which swaps the inode — `awatch` on the file path itself misses these events. Always watch the parent directory and filter by filename.
- **Calling `awatch` from a thread worker (`thread=True`):** `awatch` is an async generator; use `@work` (default asyncio worker), not thread worker.
- **ID collisions on AgentPanel:** Use `id=f"agent-{agent.id}"` so `query_one` lookups are unambiguous. Agent IDs from `AgentRecord.id` are already unique.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Collapsible panel toggle | Custom CSS `display: none` toggling | `textual.widgets.Collapsible` | Built-in keyboard/click handling, `Expanded`/`Collapsed` events, focus management |
| File change detection | `asyncio` polling loop with `mtime` check | `watchfiles.awatch` | Handles inode-swap, debouncing, stop_event — already in project deps |
| State diffing | Custom dict comparison | Reuse `classify_delta` from `dashboard/events.py` | Already tested, handles agent/task delta events correctly |

**Key insight:** The dashboard already solved the hard problems (inode-aware watching, state diffing). Phase 35 is primarily plumbing the existing dashboard infrastructure into the TUI widget layer.

## Common Pitfalls

### Pitfall 1: awatch misses atomic writes
**What goes wrong:** Watching the file path directly via `watchfiles` gives zero events when `StateManager._atomic_write` does `os.replace(tmp, state_path)` — the inode changes so the watch descriptor becomes stale.
**Why it happens:** `os.replace` on Linux moves the temp file into place, creating a new inode. A watcher on the original path watches the old inode.
**How to avoid:** Watch `state_path.parent` and filter `{Path(p).name for _, p in changes}` to match `state_path.name`. This is exactly what `dashboard/watcher.py` does.
**Warning signs:** File watcher never fires despite orchestrator writing state updates.

### Pitfall 2: remove() in sync handler silently does nothing
**What goes wrong:** Calling `panel.remove()` in a synchronous message handler without awaiting it — the `AwaitRemove` coroutine is created but never scheduled.
**Why it happens:** `remove()` returns `AwaitRemove` (an awaitable), not a direct action.
**How to avoid:** Either make the handler `async def on_agent_state_updated(self, event)` and `await panel.remove()`, or use `self.app.call_later(panel.remove)`.
**Warning signs:** Dead agent panels accumulate without disappearing.

### Pitfall 3: @work stop on app exit
**What goes wrong:** `StateWatchWorker` holds open an `awatch` generator that blocks app shutdown if not cancelled.
**Why it happens:** `awatch` loops indefinitely unless stopped via `stop_event` or worker cancellation.
**How to avoid:** Textual `@work` workers are automatically cancelled when the app exits (confirmed in Textual source). No explicit `stop_event` needed when using `@work`. But `awatch` also accepts a `stop_event: asyncio.Event` parameter for explicit control if needed.
**Warning signs:** App hangs on exit with `KeyboardInterrupt`.

### Pitfall 4: AgentPanel compose() mounts before data is known
**What goes wrong:** `AgentPanel` tries to `query_one` its own children in `__init__` before `compose()` runs.
**Why it happens:** Children don't exist until the widget is mounted into the DOM.
**How to avoid:** Store data as instance attributes in `__init__`, render in `compose()`, update via `query_one().update()` in `update_status()`.

### Pitfall 5: Tool activity for AGNT-03 has no live feed
**What goes wrong:** `StreamMonitor._tool_events` collects tool names during agent execution inside `orchestrator.py`, but nothing currently sends these to the TUI.
**Why it happens:** The orchestrator runs inside `DelegationManager.handle_delegate()` which is a `@tool` callback on the SDK. There is no direct message channel from orchestrator worker to AgentMonitorPane.
**How to avoid:** Two options — (A) surface tool events via state.json writes (add a `tool_log: list[str]` field to `AgentRecord` and write after each tool use), or (B) add a TUI-specific callback to `DelegationManager` that posts `ToolActivity` messages. Option A is simpler and keeps the file watcher as the single source of truth. **Recommend Option A for Phase 35 scope — if `AgentRecord` modification is too invasive, fall back to showing task-level status changes (assigned, in_progress, completed) as "activity" items.**

## Code Examples

### StateWatchWorker wiring
```python
# Source: dashboard/watcher.py pattern + app.py @work pattern
import asyncio
from pathlib import Path
from textual import work
from watchfiles import awatch

class AgentMonitorPane(VerticalScroll):
    def on_mount(self) -> None:
        state_path = Path(self.app._cwd) / ".conductor" / "state.json"
        if state_path.parent.exists() or True:  # watch even before file created
            self._watch_state(state_path)

    @work(exclusive=True, exit_on_error=False)
    async def _watch_state(self, state_path: Path) -> None:
        from conductor.state.manager import StateManager
        state_path.parent.mkdir(parents=True, exist_ok=True)
        async for changes in awatch(str(state_path.parent), debounce=200):
            changed_names = {Path(p).name for _, p in changes}
            if state_path.name not in changed_names:
                continue
            try:
                new_state = await asyncio.to_thread(
                    StateManager(state_path).read_state
                )
            except Exception:
                continue
            self.post_message(AgentStateUpdated(new_state))
```

### Collapsible AgentPanel creation
```python
# Source: Textual 8.1.1 Collapsible API verified
from textual.widgets import Collapsible, Static
from conductor.state.models import AgentRecord

class AgentPanel(Collapsible):
    def __init__(self, agent_id: str, title: str) -> None:
        super().__init__(
            title=title,
            collapsed=True,
            id=f"agent-{agent_id.replace('/', '-')}",
        )
        self._agent_id = agent_id

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def compose(self) -> ComposeResult:
        yield Static("", id="task-info")
        yield Static("", id="activity-log")

    def refresh_data(self, task_title: str, activity: str) -> None:
        self.query_one("#task-info", Static).update(task_title)
        self.query_one("#activity-log", Static).update(activity)
```

### AgentStateUpdated message definition
```python
# Source: messages.py existing pattern
from textual.message import Message
from conductor.state.models import ConductorState

class AgentStateUpdated(Message):
    """State watcher detected a change in state.json."""
    def __init__(self, state: ConductorState) -> None:
        self.state = state
        super().__init__()
```

### Test pattern (async, no fixtures)
```python
# Source: test_tui_shell.py / test_tui_streaming.py patterns
# IMPORTANT: Keep run_test() inline -- never in fixtures (GitHub #4998)
async def test_agent_panel_appears_for_working_agent():
    from conductor.tui.app import ConductorApp
    from conductor.tui.widgets.agent_monitor import AgentMonitorPane, AgentPanel
    from conductor.tui.messages import AgentStateUpdated
    from conductor.state.models import (
        ConductorState, AgentRecord, AgentStatus, Task, TaskStatus
    )

    app = ConductorApp()
    async with app.run_test() as pilot:
        pane = app.query_one(AgentMonitorPane)
        state = ConductorState(
            agents=[AgentRecord(
                id="agent-001", name="Agent 1", role="coder",
                status=AgentStatus.WORKING, current_task_id="t-001"
            )],
            tasks=[Task(
                id="t-001", title="Add auth module",
                description="...", assigned_agent="agent-001",
                status=TaskStatus.IN_PROGRESS
            )],
        )
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()

        panels = pane.query(AgentPanel)
        assert len(panels) == 1
        assert panels[0].agent_id == "agent-001"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling `mtime` | `watchfiles.awatch` event-driven | Already adopted in Phase 9 (dashboard) | Zero CPU idle |
| Rich `Console.print` for status | Textual widget reactive updates | Phase 31 (prompt_toolkit removal) | No ANSI corruption |
| `AgentMonitorPane` as static placeholder | Reactive panels wired to state.json | Phase 35 (this phase) | Live monitoring |

**Deprecated/outdated:**
- `DelegationManager.print_status()`: The Rich console-based status printer. The comment in `delegation.py` line 164 explicitly says "status display moved to Textual StateWatchWorker in Phase 35." It should remain in place for backward compat (console=None guard already present) but is no longer the primary display path.

## Open Questions

1. **Tool activity live feed (AGNT-03 full fidelity)**
   - What we know: `StreamMonitor._tool_events` collects tool names during agent execution. `ToolActivity` message exists in `messages.py`. No current path from orchestrator to TUI.
   - What's unclear: Whether modifying `AgentRecord` to add `tool_log: list[str]` is acceptable scope, or if task-status transitions are sufficient for "activity."
   - Recommendation: For Phase 35, show task status transitions as activity lines (e.g., "Task assigned", "In progress", "Completed") plus a count like "3 tools used" from `AgentRecord.outputs` if present. Full real-time tool streaming deferred to Phase 36 or later.

2. **state_path source in AgentMonitorPane**
   - What we know: `ConductorApp._cwd` holds the repo path. `DelegationManager` creates state at `{_cwd}/.conductor/state.json`.
   - What's unclear: `AgentMonitorPane` currently has no reference to `ConductorApp._cwd`.
   - Recommendation: Pass `state_path: Path` to `AgentMonitorPane.__init__`, defaulting to `None`. `ConductorApp.compose()` passes `state_path=Path(self._cwd) / ".conductor" / "state.json"`. If None, `on_mount` skips the worker (placeholder behavior preserved for tests that don't provide a path).

3. **Phase 31 audit item (stdout bypass)**
   - What we know: STATE.md flags "Claude Agent SDK subprocess may write to inherited terminal stdout, bypassing Textual renderer — audit with test delegation run in Phase 35."
   - What's unclear: Whether SDK subprocess writes actually corrupt the TUI in practice.
   - Recommendation: Include a test delegation run as part of Phase 35 acceptance criteria. If stdout pollution occurs, the fix is to redirect subprocess stdout in `DelegationManager.handle_delegate`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 + Textual run_test() |
| Config file | `packages/conductor-core/pyproject.toml` — `asyncio_mode = "auto"` |
| Quick run command | `cd packages/conductor-core && python -m pytest tests/test_tui_agent_monitor.py -x` |
| Full suite command | `cd packages/conductor-core && python -m pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGNT-01 | `AgentPanel` (Collapsible) appears in pane for WORKING agent | unit | `pytest tests/test_tui_agent_monitor.py::test_agent_panel_appears_for_working_agent -x` | Wave 0 |
| AGNT-01 | Panel shows agent name, task title, status in title | unit | `pytest tests/test_tui_agent_monitor.py::test_agent_panel_shows_name_task_status -x` | Wave 0 |
| AGNT-02 | `AgentStateUpdated` message triggers panel mount | unit | `pytest tests/test_tui_agent_monitor.py::test_state_update_message_mounts_panel -x` | Wave 0 |
| AGNT-02 | Second update refreshes existing panel (not duplicate mount) | unit | `pytest tests/test_tui_agent_monitor.py::test_state_update_refreshes_existing_panel -x` | Wave 0 |
| AGNT-03 | Expanding panel reveals task info and activity content | unit | `pytest tests/test_tui_agent_monitor.py::test_expanded_panel_shows_activity -x` | Wave 0 |
| AGNT-04 | DONE agent's panel is removed (or archived) from pane | unit | `pytest tests/test_tui_agent_monitor.py::test_completed_agent_panel_removed -x` | Wave 0 |
| AGNT-04 | Empty pane shows "No agents active" when all done | unit | `pytest tests/test_tui_agent_monitor.py::test_empty_state_shows_no_agents -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && python -m pytest tests/test_tui_agent_monitor.py -x`
- **Per wave merge:** `cd packages/conductor-core && python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui_agent_monitor.py` — covers AGNT-01, AGNT-02, AGNT-03, AGNT-04 (all 7 tests above)

*(No framework install needed — pytest + pytest-asyncio + Textual run_test() already in place)*

## Sources

### Primary (HIGH confidence)
- `packages/conductor-core/src/conductor/dashboard/watcher.py` — awatch pattern, directory watching for inode-swap writes, asyncio.to_thread, debounce=200
- `packages/conductor-core/src/conductor/state/models.py` — ConductorState, AgentRecord, AgentStatus, Task, TaskStatus field names verified
- `packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py` — current placeholder; Phase 35 target
- `packages/conductor-core/src/conductor/tui/messages.py` — DelegationStarted, DelegationComplete, ToolActivity already defined
- Textual 8.1.1 installed source — `Collapsible.__init__` signature, reactive `collapsed`, `Toggled`/`Expanded`/`Collapsed` events, `Contents` container verified via `inspect.getsource`

### Secondary (MEDIUM confidence)
- `packages/conductor-core/src/conductor/cli/delegation.py` line 164 comment — explicit design note: "status display moved to Textual StateWatchWorker in Phase 35"
- `packages/conductor-core/src/conductor/orchestrator/monitor.py` — `StreamMonitor._tool_events` is a list of tool names collected during agent SDK session; not yet piped to TUI

### Tertiary (LOW confidence)
- Phase 31 audit item in STATE.md — SDK subprocess stdout bypass concern; unverified until runtime test delegation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libs verified as installed and APIs inspected from source
- Architecture patterns: HIGH — reuses proven dashboard watcher pattern + established @work pattern from app.py
- Pitfalls: HIGH — inode-swap issue is documented in watcher.py; remove() async issue verified from Textual source; tool activity gap is explicit finding from source read
- Tool activity (AGNT-03 full fidelity): MEDIUM — design decision required; multiple valid options identified

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (Textual 8.x is stable; watchfiles 1.x is stable)
