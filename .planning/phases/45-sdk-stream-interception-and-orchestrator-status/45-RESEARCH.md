# Phase 45: SDK Stream Interception and Orchestrator Status — Research

**Researched:** 2026-03-12
**Domain:** Textual TUI / Claude SDK streaming / tool-use event interception
**Confidence:** HIGH

## Summary

Phase 45 wires the existing SDK `_stream_response` worker in `app.py` to intercept
`conductor_delegate` tool-use events. Two observable outcomes must appear in the
transcript: (1) the active `AssistantCell`'s label changes from "Assistant" to
"Orchestrator — delegating", and (2) an `OrchestratorStatusCell` is mounted with
the task description extracted from the accumulated `input_json_delta` stream.

The infrastructure for this phase is already built. `AssistantCell`, `OrchestratorStatusCell`,
`TranscriptPane`, and all message types exist. The SDK's `StreamEvent` carries raw
Anthropic API server-sent events as `event: dict[str, Any]`. The stream loop must
track `content_block_start` / `content_block_delta` / `content_block_stop` events
to accumulate tool-use input JSON, then fire on `content_block_stop` for the
`conductor_delegate` block.

The primary risk is the `input_json_delta` accumulation: `content_block_start.input`
is always `{}` in real streaming — input arrives only as `input_json_delta` deltas and
must be concatenated by `content_block_index`, then parsed with `json.loads()` on
`content_block_stop`. Widget creation must use `post_message` (not `await mount`)
because the stream worker is a Textual `@work` coroutine and blocking it blocks SDK
event delivery.

**Primary recommendation:** Extend `_stream_response` with a minimal state machine
tracking `content_block_index` → partial JSON string, then parse on stop; use
`post_message` to fire a new `DelegationStarted`-extended message that `TranscriptPane`
handles for cell creation.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STRM-01 | SDK stream tool_use events for conductor_delegate are intercepted and trigger agent visibility updates | Stream loop pattern in `_stream_response`; `content_block_start` with `type=tool_use` identifies the block; handled by extending the existing `isinstance(message, StreamEvent)` branch |
| STRM-02 | Tool-use input accumulated from input_json_delta events before creating cells | `input_json_delta` accumulation by `content_block_index`; `json.loads()` on `content_block_stop` with guard for the identified conductor_delegate block index |
| ORCH-01 | Orchestrator label changes from "Assistant" to "Orchestrator — delegating" | `AssistantCell` label is a `Static("Assistant", classes="cell-label")` — needs mutation via `query_one(".cell-label").update(...)` after tool-use start detected |
| ORCH-02 | Delegation start shows which agents were spawned and what tasks they received | `OrchestratorStatusCell` mounted via `TranscriptPane` with task description from parsed input; agent identity from `DelegationStarted` message (extended) or `TaskStartedMessage.description` |
</phase_requirements>

## Standard Stack

### Core (already installed — no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude_agent_sdk` | installed | `StreamEvent`, `AssistantMessage`, `ToolUseBlock` | Project decision: zero new deps |
| `textual` | installed | `@work`, `post_message`, widget mutations | All TUI widgets built on it |
| `json` | stdlib | `json.loads()` for accumulated input_json_delta | No third-party parser needed |

### No New Installations Required

## Architecture Patterns

### Recommended Project Structure (files touched)

```
packages/conductor-core/src/conductor/tui/
├── app.py               # extend _stream_response worker
├── messages.py          # extend DelegationStarted (add agent_count / task_description fields)
└── widgets/
    └── transcript.py    # add on_delegation_started handler to TranscriptPane
packages/conductor-core/tests/
└── test_tui_stream_interception.py  # new test file (TDD pattern)
```

### Pattern 1: tool_use Detection in Stream Events

The SDK's `StreamEvent.event` dict carries raw Anthropic API SSE events. The relevant
event sequence for a single tool_use block is:

```
content_block_start  → {"type": "content_block_start", "index": N, "content_block": {"type": "tool_use", "id": "...", "name": "conductor_delegate", "input": {}}}
content_block_delta  → {"type": "content_block_delta", "index": N, "delta": {"type": "input_json_delta", "partial_json": "..."}}
content_block_delta  → ... (more deltas)
content_block_stop   → {"type": "content_block_stop", "index": N}
```

`content_block_start.content_block.input` is always `{}` — do not read it.
Accumulate `delta.partial_json` strings, join, then `json.loads()` on `content_block_stop`.

**Detection code pattern (inside `_stream_response`):**

```python
# Source: verified against claude_agent_sdk/types.py StreamEvent + Anthropic SSE docs
_tool_input_buffers: dict[int, list[str]] = {}  # index → partial JSON chunks
_tool_use_names: dict[int, str] = {}            # index → tool name
_orch_status_cell: OrchestratorStatusCell | None = None

if event.get("type") == "content_block_start":
    block = event.get("content_block", {})
    if block.get("type") == "tool_use":
        idx = event.get("index", 0)
        _tool_use_names[idx] = block.get("name", "")
        _tool_input_buffers[idx] = []

elif event.get("type") == "content_block_delta":
    delta = event.get("delta", {})
    idx = event.get("index", 0)
    if delta.get("type") == "input_json_delta":
        if idx in _tool_input_buffers:
            _tool_input_buffers[idx].append(delta.get("partial_json", ""))

elif event.get("type") == "content_block_stop":
    idx = event.get("index", 0)
    tool_name = _tool_use_names.pop(idx, None)
    raw = "".join(_tool_input_buffers.pop(idx, []))
    if tool_name == "conductor_delegate":
        try:
            args = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            args = {}
        task_description = args.get("task", "delegating...")
        self.post_message(DelegationStarted(task_description=task_description))
```

**When to use:** Use this accumulation pattern for ALL input_json_delta scenarios.
Never read `content_block.input` from `content_block_start` for tool input content.

### Pattern 2: Label Mutation on active AssistantCell

`AssistantCell` renders `Static("Assistant", classes="cell-label")`. When
`conductor_delegate` tool-use starts (on `content_block_start` for a tool_use block
with that name), mutate the label immediately — before input is fully accumulated:

```python
# Source: transcript.py Static widget pattern (already used by update_status)
if tool_name == "conductor_delegate":
    if cell is not None:
        try:
            cell.query_one(".cell-label", Static).update("Orchestrator — delegating")
        except Exception:
            pass
```

Do this on `content_block_start` (when the tool name is known), not on `content_block_stop`
(which would add a visible delay). This satisfies ORCH-01.

### Pattern 3: OrchestratorStatusCell via post_message (not await mount)

The `_stream_response` worker runs in Textual's `@work` context. `await mount()` inside
a worker **blocks the async generator** — the SDK stops delivering events until mount
completes. Use `post_message` to pass the cell creation to a `TranscriptPane` handler
that owns the DOM:

```python
# In _stream_response worker (app.py):
self.post_message(DelegationStarted(task_description=task_description))

# In TranscriptPane.on_delegation_started (transcript.py):
async def on_delegation_started(self, event: DelegationStarted) -> None:
    cell = OrchestratorStatusCell(
        label="Orchestrator — delegating",
        description=event.task_description,
    )
    self._orch_status_cell = cell
    await self.mount(cell)
    self._maybe_scroll_end()
```

This is the same `post_message` pattern already used for `AgentStateUpdated` fan-out
(confirmed in `app.py` line 175 and `transcript.py` line 387).

### Pattern 4: Extending DelegationStarted

Current `DelegationStarted` has only `task_description: str`. For ORCH-02 the cell
must show task content. The `task_description` field already carries the task arg
from `conductor_delegate` input. No agent identity is available at stream-interception
time (agents haven't been spawned yet — they are created inside `handle_delegate()`
which runs after the tool-use block completes).

**Resolution for the STATE.md blocker:** Agent identity is NOT available at
`content_block_stop` time. Use `task_description` from the parsed input for the
`OrchestratorStatusCell` description. Agent names appear later via `AgentStateUpdated`
(already handled in Phase 44). The `OrchestratorStatusCell` label shows the task
description; the individual `AgentCell` widgets show agent identity. This is the
correct two-layer display: orchestrator status cell for the delegation event, agent
cells for each spawned agent.

**Extend `DelegationStarted`** to carry `task_description` (already present) — no
structural change needed. The `DelegationComplete` message may be used in the future
to finalize the `OrchestratorStatusCell`.

### Anti-Patterns to Avoid

- **Reading `content_block_start.content_block.input`:** Always `{}` in real streaming.
  Real input arrives only via `input_json_delta` deltas.
- **`await mount()` inside `_stream_response`:** Blocks the SDK async generator,
  causing visible stutter. Use `post_message` + a handler in `TranscriptPane`.
- **Single-buffer accumulation (not indexed):** Multiple tool-use blocks can be open
  concurrently (e.g., thinking + tool_use). Must key the buffer by `content_block_index`.
- **Mutating label on `content_block_stop`:** The label change should happen as early
  as possible (on `content_block_start`) to give immediate feedback. Input accumulation
  is needed only for the `OrchestratorStatusCell` description.
- **Assuming conductor_delegate fires only once per conversation:** The worker resets
  state at the top of each `_stream_response` call (local variables), so multiple
  delegations across multiple user messages are handled correctly.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON accumulation | Custom streaming parser | stdlib `json.loads()` on complete buffer | Partial JSON is not valid JSON; accumulate first |
| Widget DOM mutation from worker | `await self.mount()` in `@work` | `post_message` to handler on `TranscriptPane` | Workers must not block async generator |
| Thread-safe message passing | asyncio.Queue / custom bridge | Textual's `post_message` | Already designed for cross-context widget communication |
| Agent identity at delegation time | Read from delegation layer | Read from `AgentStateUpdated` (Phase 44 system) | Agents don't exist until `handle_delegate()` creates them |

## Common Pitfalls

### Pitfall 1: input_json_delta Accumulation — Empty Input
**What goes wrong:** Reading `content_block_start.content_block.input` gives `{}`, so
the parsed `task` field is empty, and `OrchestratorStatusCell` shows no content.
**Why it happens:** The Anthropic API always sends `input: {}` on `content_block_start`
for tool_use blocks in streaming mode. All input arrives as delta events.
**How to avoid:** Initialize buffer on `content_block_start`, accumulate on
`content_block_delta` with `delta.type == "input_json_delta"`, parse on `content_block_stop`.
**Warning signs:** OrchestratorStatusCell body is blank or shows `"delegating..."` fallback.

### Pitfall 2: await mount() Stutter
**What goes wrong:** SDK event delivery pauses mid-stream; tokens stop flowing
momentarily while the widget is being mounted.
**Why it happens:** `@work` coroutines share Textual's event loop. `await mount()`
yields control, preventing the SDK async generator from advancing.
**How to avoid:** Use `self.post_message(DelegationStarted(...))` in the worker;
do `await self.mount(cell)` only inside `TranscriptPane.on_delegation_started`.
**Warning signs:** Visible text-stream pause exactly when conductor_delegate fires.

### Pitfall 3: content_block_index Collisions
**What goes wrong:** If a thinking block (index 0) is followed by a tool_use block
(index 1), using a single `_tool_input_buffer` variable (not a dict) mangles data.
**Why it happens:** Anthropic API streams multiple content blocks with different indices.
**How to avoid:** Key all buffer state by `content_block_index`. Use dicts:
`_tool_input_buffers: dict[int, list[str]]` and `_tool_use_names: dict[int, str]`.
**Warning signs:** task description contains non-JSON fragments or parsing errors.

### Pitfall 4: Label Mutation After Cell is Finalized
**What goes wrong:** Calling `cell.query_one(".cell-label").update(...)` after
`cell.finalize()` has run raises `NoMatches` or is silently dropped.
**Why it happens:** `finalize()` marks `_is_streaming = False` but doesn't remove children.
For `AssistantCell` the children remain, so the mutation works — BUT only if the cell
hasn't been garbage-collected or removed from the DOM.
**How to avoid:** Guard with `try/except Exception: pass` (same pattern already used
throughout the codebase for `.query_one()` mutations).

### Pitfall 5: json.JSONDecodeError on Partial or Empty Buffer
**What goes wrong:** `json.loads("")` raises `json.JSONDecodeError`; incomplete input
if stream is interrupted raises it too.
**Why it happens:** `content_block_stop` may fire before all deltas arrive in error
cases, or the buffer may be empty if the block had no delta events.
**How to avoid:** Guard with `try/except json.JSONDecodeError` and fall back to a
default description string like `"delegating..."`.

## Code Examples

### Minimal Stream Interception Extension for _stream_response

```python
# Source: verified pattern from app.py _stream_response + StreamEvent.event dict structure
import json
from conductor.tui.widgets.transcript import OrchestratorStatusCell, Static

# Initialize per-call (at top of _stream_response, before the SDK loop)
_tool_input_buffers: dict[int, list[str]] = {}
_tool_use_names: dict[int, str] = {}

# Inside the StreamEvent branch, after the existing text_delta block:
elif event.get("type") == "content_block_start":
    block = event.get("content_block", {})
    if block.get("type") == "tool_use":
        idx = event["index"]
        name = block.get("name", "")
        _tool_use_names[idx] = name
        _tool_input_buffers[idx] = []
        if name == "conductor_delegate" and cell is not None:
            try:
                cell.query_one(".cell-label", Static).update("Orchestrator — delegating")
            except Exception:
                pass

elif event.get("type") == "content_block_delta":
    delta = event.get("delta", {})
    idx = event.get("index", 0)
    if delta.get("type") == "input_json_delta" and idx in _tool_input_buffers:
        _tool_input_buffers[idx].append(delta.get("partial_json", ""))

elif event.get("type") == "content_block_stop":
    idx = event.get("index", 0)
    name = _tool_use_names.pop(idx, None)
    raw = "".join(_tool_input_buffers.pop(idx, []))
    if name == "conductor_delegate":
        try:
            args = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            args = {}
        task_description = args.get("task", "delegating...")
        self.post_message(DelegationStarted(task_description=task_description))
```

### TranscriptPane Handler for DelegationStarted

```python
# In TranscriptPane (transcript.py):
async def on_delegation_started(self, event: "DelegationStarted") -> None:
    """Mount OrchestratorStatusCell when conductor_delegate fires (ORCH-01, ORCH-02)."""
    from conductor.tui.messages import DelegationStarted
    cell = OrchestratorStatusCell(
        label="Orchestrator — delegating",
        description=event.task_description,
    )
    self._orch_status_cell = cell
    await self.mount(cell)
    self._maybe_scroll_end()
```

### DelegationStarted Message (no structural change needed)

```python
# Current messages.py — task_description already carries what we need:
class DelegationStarted(Message):
    def __init__(self, task_description: str) -> None:
        self.task_description = task_description
        super().__init__()
```

`DelegationStarted` already has `task_description`. No change to `messages.py`
is required for the core requirement. The blocker in STATE.md about agent identity
is resolved by deferring agent identity display to `AgentStateUpdated` (Phase 44
system), which fires once agents are actually created inside `handle_delegate()`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Read `content_block.input` from `content_block_start` | Accumulate `input_json_delta` deltas | Anthropic streaming API design | Must accumulate; old approach always yields `{}` |
| `await mount()` in async workers | `post_message` to widget handler | Phase 44 decision (STATE.md) | Non-blocking stream delivery |
| Label static text | `.update()` via `query_one(".cell-label")` | Phase 43 pattern (Static.content API) | Dynamic label updates confirmed working |

**Known current status:**
- `DelegationStarted` exists in `messages.py` but is NOT currently consumed by any widget handler (it was defined in an earlier phase but never wired to `TranscriptPane`)
- `_stream_response` in `app.py` only handles `content_block_delta` / `text_delta` today — `content_block_start` and `content_block_stop` are unhandled

## Open Questions

1. **OrchestratorStatusCell lifetime: when to finalize?**
   - What we know: `finalize()` exists on `OrchestratorStatusCell` and marks it immutable
   - What's unclear: Should it be finalized when `DelegationComplete` fires? When the
     first `AgentStateUpdated` arrives? Or never (left as a static record)?
   - Recommendation: For Phase 45, leave it open (never finalized). Phase 46 can wire
     `DelegationComplete` → `cell.finalize()` as part of visual polish.

2. **Multiple concurrent conductor_delegate calls**
   - What we know: `_stream_response` is `@work(exclusive=True)` — only one stream runs
     at a time, so a single delegation per user message is the only case
   - What's unclear: Could the orchestrator delegate twice in one stream? (Unlikely given
     the system prompt instructions and exclusive worker)
   - Recommendation: The indexed buffer approach handles this correctly anyway; treat
     as a non-issue for Phase 45.

3. **TranscriptPane._orch_status_cell registry**
   - What we know: `_agent_cells` dict exists for agent registry; `OrchestratorStatusCell`
     has no registry yet
   - What's unclear: Is a single-ref `_orch_status_cell: OrchestratorStatusCell | None`
     sufficient, or should it be a list for multiple delegations?
   - Recommendation: Single ref is sufficient for Phase 45 — each new delegation
     replaces it. A list can be added in Phase 46 if history matters.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + Textual test harness |
| Config file | `packages/conductor-core/pyproject.toml` |
| Quick run command | `uv run pytest packages/conductor-core/tests/test_tui_stream_interception.py -x` |
| Full suite command | `uv run pytest packages/conductor-core/tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STRM-01 | content_block_start for conductor_delegate tool_use detected | unit | `uv run pytest tests/test_tui_stream_interception.py::test_content_block_start_triggers_label_change -x` | Wave 0 |
| STRM-02 | input_json_delta deltas accumulated and parsed on content_block_stop | unit | `uv run pytest tests/test_tui_stream_interception.py::test_input_json_delta_accumulation -x` | Wave 0 |
| ORCH-01 | Active cell label changes from "Assistant" to "Orchestrator — delegating" | unit | `uv run pytest tests/test_tui_stream_interception.py::test_active_cell_label_becomes_orchestrator -x` | Wave 0 |
| ORCH-02 | OrchestratorStatusCell appears with task description content | unit | `uv run pytest tests/test_tui_stream_interception.py::test_orch_status_cell_shows_task_description -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest packages/conductor-core/tests/test_tui_stream_interception.py -x`
- **Per wave merge:** `uv run pytest packages/conductor-core/tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `packages/conductor-core/tests/test_tui_stream_interception.py` — covers STRM-01, STRM-02, ORCH-01, ORCH-02

*(Existing test infrastructure — pytest, pytest-asyncio, Textual harness — is already present. Only the new test file is missing.)*

## Sources

### Primary (HIGH confidence)
- `/home/huypham/code/digest/claude-auto/.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py` — `StreamEvent` structure, `ToolUseBlock`, all SDK types
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/app.py` — `_stream_response` worker, `post_message` pattern, `DelegationManager` wiring
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/widgets/transcript.py` — `AssistantCell`, `OrchestratorStatusCell`, `TranscriptPane`, existing handler patterns
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/tui/messages.py` — `DelegationStarted`, all existing message types
- `.planning/STATE.md` — Phase 45 blockers, established decisions on `post_message` vs `await mount`

### Secondary (MEDIUM confidence)
- Anthropic SSE streaming protocol (content_block_start / input_json_delta / content_block_stop sequence) — cross-verified with SDK types.py field names and existing stream event handling in `_stream_response`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, all tools already in use
- Architecture: HIGH — event sequence verified in SDK types; `post_message` pattern confirmed in existing Phase 44 code
- Pitfalls: HIGH — `input_json_delta` pitfall explicitly documented in STATE.md; `post_message` vs await confirmed as project decision

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (SDK types are stable; Textual API is stable)
