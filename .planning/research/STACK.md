# Stack Research

**Domain:** Textual TUI agent visibility — v2.2 milestone (Conductor)
**Researched:** 2026-03-12
**Confidence:** HIGH

---

## Existing Stack (Validated — Do Not Re-research)

| Technology | Version | Role |
|------------|---------|------|
| `textual` | `8.1.1` | TUI framework — App, Widget, CSS, workers, messages |
| `claude-agent-sdk` | `0.1.48` | SDK streaming, `ClaudeSDKClient`, typed message objects |
| `watchfiles` | `1.1.1` | `awatch()` for state.json directory watching |
| `pydantic v2` | `>=2.10` | `ConductorState`, `AgentRecord`, `Task` models |
| `asyncio` | stdlib | Event loop, `@work` coroutines, background tasks |

---

## What v2.2 Needs: Zero New Dependencies

All four v2.2 features are implementable using APIs already present in the installed stack. No `uv add` is needed.

The features map to two distinct data pipelines:

1. **SDK stream → transcript**: Intercept `AssistantMessage` (typed `ToolUseBlock`) and `StreamEvent` (raw event dict) from the existing `_stream_response` loop to detect `conductor_delegate` calls and label the orchestrator's cell.
2. **state.json → transcript**: Extend the existing `AgentStateUpdated` message pipeline (already wired from `watchfiles` → `AgentMonitorPane`) to also drive agent cells in `TranscriptPane`.

---

## Feature 1: Tool-Use Interception for Delegation Detection

### What's Already There

The existing `_stream_response` loop in `app.py` iterates `receive_response()` and already handles two message types:

- `StreamEvent` — checked for `content_block_delta` / `text_delta` → routed to `AssistantCell.append_token()`
- `ResultMessage` — checked for usage and session_id → routed to `StatusFooter`

### What's Missing

The loop does not handle `AssistantMessage`. When the SDK finishes a turn, it emits an `AssistantMessage` containing typed `ContentBlock` objects. A `ToolUseBlock` in that content signals that Claude used a tool.

### The Integration Point

`AssistantMessage` is already a parsed SDK type with strongly-typed content:

```python
from claude_agent_sdk import AssistantMessage
from claude_agent_sdk.types import ToolUseBlock

async for message in self._sdk_client.receive_response():
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock) and block.name == "conductor_delegate":
                task_desc = block.input.get("task", "")
                # Post DelegationStarted — already defined in messages.py
                self.post_message(DelegationStarted(task_description=task_desc))
```

`ToolUseBlock` has three fields: `id: str`, `name: str`, `input: dict[str, Any]`. The `conductor_delegate` tool always has `input["task"]` as a string. No parsing beyond `.input.get("task")` is needed.

**StreamEvent for tool_use_start**: The `StreamEvent.event` dict also carries partial tool data during streaming. The `content_block_start` event type with `content_block.type == "tool_use"` fires when a tool call begins streaming. This can be used to show an "orchestrator is delegating..." indicator before the full `AssistantMessage` arrives. The relevant dict path:

```python
event = message.event
if (event.get("type") == "content_block_start"
        and event.get("content_block", {}).get("type") == "tool_use"):
    tool_name = event["content_block"]["name"]
    # Show delegation pending indicator
```

**Which to use**: Use `AssistantMessage` (not `StreamEvent`) for reliable delegation detection — it fires after the tool input is fully assembled. Use `StreamEvent`'s `content_block_start` only if you need an early "delegating..." indicator during streaming.

### Orchestrator Status Labeling

The current `AssistantCell` hardcodes the label `"Assistant"` in `compose()`:

```python
yield Static("Assistant", classes="cell-label")
```

To show the orchestrator's current phase (e.g., "Orchestrator — planning", "Orchestrator — delegating"), `AssistantCell` needs a `label` constructor parameter. The pattern:

```python
class AssistantCell(Widget):
    def __init__(self, text: str | None = None, label: str = "Assistant") -> None:
        super().__init__()
        self._label = label
        ...

    def compose(self) -> ComposeResult:
        yield Static(self._label, classes="cell-label")
        ...

    def update_label(self, label: str) -> None:
        """Update the cell label text after mount (e.g., 'Orchestrator — delegating')."""
        try:
            self.query_one(".cell-label", Static).update(label)
        except Exception:
            pass
```

`TranscriptPane.add_assistant_streaming()` gains an optional `label` parameter passed through to `AssistantCell`.

---

## Feature 2: Per-Agent Labeled Cells in Transcript

### What's Already There

`AgentMonitorPane` already receives `AgentStateUpdated(state: ConductorState)` messages via the `watchfiles` watcher. `AgentRecord` has `id`, `name`, `role`, `current_task_id`, `status`. The `AgentStatus` enum uses `WORKING` and `WAITING` as active states.

### What's Missing

`TranscriptPane` does not currently receive or handle `AgentStateUpdated`. The `AgentMonitorPane` already handles agent panel lifecycle (mount/update/remove) based on state diffs. The transcript needs a parallel stream: when an agent transitions to `WORKING`, mount an `AgentCell` with that agent's name and role; when it transitions to `DONE`, finalize the cell.

### The New Widget: AgentCell

`AgentCell` is a variant of `AssistantCell` — same streaming lifecycle (`start_streaming`, `append_token`, `finalize`) but with a labeled header showing agent name and role:

```python
class AgentCell(Widget):
    """A labeled cell for a sub-agent's output stream in the transcript."""

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
    AgentCell .cell-role {
        color: $text-muted;
        text-style: italic;
    }
    """

    def __init__(self, agent_id: str, agent_name: str, agent_role: str) -> None:
        super().__init__(id=f"agent-cell-{agent_id}")
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._agent_role = agent_role
        self._is_streaming: bool = True
        self._stream = None
        self._markdown = None
```

**Why a separate class rather than a parameter on `AssistantCell`**: `AgentCell` has a different lifecycle — it is driven by state.json changes, not by the SDK stream, and it needs a stable DOM `id` for later lookup. Keeping it separate avoids muddying `AssistantCell`'s text-driven streaming contract.

### State-to-Cell Correlation

`TranscriptPane` needs to track active agent cells by `agent_id`. A `dict[str, AgentCell]` keyed on `agent_id` is sufficient:

```python
class TranscriptPane(VerticalScroll):
    def __init__(self, ...) -> None:
        ...
        self._agent_cells: dict[str, AgentCell] = {}
```

When `AgentStateUpdated` arrives at `TranscriptPane`:

1. For each agent newly in `WORKING` state (not yet in `_agent_cells`): mount a new `AgentCell` and call `start_streaming()`.
2. For each agent transitioning from `WORKING` to `DONE`/`IDLE`: call `finalize()` on the existing cell and remove it from `_agent_cells`.
3. For agents remaining in `WORKING`: optionally update the task title in the cell header (low priority for MVP).

**Routing `AgentStateUpdated` to `TranscriptPane`**: The `watchfiles` watcher lives in `AgentMonitorPane`, which posts `AgentStateUpdated` to itself. Since Textual message propagation bubbles up the DOM, `TranscriptPane` cannot receive messages posted by a sibling widget. Two options:

- **Preferred**: Have `ConductorApp` handle `on_agent_state_updated` and forward to `TranscriptPane` explicitly:

  ```python
  async def on_agent_state_updated(self, event: AgentStateUpdated) -> None:
      pane = self.query_one(TranscriptPane)
      pane.post_message(event)   # re-post to the pane directly
  ```

- **Alternative**: Move the `watchfiles` watcher from `AgentMonitorPane` to `ConductorApp` and broadcast `AgentStateUpdated` to both panes. This is cleaner architecturally but requires moving existing code.

For minimum diff, use the forwarding approach in `ConductorApp`.

---

## Feature 3: Orchestrator Status Indicator

### What's Already There

`DelegationStarted` and `DelegationComplete` messages are already defined in `messages.py` but not yet posted or handled anywhere in the TUI path.

`DelegationManager.handle_delegate()` is the call site — it runs inside the SDK's `conductor_delegate` MCP tool handler. When delegation starts, `handle_delegate()` runs `orchestrator.run(task)`. When it completes, it returns. The TUI can intercept the delegation lifecycle by:

1. Posting `DelegationStarted` from the `AssistantMessage` handler in `_stream_response` (when `ToolUseBlock.name == "conductor_delegate"` is detected).
2. Posting `DelegationComplete` from `_stream_response` when the tool result comes back (a `UserMessage` with `tool_use_result` and the matching `tool_use_id`).

### StatusFooter vs. Transcript

The orchestrator status indicator belongs in the **transcript cell label**, not the `StatusFooter`. The `StatusFooter` already shows model/tokens/mode — adding "delegating" there creates visual ambiguity. Instead:

- When `conductor_delegate` tool call is detected: update the active `AssistantCell`'s label from `"Orchestrator"` to `"Orchestrator — delegating"` via `cell.update_label()`.
- When delegation completes (tool result received): update label back to `"Orchestrator — done"` or finalize the cell.

This requires no new message types — it's handled inline in `_stream_response`.

---

## Feature 4: state.json Agent Records → Transcript Cell Lifecycle

### What Already Works

The `watchfiles` → `AgentMonitorPane` pipeline already reads `ConductorState`, diffs against current panels, and mounts/updates/removes `AgentPanel` widgets. The diff logic is sound:

```python
active = {a.id: a for a in state.agents
          if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)}
```

### Reuse Pattern

`TranscriptPane.on_agent_state_updated()` can follow the exact same diff pattern:

```python
async def on_agent_state_updated(self, event: AgentStateUpdated) -> None:
    state = event.state
    active = {a.id: a for a in state.agents
              if a.status in (AgentStatus.WORKING, AgentStatus.WAITING)}

    # Finalize cells for completed agents
    for agent_id in list(self._agent_cells):
        if agent_id not in active:
            cell = self._agent_cells.pop(agent_id)
            await cell.finalize()

    # Mount new cells for newly active agents
    for agent_id, agent in active.items():
        if agent_id not in self._agent_cells:
            cell = AgentCell(agent_id, agent.name, agent.role)
            self._agent_cells[agent_id] = cell
            await self.mount(cell)
            await cell.start_streaming()
```

`AgentCell` content comes from state.json — the agent's current task description is available via `tasks` cross-reference. For MVP, showing agent name + role in the header is sufficient; task title can be added in a follow-on.

---

## New Message Types Needed

The existing `messages.py` already has `DelegationStarted` and `DelegationComplete`. One new message type is useful:

```python
class OrchestratorStatusChanged(Message):
    """Orchestrator phase changed (planning, delegating, reviewing, done)."""

    def __init__(self, phase: str) -> None:
        self.phase = phase   # e.g. "planning", "delegating", "reviewing", "done"
        super().__init__()
```

This is optional for MVP — the label update approach handles the common case inline.

---

## Summary: Integration Points

| Feature | SDK / Library API | Integration Point | Change Required |
|---------|------------------|-------------------|-----------------|
| Detect delegation | `AssistantMessage` + `ToolUseBlock` | `_stream_response` loop in `app.py` | Add `isinstance(message, AssistantMessage)` branch |
| Early delegation indicator | `StreamEvent.event["content_block_start"]` | `_stream_response` loop | Add check for `content_block.type == "tool_use"` |
| Labeled orchestrator cell | `AssistantCell(label=...)` + `update_label()` | `TranscriptPane`, `AssistantCell` | Add `label` param and `update_label()` method |
| Agent cells in transcript | `AgentStateUpdated` message | `TranscriptPane.on_agent_state_updated()` | Add handler + `AgentCell` widget + `_agent_cells` dict |
| Route state updates to transcript | Textual `post_message()` | `ConductorApp.on_agent_state_updated()` | Add forwarding handler in app |
| Agent cell lifecycle | `AgentCell.start_streaming()` / `finalize()` | `TranscriptPane` diff logic | New `AgentCell` widget (modeled on `AssistantCell`) |

---

## Installation

No new dependencies. All APIs are in the installed stack.

```bash
# Verify — no uv add needed
uv run python -c "import textual; print(textual.__version__)"      # 8.1.1
uv run python -c "import claude_agent_sdk; print(claude_agent_sdk.__version__)"  # 0.1.48
uv run python -c "import watchfiles; print(watchfiles.__version__)"  # 1.1.1
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `AssistantMessage` for delegation detection | `StreamEvent` `content_block_start` with `tool_use` block | Use `StreamEvent` only for an early "delegating..." banner shown before the tool input is fully assembled — `AssistantMessage` is reliable and fully parsed |
| Forward `AgentStateUpdated` from app to `TranscriptPane` | Move watcher to `ConductorApp` and broadcast | Moving the watcher reduces coupling but requires restructuring existing working code — deferring to a future refactor is lower risk |
| `AgentCell` as a new widget class | Add `mode` parameter to `AssistantCell` | A separate class avoids conditional branching in `AssistantCell` and keeps its streaming contract clean — worth the small duplication |
| Inline label update via `update_label()` | New `OrchestratorStatusChanged` message + app-level handler | The message approach is more testable but adds indirection for a single-cell update — inline is simpler for MVP |

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Polling `DelegationManager.is_delegating` in a timer | Race-prone and burns CPU — the `AssistantMessage` event is synchronous in the SDK stream | Handle `AssistantMessage` with `ToolUseBlock` in `_stream_response` |
| New file watcher for per-agent transcript files | State.json already captures agent status transitions — another watcher adds complexity and sync issues | Extend `AgentStateUpdated` pipeline to `TranscriptPane` |
| Separate asyncio queue for agent-to-transcript routing | Already have a clean Textual message bus with `post_message()` — an additional queue adds overhead | Textual message bus via `post_message()` and `on_*` handlers |
| `anyio` or `trio` primitives for event coordination | The event loop is owned by Textual's `asyncio` loop — mixing runtimes is not viable | `asyncio.Queue` (already in use for escalations) if async queuing is needed |
| `rich.console` output in agent cells | ANSI/Rich output corrupts Textual's compositor — this was explicitly removed in Phase 31 | `Markdown` widget or `Static` widget within `AgentCell` |

---

## Stack Patterns by Variant

**If agent activity log is available (future: per-agent JSONL file):**
- Parse the agent's transcript file to populate `AgentCell` content
- `AssistantMessage` blocks from the agent's session give rich content
- Current MVP: show task title from state.json — no transcript file needed yet

**If multiple agents are active simultaneously:**
- Each agent gets its own `AgentCell` in transcript, mounted in the order state.json reports WORKING status
- `_agent_cells: dict[str, AgentCell]` handles N-agent concurrency cleanly
- Scroll behavior: `scroll_end(animate=False)` when a new `AgentCell` is mounted (same as `add_assistant_streaming()`)

**If delegation is deeply nested (orchestrator delegates to sub-orchestrator):**
- `AssistantMessage.parent_tool_use_id` is None for the top-level orchestrator
- Nested tool use will have a non-None `parent_tool_use_id` — can be used to indent or nest agent cells
- For MVP, treat all active agents as peers in the transcript

---

## Version Compatibility

| Package | Version | Notes |
|---------|---------|-------|
| `textual` | `8.1.1` | `Widget.mount()`, `VerticalScroll`, `post_message()`, `on_*` handlers all confirmed working |
| `claude-agent-sdk` | `0.1.48` | `AssistantMessage`, `ToolUseBlock`, `StreamEvent` all confirmed in `types.py` and `message_parser.py` |
| `watchfiles` | `1.1.1` | `awatch()` with `debounce=200` confirmed working in `AgentMonitorPane._watch_state()` |
| `pydantic v2` | installed | `AgentRecord.name`, `.role`, `.status`, `.id` all present in `models.py` |

---

## Sources

- `.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py` — `AssistantMessage`, `ToolUseBlock` (fields: `id`, `name`, `input`), `StreamEvent` (field: `event: dict[str, Any]`) confirmed
- `.venv/lib/python3.13/site-packages/claude_agent_sdk/_internal/message_parser.py` — `case "assistant"` parses `tool_use` blocks into `ToolUseBlock`; `case "stream_event"` confirms `event` dict is raw Anthropic API payload
- `packages/conductor-core/src/conductor/tui/app.py` — `_stream_response` loop structure confirmed; existing `isinstance(message, StreamEvent)` and `isinstance(message, ResultMessage)` branches; `AssistantMessage` not yet handled
- `packages/conductor-core/src/conductor/tui/widgets/transcript.py` — `AssistantCell` constructor and `compose()` confirmed; hardcoded `"Assistant"` label; `_is_streaming`, `_stream`, `start_streaming()`, `append_token()`, `finalize()` all present
- `packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py` — `_watch_state()` → `AgentStateUpdated` pipeline confirmed; diff logic against `AgentStatus.WORKING`/`WAITING` confirmed
- `packages/conductor-core/src/conductor/tui/messages.py` — `DelegationStarted`, `DelegationComplete`, `AgentStateUpdated` all already defined
- `packages/conductor-core/src/conductor/state/models.py` — `AgentRecord` fields confirmed: `id`, `name`, `role`, `current_task_id`, `status`; `AgentStatus.WORKING`, `WAITING`, `DONE`, `IDLE` confirmed

---
*Stack research for: Conductor v2.2 — Agent Visibility (labeled agent cells, orchestrator status, tool-use interception, state.json correlation)*
*Researched: 2026-03-12*
