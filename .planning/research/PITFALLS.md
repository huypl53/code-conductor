# Pitfalls Research

**Domain:** Adding real-time agent visibility (labeled agent cells, tool-use interception, state-driven transcript) to existing Textual TUI — Conductor v2.2
**Researched:** 2026-03-12
**Confidence:** HIGH (direct codebase analysis of app.py, transcript.py, agent_monitor.py, SDK types.py, message_parser.py)

---

## Critical Pitfalls

### Pitfall 1: Blocking the Orchestrator Text Stream While Handling Tool-Use Events

**What goes wrong:**
The current `_stream_response` worker in `app.py` (line 364) iterates `async for message in self._sdk_client.receive_response()`. If agent-cell creation logic (mounting a new `AgentCell` widget) is awaited inside this same loop iteration, the SDK receive loop pauses. Any subsequent stream tokens arriving while the cell is mounting are queued but not delivered until the mount completes. On slow systems or with many concurrent agents, this produces visible "stutter" — text streaming stops mid-sentence while the agent cell mounts.

**Why it happens:**
`await self.mount(widget)` takes a round-trip through Textual's event loop to paint the widget and trigger `on_mount`. All `await` points in a `@work` coroutine yield back to the event loop; the SDK's async generator is only advanced on resume. Any non-trivial mount (composing children, running animations) delays the next `receive_response()` iteration.

**How to avoid:**
Post a Textual message (`self.post_message(AgentCellRequested(...))`) from inside the stream loop instead of `await`-ing the mount directly. The message handler runs on the next event loop iteration, independently of the stream loop. The stream continues advancing while the mount happens in parallel on the Textual event loop. Pattern already established in the codebase: `TokensUpdated` is posted rather than awaited (app.py lines 382-384).

```python
# Inside the stream loop — post, don't await
elif event.get("type") == "content_block_start":
    block = event.get("content_block", {})
    if block.get("type") == "tool_use" and block.get("name") == "conductor_delegate":
        self.post_message(AgentCellRequested(task_description=...))
# NOT: await pane.add_agent_cell(...)
```

**Warning signs:**
- Text streaming visibly pauses each time an agent cell appears
- `receive_response()` latency correlates with number of active agents
- Profiling shows `mount()` on the hot path inside the stream loop

**Phase to address:**
The phase intercepting tool-use events from the SDK stream — establish the post-message pattern before wiring any cell lifecycle.

---

### Pitfall 2: tool_use Input Not Fully Available in content_block_start — Must Reconstruct from Deltas

**What goes wrong:**
The SDK emits tool-use information across multiple stream events. The `content_block_start` event marks the beginning of a tool use block and may carry partial or empty `input` (`{}`). The actual tool arguments accumulate in subsequent `content_block_delta` events with `delta.type == "input_json_delta"`. Code that reads the task description from `content_block_start.content_block.input` will get an empty dict on every real invocation.

**Why it happens:**
The Anthropic streaming protocol follows a "start / delta / stop" structure for all content blocks including tool use. The current `_stream_response` handler already navigates this for text deltas (lines 367-375), but tool-use input deltas use a different delta type (`input_json_delta`) and must be JSON-concatenated before parsing. A naive implementation reads the start event and misses the actual arguments.

**How to avoid:**
Track pending tool-use blocks by `content_block_index` (the index field in `content_block_start` events). Accumulate `input_json_delta` strings. On `content_block_stop`, parse the accumulated JSON. Only then post the `AgentCellRequested` message with the full task description.

```python
# State inside the worker
_pending_tool_inputs: dict[int, list[str]] = {}  # index → accumulated json

# On content_block_start with type == "tool_use"
_pending_tool_inputs[index] = []
_pending_tool_names[index] = block.get("name", "")

# On content_block_delta with delta.type == "input_json_delta"
_pending_tool_inputs[index].append(delta.get("partial_json", ""))

# On content_block_stop
full_input = json.loads("".join(_pending_tool_inputs.pop(index, [])) or "{}")
if _pending_tool_names.pop(index, "") == "conductor_delegate":
    self.post_message(AgentCellRequested(task_description=full_input.get("task", "")))
```

**Warning signs:**
- Agent cells appear with empty or `"(unknown task)"` label even when the orchestrator is clearly delegating
- Task description always shows `{}` in debug logs
- Works in unit tests that use pre-built `AssistantMessage` objects (which have complete input) but fails on real streaming

**Phase to address:**
The phase implementing tool-use event interception — write a stream event state machine that tracks start/delta/stop, not just start.

---

### Pitfall 3: Single `_active_cell` Reference Broken by Multiple Concurrent Agent Cells

**What goes wrong:**
`app.py` stores exactly one `_active_cell: Any | None`. Adding per-agent streaming cells to the transcript creates N simultaneous streaming cells. If `_active_cell` is reused to hold the "most recently created" agent cell, the `StreamDone` handler calls `cell.finalize()` on whichever cell happens to be in `_active_cell` at that moment — not the one that just finished streaming. Other cells are never finalized and their shimmer timers run forever.

**Why it happens:**
The single-cell architecture was designed for a one-turn-at-a-time chat flow: user sends → one orchestrator response → `StreamDone`. Agent visibility adds N agent cells that stream concurrently (multiple agents run in parallel). There is no existing mechanism to correlate a "finalize" signal with a specific cell.

**How to avoid:**
Each agent cell must be identified by a stable key (agent ID or task ID). Store a `dict[str, AgentCell]` keyed by agent_id, not a single `_active_cell`. Finalize a cell when its specific completion signal arrives (state.json shows agent DONE, or `TaskNotificationMessage` for that agent arrives). Do not reuse the orchestrator `_active_cell` slot.

```python
# In ConductorApp
_agent_cells: dict[str, "AgentCell"] = {}

# On AgentCellCreated(agent_id, cell):
self._agent_cells[agent_id] = cell

# On AgentCellFinalized(agent_id):
cell = self._agent_cells.pop(agent_id, None)
if cell and cell._is_streaming:
    await cell.finalize()
```

**Warning signs:**
- After all agents complete, some agent cells still show shimmer animation
- `_shimmer_timer` is not None on cells that should be finalized
- CPU usage stays elevated after delegation completes

**Phase to address:**
The phase creating agent cell lifecycle — define the multi-cell registry before writing any cell finalization logic.

---

### Pitfall 4: State.json Race Condition — AgentStateUpdated Arrives Before AgentCell Is Mounted

**What goes wrong:**
`AgentMonitorPane._watch_state` has a 200ms debounce (`debounce=200` in `awatch`). When an agent starts, state.json is written before the SDK stream emits the `conductor_delegate` tool-use event (the orchestrator writes state when the sub-agent registers, then returns the result). This means `AgentStateUpdated` (for the new agent) fires before the corresponding `AgentCellRequested` message is processed by the transcript. The agent panel in the monitor pane shows the agent as active, but no matching cell exists in the transcript yet.

The reverse also happens: when an agent finishes, the transcript cell may receive a finalize signal (from `TaskNotificationMessage`) before state.json is updated, leaving the monitor pane showing the agent as active while the transcript cell is already finalized.

**Why it happens:**
Two independent data paths update UI state: the SDK stream (for the orchestrator's own perspective) and the state.json file watcher (for sub-agent registration). These run concurrently with no ordering guarantee.

**How to avoid:**
Treat the two data sources as independent. Do not require them to be in sync. The transcript cell lifecycle should be driven by one source (SDK stream events + TaskStarted/TaskNotification messages). The AgentMonitorPane is already driven by state.json independently. Do not attempt to create transcript cells in response to `AgentStateUpdated` — this creates a dependency between the two paths. Use `TaskStartedMessage` (already parsed by the SDK's `message_parser.py`) as the transcript trigger; use `AgentStateUpdated` only for the monitor pane.

**Warning signs:**
- Agent cells appear in transcript at different times than the monitor pane panels
- Spurious duplicate cells when state.json fires multiple events for one agent start
- KeyError on agent_id when `AgentStateUpdated` arrives before the cell registry is populated

**Phase to address:**
The phase wiring state.json updates to the transcript — establish that the transcript uses SDK stream events and the monitor pane uses state.json; never cross-wire them.

---

### Pitfall 5: TaskStartedMessage / TaskNotificationMessage Are SystemMessage Subclasses — Existing isinstance Check Catches Them Wrong

**What goes wrong:**
The current `_stream_response` loop checks `isinstance(message, StreamEvent)` and `isinstance(message, ResultMessage)` but has no branch for `SystemMessage`. In the SDK's `message_parser.py` (line 143-183), `TaskStartedMessage`, `TaskProgressMessage`, and `TaskNotificationMessage` are all subclasses of `SystemMessage`. They carry the `task_id`, `description`, and `session_id` needed to create and finalize agent cells. Because the current stream loop does not handle `SystemMessage`, these messages are silently dropped.

**Why it happens:**
When `include_partial_messages=True` (already set in `app.py` line 275), the SDK emits `StreamEvent` objects for partial tokens. But `TaskStartedMessage` and friends are parsed as `system` type messages — not stream events. They arrive interleaved with `StreamEvent` and `ResultMessage` in the same `receive_response()` iterator. The existing loop has an implicit "else: ignore" for any message type that isn't `StreamEvent` or `ResultMessage`.

**How to avoid:**
Add explicit handling for `SystemMessage` subtypes in the stream loop:

```python
from claude_agent_sdk.types import (
    TaskStartedMessage, TaskProgressMessage, TaskNotificationMessage
)

elif isinstance(message, TaskStartedMessage):
    self.post_message(AgentCellRequested(
        task_id=message.task_id,
        description=message.description,
        session_id=message.session_id,
    ))

elif isinstance(message, TaskNotificationMessage):
    self.post_message(AgentCellFinalized(
        task_id=message.task_id,
        status=message.status,
        summary=message.summary,
    ))
```

Note: `TaskStartedMessage` is a subclass of `SystemMessage`, so `isinstance(message, SystemMessage)` would match — check for the specific subclass first to avoid ambiguity.

**Warning signs:**
- No agent cells appear even though the orchestrator is delegating (tool-use events arrive, cells are never created)
- `TaskStartedMessage` is emitted by the SDK (visible in debug logging) but no handler fires
- Works when driven by hook callbacks but not from the stream loop

**Phase to address:**
The phase intercepting SDK events for agent cell creation — add all three `Task*Message` branches to the stream loop in the same phase as `StreamEvent` handling.

---

### Pitfall 6: Mounting New Cells During Active Scrolling — Scroll Position Jumps

**What goes wrong:**
`TranscriptPane._maybe_scroll_end()` (transcript.py line 190) scrolls to bottom only if the user is already near the bottom (`scroll_offset.y >= max_scroll_y - 2`). When an agent cell streams continuously, it grows in height, pushing `max_scroll_y` down. Each new token append triggers a layout recalculation. If the user has scrolled up to read previous content, mounting a new agent cell causes a layout shift and the scroll position appears to jump to an unexpected position (not to where the user was, not to the bottom).

**Why it happens:**
Textual's `VerticalScroll` container recalculates layout on every child size change. When a streaming `AgentCell` receives tokens and its `RichMarkdown` widget grows, the scroll container's `max_scroll_y` increases. If the user is at position Y and a cell above them grows, their apparent view position shifts. The `_maybe_scroll_end` guard only protects against forced scroll-to-bottom, not against scroll-position drift from height changes.

**How to avoid:**
Before mounting a new agent cell, record the current `scroll_offset.y` and `max_scroll_y`. After the mount completes, check if the new max differs; if the user was not at the bottom, restore their scroll position explicitly:

```python
async def add_agent_cell(self, ...) -> "AgentCell":
    was_at_bottom = self._is_at_bottom
    cell = AgentCell(...)
    await self.mount(cell)
    if was_at_bottom:
        self.scroll_end(animate=False)
    # else: preserve scroll position — do not force scroll
    return cell
```

Also: if multiple agent cells stream simultaneously, only auto-scroll for the most recently active one. The user following one agent should not be yanked away when a different agent appends a token.

**Warning signs:**
- Scroll position jumps when reading older content while agents are active
- User scrolls up to review output; position resets unexpectedly on every token
- The "scroll to bottom if near bottom" guard works for one cell but not for N cells growing simultaneously

**Phase to address:**
The phase adding `add_agent_streaming()` to `TranscriptPane` — test scroll behavior with 3 concurrent agents before considering the phase complete.

---

### Pitfall 7: Finalizing a Cell That Was Never Started — start_streaming() Not Called

**What goes wrong:**
`AssistantCell.finalize()` (transcript.py lines 116-126) calls `self._stream.stop()` if `_stream is not None`. But `_stream` is only set by `start_streaming()`. If the orchestrator calls `conductor_delegate` but immediately returns an error (delegation fails before any text is emitted), the agent cell is created, but `start_streaming()` is never called. When `finalize()` runs, `self._stream is None`, which is handled — but `self._is_streaming` is `True` (set in `__init__` when `text is None`). This leaves the `LoadingIndicator` visible indefinitely since `finalize()` only stops the stream, not the indicator.

**Why it happens:**
The current `AssistantCell` finalize path assumes `start_streaming()` was called before `finalize()`. The error path in `_stream_response` (app.py lines 394-407) calls `start_streaming()` before `append_token(error_message)` to handle this case for the orchestrator cell. The same defensive call must be made for agent cells when delegation fails before streaming begins.

**How to avoid:**
In `AgentCell.finalize()` (which will likely mirror `AssistantCell.finalize()`), always check if `start_streaming()` was called and, if not, remove the `LoadingIndicator` explicitly:

```python
async def finalize(self, error_message: str | None = None) -> None:
    if not self._started_streaming:
        # Delegation failed before streaming began — remove spinner
        try:
            await self.query_one(LoadingIndicator).remove()
        except Exception:
            pass
        if error_message:
            await self.mount(Static(f"Error: {error_message}"))
    else:
        await self._stream.stop()
        ...
    self._is_streaming = False
```

**Warning signs:**
- Agent cells show a spinning `LoadingIndicator` long after the delegation attempt failed
- `finalize()` returns immediately (no-ops) but the cell still looks "active"
- The cell is never removed and stays in the transcript as a zombie

**Phase to address:**
The phase implementing `AgentCell` finalization — write a test where delegation fails immediately (before any token is emitted) and verify the cell reaches a clean non-streaming state.

---

### Pitfall 8: Widget ID Collision Between AgentPanel and AgentCell When agent_id Has Special Characters

**What goes wrong:**
`AgentMonitorPane` creates `AgentPanel` widgets with `id=f"agent-{agent_id}"` (agent_monitor.py line 36). If the transcript creates `AgentCell` widgets with a similar ID scheme (`id=f"agent-cell-{agent_id}"`), and `agent_id` contains characters that are invalid in CSS selectors (dots, slashes, colons — common in UUID-based IDs or path-based IDs), `self.query_one(f"#agent-{agent_id}")` will raise a `NoMatches` or `InvalidSelector` exception. The current codebase uses this exact query pattern (agent_monitor.py line 169).

**Why it happens:**
Agent IDs in the orchestrator (`AgentRecord.id` in models.py) are strings with no format constraint in the model. If an orchestrator generates IDs like `"agent/1"`, `"wave-2.agent-3"`, or UUIDs with uppercase letters, the CSS selector `#agent-agent/1` is invalid. Textual's CSS selector parser does not escape these characters.

**How to avoid:**
Sanitize agent IDs before using them as CSS IDs. Replace any non-alphanumeric character with a hyphen or underscore:

```python
def _safe_widget_id(self, agent_id: str) -> str:
    import re
    return "agent-" + re.sub(r"[^a-zA-Z0-9_-]", "-", agent_id)
```

Use this sanitized ID for both the `AgentPanel` (monitor pane) and the `AgentCell` (transcript). Keep the original `agent_id` as a data attribute (`self._agent_id = agent_id`) for logic lookups.

**Warning signs:**
- `InvalidSelector` or `NoMatches` exceptions in the agent monitor log when updating an existing panel
- Panel creation succeeds but `update_status()` fails to find the panel by ID
- Only triggered with certain orchestrator configurations that produce unusual agent IDs

**Phase to address:**
The phase creating both `AgentPanel` and `AgentCell` widgets — add the `_safe_widget_id` sanitizer from the start; do not wait for it to break in production.

---

### Pitfall 9: Hook-Based Agent Attribution vs. Stream-Based — Choosing the Wrong Interception Layer

**What goes wrong:**
The SDK supports two ways to observe tool use: (1) `StreamEvent` events in the `receive_response()` loop with `content_block_start/delta/stop` events, and (2) `hooks` callbacks in `ClaudeAgentOptions` (`PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`). If a developer uses both simultaneously — stream events to detect `conductor_delegate` and hooks to detect `SubagentStart` — they get two fires for the same logical event. Agent cells are created twice, or finalization from one path conflicts with creation from the other.

**Why it happens:**
The SDK hook system and the stream event system are independent notification channels. `SubagentStart` hook fires when a Task tool invocation begins a sub-agent session. `content_block_start` for `tool_use` fires when the orchestrator emits the tool call into the stream. These are different events in the lifecycle, but both can appear to signal "agent starting". Using both without a deduplication layer creates double-registration.

**How to avoid:**
Pick one interception layer and commit to it for all agent visibility signals:

- **SDK stream events** (`content_block_start`, `TaskStartedMessage`, `TaskNotificationMessage`): already flowing through the existing `receive_response()` loop; no new infrastructure needed; lower latency for text visibility.
- **Hooks** (`SubagentStart`, `SubagentStop`, `PreToolUse`): fire outside the stream loop via callbacks; useful for actions that block tool execution (e.g., permission prompts), but adds callback infrastructure.

For v2.2 (read-only visibility, no blocking), stream events are the correct layer. Hooks are for permission enforcement. Do not mix them for the same signal.

**Warning signs:**
- Agent cells appear twice per delegation
- `AgentCell` in transcript and `AgentPanel` in monitor pane are out of sync by one state
- `_agent_cells` dict already contains a key when `AgentCellRequested` fires for a new agent

**Phase to address:**
The phase defining the event interception strategy — document the single chosen path in a comment at the top of the stream loop before writing any cell creation code.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reuse `_active_cell` for agent cells | No new registry code | Wrong cell finalized; shimmer timer leaks on all other cells | Never — add `_agent_cells: dict[str, AgentCell]` from the start |
| Create agent cells in `AgentStateUpdated` handler instead of SDK stream | Single data path | 200ms debounce delay on cell creation; misses agents that never write to state.json | Never — state.json and SDK stream are independent paths |
| Skip the input_json_delta accumulation; read input from `content_block_start` | Simpler code | Task description always empty on real streaming invocations | Never — the Anthropic streaming protocol requires delta accumulation |
| Use raw agent_id string as widget CSS ID | No sanitization code | `InvalidSelector` crash on agent IDs with dots, slashes, or spaces | Never — always sanitize with `re.sub` before using as CSS ID |
| `await pane.mount(AgentCell(...))` directly in stream loop | Simple, linear code | Blocks `receive_response()` for the mount duration; streaming stutters | Never — use `post_message(AgentCellRequested(...))` to decouple |
| Intercept both hooks and stream events for agent visibility | Belt-and-suspenders coverage | Duplicate cells; double-finalization; state machine becomes inconsistent | Never — pick one interception layer |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| SDK `receive_response()` + tool-use detection | Reading `content_block_start.content_block.input` for task description | Accumulate `input_json_delta` strings; parse JSON on `content_block_stop` |
| `TaskStartedMessage` in stream loop | Not handling `SystemMessage` subclasses because the loop only checks `StreamEvent` and `ResultMessage` | Add `isinstance(message, TaskStartedMessage)` branch before the generic `SystemMessage` fallthrough |
| `AgentStateUpdated` → transcript | Using `AgentStateUpdated` to trigger cell creation in `TranscriptPane` | Use SDK stream events (`TaskStartedMessage`) for transcript; `AgentStateUpdated` for monitor pane only |
| Multiple streaming cells + scroll | `scroll_end(animate=False)` on every token append across all cells | Only call `scroll_end` if `_is_at_bottom` was True before the new content; preserve user scroll position |
| `AgentPanel` + `AgentCell` shared ID | `id=f"agent-{agent_id}"` used in both widgets | Sanitize agent_id for CSS; use distinct prefixes (`agent-panel-`, `agent-cell-`) to prevent collisions |
| SDK hooks + stream events | Registering both `SubagentStart` hook and `TaskStartedMessage` handler | Choose stream events for v2.2 read-only visibility; reserve hooks for permission enforcement |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| N concurrent shimmer timers at 15fps each | CPU usage scales linearly with agent count | Each `AgentCell` uses the same 15fps `set_interval` from transcript.py; this is acceptable up to ~10 agents; above 10, reduce to 10fps | > 10 concurrent agents |
| MarkdownStream `write()` called on every token across N cells | Markdown parse latency accumulates; each write triggers a re-render | Batch tokens per cell (collect for 50ms, then write) if > 5 agents are streaming simultaneously | > 5 concurrent streaming agents |
| `on_agent_state_updated` doing DOM diffing on every state.json write | `query(AgentPanel)` traversal scales with number of panels; called on every debounced write | The 200ms debounce in `awatch` already throttles this; acceptable up to ~20 agents | > 20 agents with state.json writing at high frequency |
| Mounting `AgentCell` via `post_message` + handler creates a one-event-loop-tick delay | First token of agent output arrives before cell is mounted; first chunk is lost | Buffer the first token in the `AgentCellRequested` message; re-emit it after cell is mounted | Every invocation if not handled — first token always lost |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Agent cell label shows agent_id (a UUID or opaque string) | User cannot tell which agent is which | Show agent `name` and `role` from `AgentRecord`; use `TaskStartedMessage.description` for task context |
| Agent cell remains in transcript after agent completes | Transcript grows unboundedly during long sessions with many agents | Finalize (stop shimmer, freeze content) but keep cell; do not remove — removal during active streaming causes layout thrash |
| Orchestrator cell and agent cells interleaved with no visual distinction | User cannot tell orchestrator output from agent output | Use distinct accent colors per cell type: existing `$accent` for orchestrator, a different CSS variable (`$success` or custom) for agent cells |
| No indication that the orchestrator is in delegation (planning) phase | User sees blank streaming area while orchestrator is reasoning | Show an "Orchestrator: Planning..." status in StatusFooter or as a static cell during the orchestrator's pre-delegation reasoning phase |
| State.json watcher 200ms debounce means agent panel appears 200ms after agent starts | Minor but noticeable lag before the monitor pane updates | Acceptable; do not reduce debounce below 100ms (atomic-write inode swap on `os.replace` already solved by parent-directory watch — documented in PROJECT.md Key Decisions) |

---

## "Looks Done But Isn't" Checklist

- [ ] **Tool-use input accumulation:** Verify task description in `AgentCellRequested` is populated from accumulated `input_json_delta`, not from `content_block_start.input`. Test with real orchestrator delegation, not unit tests with pre-built `AssistantMessage` objects.
- [ ] **SystemMessage handling in stream loop:** Confirm `TaskStartedMessage` and `TaskNotificationMessage` are handled in `_stream_response`. Add a test that injects a `TaskStartedMessage` into the `receive_response()` mock and verifies cell creation fires.
- [ ] **Multi-cell shimmer cleanup:** After a full delegation cycle (3+ agents), verify zero shimmer timers remain active on finalized cells. CPU should return to baseline after all agents complete.
- [ ] **Scroll preservation:** Scroll up 10 lines while an agent is streaming. Verify the scroll position is preserved when new tokens arrive. Scroll position should only auto-advance if the user was at the bottom before the token arrived.
- [ ] **CSS ID sanitization:** Test with an orchestrator that generates agent IDs containing dots or slashes. Verify `update_status()` can find the `AgentPanel` after the ID is sanitized.
- [ ] **Failed delegation cell state:** Trigger a delegation failure before any agent text is emitted. Verify the agent cell reaches a non-streaming state (no spinner, no shimmer) and shows an error message.
- [ ] **Single interception path:** Grep confirms no `hooks` configuration for `SubagentStart` or `PreToolUse` if the stream event path is used. Zero duplicate cell creation events in logs during delegation.
- [ ] **Cell registry cleanup:** After delegation completes, verify `_agent_cells` dict is empty (all entries popped on finalization). Memory does not grow across multiple delegation cycles.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Stream loop blocking on mount | MEDIUM | Move all `await mount(...)` calls out of the stream loop into message handlers; existing `TokensUpdated` pattern in app.py is the model |
| Empty task description on all agent cells | LOW | Add delta accumulation state machine to stream loop; add integration test with real SDK stream fixture |
| Shimmer timer leaks on finalized cells | LOW | Add `_agent_cells` cleanup in finalization; add test that counts active timers after delegation cycle |
| Scroll position jump during streaming | LOW | Wrap all `mount()` calls in `add_agent_cell()` with `_is_at_bottom` guard; restore scroll offset if user was not at bottom |
| Duplicate agent cells from mixed hook + stream event path | MEDIUM | Remove hook registrations; audit stream loop for double-fire conditions; add `if agent_id in _agent_cells: return` guard |
| Widget ID crash on unusual agent IDs | LOW | Add `_safe_widget_id()` sanitizer to `AgentPanel` and `AgentCell`; update `query_one()` calls to use sanitized form |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Stream loop blocking on mount | Phase implementing tool-use interception | Streaming text continues uninterrupted while agent cell mounts; no visible stutter |
| Empty task description from missing delta accumulation | Phase implementing tool-use interception | Integration test with real streaming fixture shows non-empty task description in agent cell |
| `_active_cell` reuse breaking multi-cell finalization | Phase defining AgentCell lifecycle | After 3-agent delegation, zero shimmer timers on finalized cells; CPU returns to baseline |
| `TaskStartedMessage` silently dropped in stream loop | Phase wiring SDK events to agent cells | Unit test: mock `receive_response()` yields `TaskStartedMessage`; verify `AgentCellRequested` fires |
| State.json / SDK stream race causing out-of-order cell creation | Phase wiring state.json to transcript | Delete the cross-wire; confirm transcript uses SDK stream only; monitor pane uses state.json only |
| Cell never started (`start_streaming()` not called) before `finalize()` | Phase implementing AgentCell finalization | Test: delegation fails before first token; cell shows error, no spinner, no shimmer |
| CSS ID collision / invalid selector | Phase creating AgentPanel + AgentCell | Test with agent_id = "wave-1.agent/2"; both widgets created and queryable without exception |
| Mixed hook + stream event double-fire | Phase defining interception strategy | Grep: no hook registrations for SubagentStart/PreToolUse in the stream visibility path |
| Scroll jump during streaming | Phase adding `add_agent_streaming()` to TranscriptPane | Manual test: scroll up while 3 agents stream; position holds until user returns to bottom |

---

## Sources

- Codebase: `packages/conductor-core/src/conductor/tui/app.py` — `_stream_response` worker, `_active_cell` pattern, `TokensUpdated` post-message pattern (HIGH confidence — direct code analysis)
- Codebase: `packages/conductor-core/src/conductor/tui/widgets/transcript.py` — `AssistantCell` lifecycle (`start_streaming`, `append_token`, `finalize`), `_maybe_scroll_end` scroll guard (HIGH confidence — direct code analysis)
- Codebase: `packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py` — `AgentPanel` ID scheme, `_watch_state` debounce, `on_agent_state_updated` DOM diffing (HIGH confidence — direct code analysis)
- Codebase: `.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py` — `StreamEvent`, `TaskStartedMessage`, `TaskProgressMessage`, `TaskNotificationMessage`, `HookEvent` union, `SubagentStartHookInput` (HIGH confidence — installed SDK source)
- Codebase: `.venv/lib/python3.13/site-packages/claude_agent_sdk/_internal/message_parser.py` — confirms `task_started/task_progress/task_notification` parsed from `"system"` type messages; confirms `StreamEvent` parsed from `"stream_event"` type (HIGH confidence — installed SDK source)
- Codebase: `.planning/PROJECT.md` — Key Decision: "Watch parent directory for state changes — watchfiles misses atomic os.replace inode swaps on direct file watch" (HIGH confidence — project decision log)
- [Anthropic Streaming API — Tool Use](https://docs.anthropic.com/en/api/messages-streaming#tool-use) — `content_block_start` / `input_json_delta` / `content_block_stop` protocol for tool-use input accumulation (HIGH confidence — official docs)
- [Textual `post_message` vs `await mount` in workers](https://textual.textualize.io/guide/workers/) — worker `await` yields event loop; post_message is fire-and-forget; established pattern for decoupling stream processing from DOM mutation (HIGH confidence — official docs)

---
*Pitfalls research for: v2.2 Agent Visibility — adding labeled agent cells, tool-use interception, state.json-driven transcript to existing Textual TUI*
*Researched: 2026-03-12*
