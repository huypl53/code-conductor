# Project Research Summary

**Project:** Conductor v2.2 — Agent Visibility (Conductor milestone)
**Domain:** Real-time multi-agent visibility in a Textual TUI — labeled per-agent output streams, tool-use interception, state-driven transcript
**Researched:** 2026-03-12
**Confidence:** HIGH

## Executive Summary

Conductor v2.2 adds four targeted agent visibility features to an already-shipped, 663-test TUI codebase: a labeled `AgentCell` widget in the primary transcript, an orchestrator status indicator during planning/delegation phases, SDK tool-use event interception to trigger cell lifecycle, and state.json agent updates feeding into the transcript as labeled activity cells. All four features are achievable with zero new dependencies — every required API (`AssistantMessage`, `ToolUseBlock`, `AgentStateUpdated`, `watchfiles`) is already installed and confirmed present in the codebase. The core architectural gap is that `TranscriptPane` is currently blind to delegation: `AssistantMessage` with `ToolUseBlock` is silently dropped in `_stream_response`, and `AgentStateUpdated` only reaches `AgentMonitorPane`, not the transcript.

The recommended approach is a layered build: create the two new widget classes (`AgentCell`, `OrchestratorStatusCell`) and extend `TranscriptPane` with a `_agent_cells` dict and `on_agent_state_updated` handler first, then wire the SDK stream interception in `app.py`. The defining architectural choice — confirmed by competitor analysis of IttyBitty, Conduit, and Codex RFC #12047 — is to keep agent output inline in the primary transcript rather than in separate tabs or side panels. This preserves the conversation-centric mental model users already understand.

The dominant risks are implementation-level, not architectural. The most dangerous is accumulating tool-use input from `input_json_delta` stream events correctly (reading from `content_block_start` always yields an empty dict on real streaming invocations). The second is avoiding blocking the SDK `receive_response()` loop by `await`-ing widget mounts directly inside it. Both are solved by patterns already established in the codebase (`TokensUpdated` post-message pattern, `AssistantMessage` handling in `cli/chat.py`).

## Key Findings

### Recommended Stack

All v2.2 features run on the existing stack with zero new dependencies. The two data pipelines needed are: (1) SDK stream → `AssistantMessage` + `ToolUseBlock` interception in `_stream_response` for orchestrator delegation detection, and (2) `watchfiles` → `AgentStateUpdated` → `TranscriptPane` fan-out for agent cell lifecycle driven by state.json. Both pipelines are partially in place — they only need to be extended to reach `TranscriptPane`.

**Core technologies:**
- `textual 8.1.1`: Widget lifecycle (`mount`, `VerticalScroll`, `post_message`, `on_*` handlers) — all confirmed working; `AgentCell` and `OrchestratorStatusCell` are new widgets built to existing patterns
- `claude-agent-sdk 0.1.48`: `AssistantMessage`, `ToolUseBlock`, `StreamEvent`, `TaskStartedMessage`, `TaskNotificationMessage` all confirmed in `types.py` and `message_parser.py` — the integration point is adding a new `elif isinstance(message, AssistantMessage)` branch to `_stream_response`
- `watchfiles 1.1.1`: `awatch()` with 200ms debounce already watches the `.conductor/` parent directory — `TranscriptPane` subscribes to `AgentStateUpdated` independently via Textual's message bus fan-out with no changes to the watcher itself
- `pydantic v2`: `AgentRecord.name`, `.role`, `.status`, `.id` and `Task.title`, `.assigned_agent` all confirmed in `models.py` — sufficient data for agent cell headers without any model changes

### Expected Features

All four v2.2 features are table stakes for a multi-agent TUI — confirmed by Claude Code issues #9521 and #6007, Codex RFC #12047, and competitor analysis.

**Must have (table stakes for v2.2):**
- `AgentCell` widget — labeled cell in transcript showing agent name, role, task title; shimmer during work; finalized on DONE; foundation all other features build on
- Orchestrator status label — change active cell label from "Assistant" to "Orchestrator"; delegate state shown at delegation time; makes the orchestrator's phase legible
- Tool-use event interception — detect `conductor_delegate` ToolUseBlock in `_stream_response`; mount `OrchestratorStatusCell` showing delegation task; only `conductor_delegate` triggers this, not other tool calls
- State.json agent updates to transcript — `TranscriptPane.on_agent_state_updated()` mirrors `AgentMonitorPane`'s existing diff logic; new WORKING agents get `AgentCell` mounted; DONE transitions finalize cells

**Should have (competitive differentiators, v2.2):**
- Inline delegation event cells — brief "Orchestrator delegating: [task]" cell before sub-agents appear; keeps user oriented without requiring side-panel attention
- Orchestrator vs agent visual distinction — distinct CSS accent colors per cell type; CSS-only once `AgentCell` has role data

**Defer (v2.3+):**
- Color-coded per-agent identity — different tint per agent role/instance; trigger when 3+ concurrent agents make visual parsing difficult
- Agent completion summary with task outputs — include `Task.outputs` data in finalization cell
- Drill-down to sub-agent transcript — link from `AgentCell` to the full sub-agent `.jsonl` file; HIGH complexity, power-user feature

**Anti-features (never build):**
- Full sub-agent transcript replay inline — information overload; destroys conversation flow model
- Real-time interleaved token streaming from N agents — concurrent streams in one scroll view are illegible (confirmed by Codex RFC rejection)
- Separate tab per agent — context switching destroys the conversational thread

### Architecture Approach

The v2.2 architecture adds two new widget classes and extends two existing components with no structural changes to the existing working pipeline. `AgentCell` mirrors `AssistantCell`'s lifecycle (`update_status`, `finalize`) but is state-snapshot-driven rather than token-stream-driven. `OrchestratorStatusCell` is an ephemeral status cell created on delegation detection and finalized at `StreamDone`. The critical routing change is that `AgentStateUpdated` now fan-outs to both `AgentMonitorPane` (existing) and `TranscriptPane` (new) independently via Textual's message bus — no coordination layer needed between the two widgets.

**Major components:**
1. `app.py._stream_response` — detects `conductor_delegate` `ToolUseBlock` in `AssistantMessage`; creates `OrchestratorStatusCell`; holds reference as `_active_orchestrator_status`; finalizes at `StreamDone`; does NOT route `AgentStateUpdated` (handled by message bus fan-out)
2. `TranscriptPane` — new `_agent_cells: dict[str, AgentCell]`; new `on_agent_state_updated()` diff logic; new `add_agent_cell()` and `add_orchestrator_status()` methods; existing scroll guard extended for N-cell scenario
3. `AgentCell` — new widget in `transcript.py`; stable DOM `id` using sanitized agent_id; CSS badge header with name/role; `update_status()` / `finalize()` methods; stays mounted permanently as transcript history
4. `OrchestratorStatusCell` — new widget in `transcript.py`; ephemeral status cell; `update()` / `finalize()` methods; created and cleaned up by `app.py`
5. `AgentMonitorPane` — unchanged; continues owning the `_watch_state` worker and right-panel `AgentPanel` widgets

**Build order (dependencies flow downward):** Steps 1-3 are independent (message type, `AgentCell`, `OrchestratorStatusCell`). Step 4 (`TranscriptPane` extensions) depends on Steps 2 and 3. Step 5 (`app.py` interception) depends on Steps 1, 3, and 4. Step 6 (CSS) is parallel with Step 5.

### Critical Pitfalls

1. **tool_use input accumulation from stream deltas** — `content_block_start.content_block.input` is always `{}` on real streaming invocations. The task description accumulates across `input_json_delta` events. Must track pending tool inputs by `content_block_index`, accumulate JSON fragments, and parse only on `content_block_stop`. Unit tests using pre-built `AssistantMessage` objects pass while integration always shows empty labels.

2. **Blocking `receive_response()` with `await mount()`** — `await self.mount(AgentCell(...))` inside the stream loop pauses the SDK async generator for the full mount duration, causing visible streaming stutter. Use `self.post_message(AgentCellRequested(...))` instead. Pattern already established: `TokensUpdated` is posted (not awaited) in `app.py` lines 382-384.

3. **`TaskStartedMessage` / `TaskNotificationMessage` silently dropped** — these are `SystemMessage` subclasses. The current stream loop only handles `StreamEvent` and `ResultMessage`. Without explicit `isinstance(message, TaskStartedMessage)` branches, agent start/completion signals are never received. Add all three `Task*Message` branches in the same phase as the `StreamEvent` handling changes.

4. **`_active_cell` reuse breaking multi-cell finalization** — the single `_active_cell` reference on `ConductorApp` cannot track N concurrent agent cells. Each agent cell must be identified by its `agent_id` in a `dict[str, AgentCell]`. Reusing `_active_cell` means all but the last agent cell are never finalized and their shimmer timers run indefinitely. Build the `_agent_cells` dict from the start.

5. **CSS widget ID collision from unsanitized agent IDs** — agent IDs with dots, slashes, or spaces produce invalid CSS selectors when used directly as widget IDs. Always sanitize with `re.sub(r"[^a-zA-Z0-9_-]", "-", agent_id)` before constructing widget IDs. Use distinct prefixes (`agent-panel-` vs `agent-cell-`) to prevent collisions between `AgentPanel` and `AgentCell`.

## Implications for Roadmap

Based on the research, the build order is constrained by one hard dependency chain: widget classes must exist before `TranscriptPane` is extended, which must exist before `app.py` wiring. Within that chain, the two new widget classes can be built in parallel.

### Phase 1: AgentCell and OrchestratorStatusCell Widgets

**Rationale:** Every subsequent feature depends on these widget classes existing. Building them first enables independent testing of the visual design before any wiring. No integration risk — pure widget code with no external dependencies.
**Delivers:** Two new `transcript.py` widget classes with full lifecycle methods (`update_status`, `finalize`); CSS variants in `conductor.tcss`; unit tests verifying `finalize()` with and without prior `start_streaming()`
**Addresses:** AgentCell widget (P1 table stakes); visual distinction between orchestrator/agent cell types (P1 differentiator)
**Avoids:** Pitfall 7 (cell finalized before streaming started — build defensive `finalize()` from the start); Pitfall 8 (CSS ID sanitization — add `_safe_widget_id()` to both widgets from the start)

### Phase 2: TranscriptPane Extensions and State.json Fan-Out

**Rationale:** Extends `TranscriptPane` to consume `AgentStateUpdated` and mount `AgentCell` widgets. Uses Textual's message bus fan-out — `AgentMonitorPane` code is unchanged. Agent cells appear in the transcript driven by state.json, which can be tested by writing directly to state.json without touching the SDK stream path.
**Delivers:** `TranscriptPane._agent_cells` dict; `add_agent_cell()` / `add_orchestrator_status()` methods; `on_agent_state_updated()` diff logic mirroring `AgentMonitorPane`'s existing pattern; scroll guard extended for N-cell scenario
**Addresses:** State.json agent updates to transcript (P1 table stakes); scroll preservation under concurrent streaming agents
**Avoids:** Pitfall 3 (multi-cell finalization — build `_agent_cells` dict here, not a single reference); Pitfall 4 (state.json / SDK stream race — transcript driven by state.json in this phase, SDK events in Phase 3, they remain independent data sources); Pitfall 6 (scroll position jump — wrap all `mount()` in `_is_at_bottom` guard)

### Phase 3: SDK Stream Interception and Orchestrator Status

**Rationale:** Wires `_stream_response` in `app.py` to detect `conductor_delegate` tool-use and create `OrchestratorStatusCell`. This is the highest-risk phase — it modifies the live stream loop. Building it last means Phases 1 and 2 are stable before the stream path is touched.
**Delivers:** `AssistantMessage` + `ToolUseBlock` interception in `_stream_response`; `TaskStartedMessage` / `TaskNotificationMessage` handling; `OrchestratorStatusCell` creation and finalization; orchestrator cell label changed from "Assistant" to "Orchestrator"
**Addresses:** Tool-use event interception (P1 table stakes); orchestrator status display (P1 table stakes)
**Avoids:** Pitfall 1 (stream loop blocking — use `post_message` not `await mount`); Pitfall 2 (delta accumulation — implement `content_block_index` state machine); Pitfall 5 (`TaskStartedMessage` silently dropped — add all `Task*Message` branches); Pitfall 9 (mixed hook + stream event double-fire — stream events only, no hooks)

### Phase 4: Visual Polish and Verification

**Rationale:** Low-effort, high-return polish pass once the P1 features are stable. Executes the "looks done but isn't" checklist from PITFALLS.md before the milestone is declared done.
**Delivers:** Color-coded per-agent identity (CSS-only); inline delegation event cells; agent completion summaries; full verification against PITFALLS.md checklist (shimmer cleanup, scroll preservation, CSS ID sanitization, failed delegation cell state)
**Addresses:** P2 differentiator features; performance validation under N concurrent streaming agents

### Phase Ordering Rationale

- Phase 1 before Phase 2: `TranscriptPane` extension calls `AgentCell()` constructor — widget class must exist first
- Phase 2 before Phase 3: `TranscriptPane.add_orchestrator_status()` must exist before `app.py` calls it; also gives a clean integration test surface (state.json → cells) before the stream path is modified
- Phase 3 last in core features: modifies the live stream loop; highest regression risk; isolated to `app.py` once transcript infrastructure is ready
- Phase 4 decoupled: can be split across phases or done as a standalone polish milestone

### Research Flags

Phase with implementation complexity that benefits from reviewing research files before coding:
- **Phase 3:** The `input_json_delta` accumulation state machine (Pitfall 2) and `TaskStartedMessage` routing (Pitfall 5) are the most likely sources of bugs. STACK.md "Feature 1: Tool-Use Interception" and PITFALLS.md sections 2 and 5 should be reviewed before writing the stream loop changes. Consider a 20-line prototype that accumulates tool input from a real streaming fixture before wiring the full message bus.

Phases with standard patterns (skip research-phase, safe to implement directly):
- **Phase 1:** Pure widget classes following `AssistantCell` as the template; no integration complexity; patterns fully documented in ARCHITECTURE.md
- **Phase 2:** Directly mirrors existing `AgentMonitorPane.on_agent_state_updated()` diff logic; pattern is proven and documented in ARCHITECTURE.md with exact code samples
- **Phase 4:** CSS-only changes plus verification checklist; no new architectural decisions required

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All APIs verified by direct inspection of installed SDK source (`types.py`, `message_parser.py`) and codebase (`app.py`, `transcript.py`, `agent_monitor.py`). Zero new dependencies needed. |
| Features | HIGH (codebase) / MEDIUM (competitive) | Table stakes and differentiators confirmed by direct codebase inspection. Competitor feature analysis (IttyBitty, Conduit, Codex RFC) based on web research — solid directional signal but not authoritative on exact patterns. |
| Architecture | HIGH | Full data flow diagrams verified against live source. Integration points are additive (new `elif` branch, new message handler) with LOW risk to existing code paths. Component boundaries are clear. |
| Pitfalls | HIGH | Pitfalls derived from direct code analysis of `_stream_response`, `AssistantCell.finalize()`, `AgentMonitorPane` ID patterns, and official Anthropic streaming protocol docs. All pitfalls verified against actual source — not inferred. |

**Overall confidence:** HIGH

### Gaps to Address

- **`DelegationStarted` message lacks agent identity:** `DelegationStarted` currently only carries `task_description`, not `agent_name` or `agent_role`. For the `OrchestratorStatusCell` to show rich delegation info, either `DelegationStarted` is extended or the agent identity comes from `TaskStartedMessage.description`. Resolve during Phase 3 planning before writing the stream loop.
- **`TaskStartedMessage` content shape in real invocations:** The `description` field in `TaskStartedMessage` is confirmed in SDK types but its actual content (free-form string vs structured data) should be validated against a live orchestrator delegation during Phase 3. Unit tests with mocked SDK may pass while real content differs in format.
- **Scroll behavior under N concurrent streaming agents:** Pitfall 6 documents the risk and the fix (`_is_at_bottom` guard). The "acceptable up to ~10 agents" shimmer timer performance claim has not been profiled against the actual TUI. Validate during Phase 4 verification with 3+ concurrent agents.

## Sources

### Primary (HIGH confidence)
- `packages/conductor-core/src/conductor/tui/app.py` — `_stream_response` worker, `_active_cell` pattern, `TokensUpdated` post-message pattern (direct code analysis)
- `packages/conductor-core/src/conductor/tui/widgets/transcript.py` — `AssistantCell` lifecycle, `_maybe_scroll_end` scroll guard, `TranscriptPane` structure (direct code analysis)
- `packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py` — `AgentPanel` ID scheme, `_watch_state` debounce, `on_agent_state_updated` diff logic (direct code analysis)
- `packages/conductor-core/src/conductor/tui/messages.py` — `DelegationStarted`, `DelegationComplete`, `AgentStateUpdated` confirmed defined; `DelegationStarted` lacks agent identity fields
- `packages/conductor-core/src/conductor/state/models.py` — `AgentRecord.name/role/status/id`, `Task.title/assigned_agent`, `AgentStatus` enum confirmed
- `.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py` — `AssistantMessage`, `ToolUseBlock`, `StreamEvent`, `TaskStartedMessage`, `TaskNotificationMessage` all confirmed
- `.venv/lib/python3.13/site-packages/claude_agent_sdk/_internal/message_parser.py` — `tool_use` → `ToolUseBlock` parsing confirmed; `system` type → `Task*Message` parsing confirmed
- [Anthropic Streaming API — Tool Use](https://docs.anthropic.com/en/api/messages-streaming#tool-use) — `content_block_start/input_json_delta/content_block_stop` protocol confirmed
- [Textual workers guide](https://textual.textualize.io/guide/workers/) — `post_message` vs `await mount` in worker coroutines confirmed

### Secondary (MEDIUM confidence)
- [Claude Code issue #9521](https://github.com/anthropics/claude-code/issues/9521) — confirms industry-wide pain point: sub-agent output invisible in TUI
- [Claude Code issue #6007](https://github.com/anthropics/claude-code/issues/6007) — confirms transcript-level agent visibility as top user request
- [Codex multi-agent TUI RFC #12047](https://github.com/openai/codex/issues/12047) — confirms colored per-agent tags pattern; rejection of interleaved output
- [IttyBitty multi-agent TUI](https://adamwulf.me/2026/01/itty-bitty-ai-agent-orchestrator/) — confirms manager/worker label + side panel pattern; Conductor's inline approach is differentiated
- [Conduit multi-agent TUI](https://getconduit.sh/) — confirms tab-per-agent as the alternative Conductor explicitly avoids

---
*Research completed: 2026-03-12*
*Ready for roadmap: yes*
