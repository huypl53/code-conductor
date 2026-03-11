# Architecture Research

**Domain:** Agent visibility in Textual TUI — labeled per-agent output streams integrated into existing streaming transcript
**Researched:** 2026-03-12
**Confidence:** HIGH (full source code inspection, SDK type definitions verified)

---

## Current System Architecture

### Component Map (Before v2.2)

```
ConductorApp (Textual App)
├── _ensure_sdk_connected()          # Lazy SDK init, creates DelegationManager
├── _stream_response(@work)          # SDK streaming worker — ONE active at a time
│   └── async for message in sdk.receive_response()
│       ├── StreamEvent → content_block_delta → text_delta → AssistantCell.append_token()
│       └── ResultMessage → TokensUpdated → StatusFooter
│       (AssistantMessage with ToolUseBlock: NOT YET HANDLED)
├── _watch_escalations(@work)        # Modal escalation bridge via DelegationManager queues
├── compose()
│   ├── TranscriptPane               # Scrollable VerticalScroll — conversation history
│   │   ├── UserCell(text)           # Immutable user turn
│   │   └── AssistantCell(text?)     # Static or streaming assistant turn
│   ├── AgentMonitorPane             # Right panel — state.json watcher
│   │   └── _watch_state(@work)      # watchfiles → AgentStateUpdated messages
│   │       └── on_agent_state_updated() → mounts/updates/removes AgentPanel widgets
│   ├── CommandInput
│   └── StatusFooter
└── DelegationManager
    └── handle_delegate()            # MCP tool handler
        └── Orchestrator.run()       # Runs INSIDE _stream_response (called by SDK tool invoke)
```

### Key Insight: Delegation Is Invisible to the Transcript

When the orchestrator calls `conductor_delegate`:

1. SDK emits `AssistantMessage` with `ToolUseBlock(name="conductor_delegate", input={"task": "..."})`.
2. SDK calls `DelegationManager.handle_delegate()` which runs `Orchestrator.run()` synchronously from the SDK's perspective. This entire sub-agent team execution happens inside the `receive_response()` async generator.
3. `_stream_response` only intercepts `StreamEvent` (partial tokens) and `ResultMessage` (final usage). The `AssistantMessage` carrying the tool_use block is currently silently dropped.
4. `AgentMonitorPane._watch_state` does detect agent activity via `state.json` — but nothing surfaces in `TranscriptPane`.

The gap: **TranscriptPane never learns that delegation happened.** It shows "Assistant" thinking, then a reply, with no indication that sub-agents ran.

---

## Integration Architecture for v2.2

### What Changes vs. What Is New

| Component | Status | Change Type |
|-----------|--------|-------------|
| `app.py._stream_response` | MODIFIED | Add `AssistantMessage` + `ToolUseBlock` interception; hold `OrchestratorStatusCell` reference |
| `TranscriptPane` | MODIFIED | Add `add_agent_cell()`, `add_orchestrator_status()`, `on_agent_state_updated()`, internal `_agent_cells` dict |
| `messages.py` | MODIFIED | Add `OrchestratorStatusChanged` message |
| `AgentCell` widget | NEW | Labeled cell in transcript showing agent name, role, task |
| `OrchestratorStatusCell` widget | NEW | Status-only cell for orchestrator planning/delegation phase |
| `AssistantCell` | UNCHANGED | Reused as-is |
| `AgentMonitorPane` | UNCHANGED | Already works; no changes needed |
| `DelegationManager` | UNCHANGED | Already exposes queues; no changes needed |
| `state/models.py` | UNCHANGED | `AgentRecord.name`, `AgentRecord.role`, `Task.title` are sufficient |

---

## Data Flow: SDK Stream to Agent Cell Creation

### Full Sequence

```
User types message
        │
        ▼
_stream_response(@work) starts
        │
        ├── [existing] StreamEvent: content_block_delta / text_delta
        │       └── AssistantCell.append_token(chunk)
        │
        ├── [NEW] AssistantMessage with ToolUseBlock(name="conductor_delegate")
        │       │   This fires BEFORE the SDK calls handle_delegate()
        │       └── task_desc = block.input["task"]
        │               │
        │               ▼
        │       post OrchestratorStatusChanged("Delegating: <task_desc>")
        │               │
        │               ▼
        │       ConductorApp.on_orchestrator_status_changed()
        │           → pane.add_orchestrator_status(text)
        │           → OrchestratorStatusCell mounted in TranscriptPane
        │           → self._active_orchestrator_status = cell
        │
        │   [SDK calls DelegationManager.handle_delegate() — blocks inside recv loop]
        │   [Orchestrator.run() runs sub-agent team — state.json changes during this]
        │           │
        │           ▼ (watchfiles detects parent dir change — ALREADY WORKING)
        │   AgentMonitorPane._watch_state(@work) posts AgentStateUpdated(state)
        │           │
        │           ├── [existing] AgentMonitorPane.on_agent_state_updated()
        │           │       └── Updates AgentPanel right-panel widgets (unchanged)
        │           │
        │           └── [NEW] TranscriptPane.on_agent_state_updated()
        │                   └── For new agents in state.agents (WORKING/WAITING):
        │                       → mount AgentCell(agent_id, name, role, task_title)
        │                       → store in self._agent_cells[agent_id]
        │                   └── For existing agents:
        │                       → cell.update_status(task_title, status)
        │                   └── For agents gone DONE/IDLE:
        │                       → cell.finalize()
        │                       → remove from self._agent_cells (cell stays mounted)
        │
        └── [existing] ResultMessage → StreamDone
                │
                └── [NEW] self._active_orchestrator_status.finalize()
                        └── OrchestratorStatusCell shows "Delegation complete"
```

### Agent Output Strategy

Sub-agent SDK streams are separate processes — they are not visible to the TUI's `receive_response()` loop. The TUI can only observe sub-agents through `state.json`.

**For v2.2:** Use `state.json` as the source of agent identity (name, role, task title, status). Agent cells show who is running and what they are doing, updated on each `AgentStateUpdated` event. This mirrors exactly what `AgentMonitorPane` already does — the transcript view is a timeline snapshot of the same data.

**Not in v2.2:** Live streaming of what each sub-agent is generating. That would require per-agent log tailing or dedicated output channels — a separate infrastructure investment.

---

## Component Design

### New: `AgentCell` Widget

**Location:** `packages/conductor-core/src/conductor/tui/widgets/transcript.py`

**Constructor:** `AgentCell(agent_id: str, agent_name: str, agent_role: str, task_title: str)`

**Visual:** Same border-left pattern as `AssistantCell` but with a distinct color (e.g., `$secondary` or `$warning`) and a two-line header showing `{agent_name} — {agent_role}` plus task title below.

**Methods:**
- `update_status(task_title: str, status: str)` — called on each `AgentStateUpdated` while agent is active
- `finalize()` — marks cell as done visually (e.g., "[DONE]" suffix on label), sets `_is_active = False`

**Lifecycle:** Mounted when agent first appears in `state.json` as WORKING/WAITING. Stays mounted permanently (transcript is history). `finalize()` called when agent leaves WORKING/WAITING.

**Pattern:** Mirrors `AssistantCell` but no streaming mode needed — content is state snapshots, not token streams.

### New: `OrchestratorStatusCell` Widget

**Location:** `packages/conductor-core/src/conductor/tui/widgets/transcript.py`

**Constructor:** `OrchestratorStatusCell(status_text: str)`

**Visual:** Distinct style from both `AssistantCell` and `AgentCell`. Suggests "system event" — e.g., `$primary` tint, different label like "Orchestrator".

**Methods:**
- `update(text: str)` — update displayed status
- `finalize()` — mark as complete ("Delegation complete" or similar)

**Lifecycle:** Created in `app.py._stream_response` when `conductor_delegate` ToolUseBlock detected. Finalized in `StreamDone` handler.

### Modified: `TranscriptPane`

**New state:** `self._agent_cells: dict[str, AgentCell] = {}` mapping `agent_id` to mounted cell.
**New state:** (optional) `self._orchestrator_status_cell: OrchestratorStatusCell | None = None`

**New methods:**
- `async add_agent_cell(agent_id, agent_name, agent_role, task_title) -> AgentCell`
- `async add_orchestrator_status(text) -> OrchestratorStatusCell`
- `async on_agent_state_updated(event: AgentStateUpdated)` — diff logic (new/update/finalize)

**Diff logic in `on_agent_state_updated`:**

```python
async def on_agent_state_updated(self, event: AgentStateUpdated) -> None:
    from conductor.state.models import AgentStatus
    state = event.state

    active = {
        a.id: a
        for a in state.agents
        if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)
    }
    tasks = {t.assigned_agent: t for t in state.tasks if t.assigned_agent}

    for agent_id, agent in active.items():
        task = tasks.get(agent_id)
        task_title = task.title if task else "(unknown task)"
        if agent_id not in self._agent_cells:
            cell = await self.add_agent_cell(
                agent_id, agent.name, agent.role, task_title
            )
            self._agent_cells[agent_id] = cell
        else:
            self._agent_cells[agent_id].update_status(task_title, str(agent.status))

    for agent_id in list(self._agent_cells):
        if agent_id not in active:
            self._agent_cells[agent_id].finalize()
            del self._agent_cells[agent_id]
```

### New Message: `OrchestratorStatusChanged`

**Location:** `packages/conductor-core/src/conductor/tui/messages.py`

```python
class OrchestratorStatusChanged(Message):
    """Orchestrator entered planning/delegation phase — create status cell."""
    def __init__(self, status_text: str, done: bool = False) -> None:
        self.status_text = status_text
        self.done = done
        super().__init__()
```

Note: `DelegationStarted` and `DelegationComplete` already exist in `messages.py` but are unused. These could be repurposed instead of adding `OrchestratorStatusChanged` — verify usage before adding a duplicate.

---

## Integration Points

### Integration Point 1: `AssistantMessage` Interception (app.py)

**Where:** `_stream_response`, inside `async for message in self._sdk_client.receive_response()`.

**Current state:** Only `StreamEvent` and `ResultMessage` are handled. `AssistantMessage` is silently dropped.

**Change:** Add `elif isinstance(message, AssistantMessage):` branch.

The SDK emits `AssistantMessage` with `content: list[ContentBlock]`. When the orchestrator invokes `conductor_delegate`, one of those blocks will be `ToolUseBlock(name="conductor_delegate", input={"task": "..."})`. This fires **before** `handle_delegate()` is called, giving the TUI a chance to show status before the delegation loop starts.

```python
from claude_agent_sdk import AssistantMessage, ResultMessage
from claude_agent_sdk.types import StreamEvent, ToolUseBlock

elif isinstance(message, AssistantMessage):
    for block in message.content:
        if isinstance(block, ToolUseBlock) and block.name == "conductor_delegate":
            task_desc = block.input.get("task", "Delegating task...")
            pane = self.query_one(TranscriptPane)
            self._active_orchestrator_status = await pane.add_orchestrator_status(
                f"Delegating: {task_desc[:80]}"
            )
```

**File:** `packages/conductor-core/src/conductor/tui/app.py`
**Risk:** LOW — adding a new `elif` branch. The existing `StreamEvent` and `ResultMessage` branches are unaffected.

### Integration Point 2: `AgentStateUpdated` Subscription (transcript.py)

**Where:** `TranscriptPane` class — new `on_agent_state_updated` handler.

**Current state:** `AgentStateUpdated` is only handled by `AgentMonitorPane`. Textual's message bus delivers to all subscribers — `TranscriptPane` just needs to declare the handler.

**Change:** `TranscriptPane.on_agent_state_updated()` with diff logic above. Requires `_agent_cells` dict initialized in `__init__`.

**File:** `packages/conductor-core/src/conductor/tui/widgets/transcript.py`
**Risk:** LOW — same message, same pattern as `AgentMonitorPane.on_agent_state_updated`.

### Integration Point 3: `OrchestratorStatusCell` Finalization (app.py)

**Where:** `ConductorApp.on_stream_done()` or the `finally` block of `_stream_response`.

**Change:** `self._active_orchestrator_status` reference held on `ConductorApp`. When `StreamDone` fires, call `finalize()`.

```python
# In ConductorApp.__init__:
self._active_orchestrator_status: Any | None = None  # OrchestratorStatusCell | None

# In _stream_response finally block:
if self._active_orchestrator_status is not None:
    try:
        await self._active_orchestrator_status.finalize()
    except Exception:
        pass
    self._active_orchestrator_status = None
```

**File:** `packages/conductor-core/src/conductor/tui/app.py`
**Risk:** LOW — mirroring the existing `self._active_cell` pattern.

---

## Component Boundary Responsibilities

| Component | Owns | Does NOT Own |
|-----------|------|--------------|
| `app.py._stream_response` | Detecting `conductor_delegate` ToolUseBlock; creating `OrchestratorStatusCell`; finalizing it on `StreamDone` | Agent cell lifecycle; state.json watching |
| `TranscriptPane` | Mounting and updating `AgentCell` widgets on `AgentStateUpdated`; cell reference tracking via `_agent_cells` dict | Watching state.json (AgentMonitorPane owns the worker) |
| `AgentMonitorPane` | Right-panel `AgentPanel` widgets; `_watch_state(@work)` worker posting `AgentStateUpdated` | Posting to TranscriptPane; creating transcript cells |
| `DelegationManager` | Running orchestrator; escalation queues | Any TUI cell lifecycle |
| `state.json` | Source of truth: agent identity, role, status, task assignment | Sub-agent output content |

---

## Architectural Patterns

### Pattern 1: `AgentStateUpdated` Fan-Out (Shared Message, Independent Handlers)

**What:** Both `AgentMonitorPane` and `TranscriptPane` handle the same `AgentStateUpdated` message independently. Each maintains its own view of the same underlying state.

**Why:** Textual's message bus delivers to all subscribers automatically. Adding a handler in `TranscriptPane` does not require changes to `AgentMonitorPane`. The widgets are decoupled.

**Trade-off:** Both widgets run the same O(n) diff on each state change. At the scale of a single delegation (typically 2-10 agents), this is negligible.

### Pattern 2: Cell Reference Tracking

**What:** `TranscriptPane._agent_cells: dict[str, AgentCell]` maps `agent_id → AgentCell`. Enables idempotent updates — `AgentStateUpdated` fires multiple times per agent lifetime as tasks progress.

**Why:** Without tracking, every state change would mount a duplicate cell. The dict is the deduplication mechanism.

**Trade-off:** Small memory overhead per agent. Dict is cleared when agent finalizes (cell stays mounted in scroll history for the session).

### Pattern 3: Finalized Cells Stay Mounted

**What:** When an agent reaches DONE/IDLE, `AgentCell.finalize()` updates the visual state (e.g., status label changes to "DONE"), but the cell is never removed from `TranscriptPane`.

**Why:** `TranscriptPane` is a conversation history. Removing cells would discard the timeline record of what happened. Users scrolling up should see which agents ran.

**Trade-off:** Memory grows with delegation history. Acceptable for a single-session TUI. If sessions become very long, cells could be collapsed rather than removed.

### Pattern 4: Orchestrator Status as Ephemeral Cell

**What:** `OrchestratorStatusCell` is created at delegation start and finalized at `StreamDone`. It represents a transient system event (not a persistent agent record).

**Why:** The orchestrator status is different from agent cells — it marks the moment of delegation decision, not an ongoing agent's work. It should be visually distinguishable.

**Trade-off:** One more reference to track on `ConductorApp`. The `self._active_orchestrator_status` pattern is identical to `self._active_cell`.

---

## Anti-Patterns

### Anti-Pattern 1: Routing Agent Output Through SDK Stream Events

**What people do:** Try to capture each sub-agent's SDK tokens and stream them directly into per-agent transcript cells.

**Why it's wrong:** Sub-agents run inside `DelegationManager.handle_delegate()`, which is called by the SDK tool invocation mechanism — not directly observable by the TUI's `receive_response()` loop. The TUI only sees the orchestrator's SDK stream. Sub-agent streams are entirely separate processes.

**Do this instead:** Use `state.json` as the data source for agent identity and status. Show task title and status snapshot. This is the established pattern in `AgentMonitorPane`.

### Anti-Pattern 2: `AgentMonitorPane` Posts to `TranscriptPane`

**What people do:** Make `AgentMonitorPane.on_agent_state_updated()` post a new `AgentCellRequested` message for `TranscriptPane` to handle.

**Why it's wrong:** Creates sibling coupling. `AgentMonitorPane` should not know `TranscriptPane` exists. Violates Textual's model where widgets post to self/parent/app — not to sibling widgets.

**Do this instead:** Both panes subscribe to `AgentStateUpdated` independently. The message bus handles fan-out. No coordination layer needed.

### Anti-Pattern 3: Widget Mutations from Background Tasks

**What people do:** Call `await transcript_pane.mount(AgentCell(...))` directly from `asyncio.create_task()` or a non-Textual background task.

**Why it's wrong:** Textual widget mutations must happen on the Textual event loop (thread). Direct calls from arbitrary asyncio tasks can corrupt the DOM.

**Do this instead:** Use `post_message()` from background tasks. All `mount()` calls happen in message handlers on the Textual event loop. The existing `AgentMonitorPane` pattern (`_watch_state` posts `AgentStateUpdated`, handler does `await self.mount(AgentPanel(...))`) is the correct model.

### Anti-Pattern 4: Handling `conductor_delegate` in `StreamEvent` Events

**What people do:** Try to detect delegation by looking for `tool_use` type in `StreamEvent.event["type"] == "content_block_start"` with partial JSON accumulation.

**Why it's wrong:** The `AssistantMessage` with a complete `ToolUseBlock` is delivered by the SDK after the full tool call is assembled. It carries the complete `input` dict. `StreamEvent` delivers raw Anthropic API stream chunks — `content_block_start` for tool_use would only have the tool name, not the input. The `AssistantMessage` is cleaner, complete, and already the pattern used in `cli/chat.py` for ToolUseBlock handling.

**Do this instead:** Handle `AssistantMessage` in `_stream_response` and check `isinstance(block, ToolUseBlock)`. The SDK assembles the complete message and delivers it.

---

## Build Order

Dependencies flow downward — each step can be tested independently before the next begins.

| Step | Component | What to Build | Dependency |
|------|-----------|--------------|------------|
| 1 | `messages.py` | `OrchestratorStatusChanged` message (or reuse `DelegationStarted`) | None |
| 2 | `transcript.py` | `AgentCell` widget (constructor, `update_status`, `finalize`, CSS) | None |
| 3 | `transcript.py` | `OrchestratorStatusCell` widget (constructor, `update`, `finalize`, CSS) | None |
| 4 | `transcript.py` | `TranscriptPane` extensions: `add_agent_cell()`, `add_orchestrator_status()`, `on_agent_state_updated()`, `_agent_cells` dict | Steps 2, 3 |
| 5 | `app.py` | `AssistantMessage`/`ToolUseBlock` interception in `_stream_response`; `_active_orchestrator_status` reference; finalization in `StreamDone` | Steps 1, 3, 4 |
| 6 | `conductor.tcss` | CSS for new cell types (color differentiation) | Steps 2, 3 |

Steps 1-3 are independent and can be built in parallel. Step 4 depends on 2 and 3. Step 5 depends on 1, 3, 4. Step 6 is parallel with 5.

---

## Data Flow Diagrams

### Flow 1: Delegation Detection to Orchestrator Status Cell

```
_stream_response (Textual @work, orchestrator SDK stream)
    │
    │ SDK recv: AssistantMessage
    │   content: [ToolUseBlock(name="conductor_delegate", input={"task": "Build auth..."})]
    │
    ├── isinstance(block, ToolUseBlock) and block.name == "conductor_delegate"
    │       → pane.add_orchestrator_status("Delegating: Build auth...")
    │       → OrchestratorStatusCell mounted in TranscriptPane
    │       → self._active_orchestrator_status = cell
    │
    │ SDK calls DelegationManager.handle_delegate({"task": "Build auth..."})
    │   [synchronous from SDK's perspective — blocks receive_response() loop]
    │   → Orchestrator.run() → sub-agents write state.json
    │
    │ SDK recv: ResultMessage → StreamDone
    │       → cell.finalize() → "Delegation complete"
    │       → self._active_orchestrator_status = None
```

### Flow 2: Agent Activation to Agent Cell in Transcript

```
Orchestrator.run() → writes state.json (agents transition to WORKING)
        │
        ▼ (watchfiles detects .conductor/ dir change — 200ms debounce)
AgentMonitorPane._watch_state(@work)
        │ reads new state via StateManager
        └── self.post_message(AgentStateUpdated(new_state))
                │
                │ Textual message bus delivers to ALL subscribers
                │
                ├── AgentMonitorPane.on_agent_state_updated()  [EXISTING]
                │       └── Mounts/updates/removes AgentPanel in right panel
                │
                └── TranscriptPane.on_agent_state_updated()   [NEW]
                        │
                        ├── agent "agent-001" (WORKING) not in _agent_cells:
                        │       → mount AgentCell("agent-001", "Alice", "Frontend Dev", "Build login form")
                        │       → _agent_cells["agent-001"] = cell
                        │
                        └── agent "agent-002" (WORKING) not in _agent_cells:
                                → mount AgentCell("agent-002", "Bob", "Backend Dev", "Add JWT endpoints")
                                → _agent_cells["agent-002"] = cell
```

### Flow 3: Agent Completion to Cell Finalization

```
Orchestrator marks agent DONE → writes state.json
        │
        ▼
AgentStateUpdated fires (next watchfiles cycle)
        │
        └── TranscriptPane.on_agent_state_updated()
                │
                └── "agent-001" not in active (status DONE):
                        → _agent_cells["agent-001"].finalize()
                        → del _agent_cells["agent-001"]
                        → AgentCell stays mounted in scroll history
```

---

## Integration Points Table

| Boundary | Communication Pattern | File | Risk |
|----------|-----------------------|------|------|
| `_stream_response` detects `conductor_delegate` | `isinstance(message, AssistantMessage)` + `isinstance(block, ToolUseBlock)` | `app.py` | LOW |
| `app.py` creates `OrchestratorStatusCell` | `await pane.add_orchestrator_status(text)` — direct async call, same event loop | `app.py` + `transcript.py` | LOW |
| `AgentMonitorPane._watch_state` → `TranscriptPane` | `AgentStateUpdated` message bus fan-out — no coupling between widgets | `agent_monitor.py` posts, `transcript.py` subscribes | LOW |
| `app.py` finalizes `OrchestratorStatusCell` | `self._active_orchestrator_status.finalize()` in `_stream_response` finally block | `app.py` | LOW |
| `TranscriptPane` updates/finalizes `AgentCell` | Direct method calls on cell references in `_agent_cells` dict | `transcript.py` | LOW |

---

## Sources

- Direct source inspection: `app.py`, `transcript.py`, `agent_monitor.py`, `messages.py`, `delegation.py`, `models.py` — HIGH confidence (primary source)
- SDK type definitions: `.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py` — HIGH confidence (installed SDK)
- `AssistantMessage` + `ToolUseBlock` handling pattern: `cli/chat.py` lines 424-450 — HIGH confidence (existing codebase pattern)
- `AgentStateUpdated` fan-out pattern: Textual message bus delivers to all `on_<message>` handlers in the widget tree — HIGH confidence (Textual documentation)
- `watchfiles` parent-directory watch pattern: `agent_monitor.py` comment — HIGH confidence (already proven in production, see PROJECT.md key decisions)

---

*Architecture research for: Conductor v2.2 — Agent Visibility TUI Integration*
*Researched: 2026-03-12*
