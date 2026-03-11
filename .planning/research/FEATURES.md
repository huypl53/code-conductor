# Feature Research

**Domain:** Agent visibility in multi-agent TUI — labeled per-agent output streams (Conductor v2.2)
**Researched:** 2026-03-12
**Confidence:** HIGH (codebase direct inspection) / MEDIUM (competitor patterns via web search)

---

## Context: This Is a Subsequent Milestone

This research focuses exclusively on **what's needed for v2.2 agent visibility**. All v2.1 features are already built and passing 663 tests.

**Already built (no changes needed):**
- `TranscriptPane` with `UserCell` / `AssistantCell`, shimmer animation, streaming lifecycle
- `AgentMonitorPane` with state.json watcher, collapsible `AgentPanel` per active agent
- `AgentStateUpdated`, `DelegationStarted`, `DelegationComplete`, `ToolActivity` messages in `messages.py`
- `AgentRecord` with `name`, `role`, `status` fields in `state/models.py`
- SDK streaming worker `_stream_response` already receives `StreamEvent` including `tool_use` events

**v2.2 adds four targeted agent visibility features on top of this foundation:**
1. Labeled `AgentCell` widget in transcript showing agent name, role, streaming output
2. Orchestrator status indicator during planning/delegation phases
3. Tool-use event interception from SDK stream to trigger agent cells
4. State.json agent updates feed into transcript as labeled activity

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in any multi-agent TUI. Missing these = the product feels opaque or incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Labeled agent cells in transcript | When the orchestrator delegates, user expects to see which agent is responding — showing "Assistant" throughout a multi-agent workflow is ambiguous. Claude Code issues #9521 and #6007, Codex multi-agent RFC #12047, and IttyBitty all confirm this is the primary pain point in multi-agent TUIs | LOW | Extend `AssistantCell` or create `AgentCell` widget with `agent_name` / `agent_role` params; CSS badge label already patterns in existing `UserCell` and `AssistantCell` cells |
| Agent name + role in cell header | `AgentRecord.name` and `AgentRecord.role` already exist in state.json and in `AgentPanel` — not surfacing them in the transcript is a UX gap. Users watching the AgentMonitorPane know agent names but the primary transcript is silent | LOW | Route agent identity to transcript at delegation time; data already available |
| Orchestrator status indicator during planning/delegation | User submits a message; orchestrator thinks, plans, then delegates — "Assistant" with shimmer is opaque for this phase. IttyBitty uses a manager/worker distinction; Codex RFC proposes colored `@handle` tags; the shared pattern is distinguishing orchestrator state from agent work | MEDIUM | Requires distinct visual state for "orchestrator thinking" vs "orchestrator delegating" vs "agent working"; `DelegationStarted` message already posted when delegation begins |
| State.json agent activity in transcript | `AgentMonitorPane` already watches state.json and updates the side panel, but the primary transcript stays silent during delegation phases. Users who scroll through the transcript after a run see no record of what agents did | MEDIUM | `AgentStateUpdated` is already posted to the app; needs a bridge so transcript pane also receives state change events and mounts labeled event cells |

### Differentiators (Competitive Advantage)

Features that go beyond what competitors show, providing meaningful extra value in the transcript-centric model.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Inline streaming `AgentCell` in primary transcript | Most tools (IttyBitty, Conduit) show agents in a separate side panel or tab. Conductor puts per-agent output directly inline in the primary conversation transcript, matching how users read conversations without context switching. Claude Code issue #6007 explicitly requests this as a top feature | MEDIUM | `AgentCell` widget extending `AssistantCell` streaming lifecycle pattern; spawned when `DelegationStarted` fires or when tool-use event is intercepted |
| Orchestrator vs agent visual distinction | Color-coded labels (different border tint or header color for orchestrator vs sub-agents) make the hierarchy immediately legible. Codex RFC proposes colored `@handle` tags per agent for exactly this reason. IttyBitty uses manager/worker type labels | LOW | CSS-only once `AgentCell` has `agent_role` data; add role-based CSS class variant (`AgentCell.--orchestrator` vs `AgentCell.--worker`) |
| Inline delegation event cells | A brief inline event showing "Orchestrator delegating: [task description]" keeps the user oriented without requiring them to look at the side panel. Ralph TUI and IttyBitty use separate log panels; Conductor's inline approach is more cohesive with the chat mental model | LOW | Static `AgentCell` variant or minimal event cell mounted when `DelegationStarted` fires; uses `task_description` already in `DelegationStarted` message |
| Agent completion summaries inline | When state.json shows an agent transition to DONE, post a brief inline completion cell with agent name and task title. Gives the transcript a full record of what happened during delegation. Claude Code issue #6007 requests "drill-down" capability — this is a first step | LOW | `AgentStateUpdated` handler watches for `AgentStatus.DONE` transitions and mounts a summary cell; task title already in `Task.title` in state |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full sub-agent transcript replay in main transcript | Claude Code issues #9521 and #6007 show users want to see every tool call inside sub-agents | Sub-agents can have thousands of tokens of internal tool calls. Dumping all of it into the main transcript destroys the conversation flow model and creates information overload — the exact problem Codex RFC #12047 is trying to solve | Show agent name, role, task, and final summary only in main transcript; link to separate `.jsonl` transcript file for drill-down (future feature) |
| Real-time token streaming from sub-agents interleaved | Feels like maximum visibility | Sub-agents run concurrently; interleaved token streams from N agents in one scrolling view is illegible. This is confirmed by Codex RFC's rejection of interleaved output in favor of separate tabs | Stream each agent in its own labeled cell that appears when delegation starts; show loading shimmer during agent work; replace shimmer with summary on completion |
| Separate tab per agent | Conduit does this (up to 10 tabs); provides full isolation | Switches context away from the primary orchestrator conversation; user loses the conversational thread they initiated. Each tab switch is a context disruption | Keep agents visible in the primary transcript as labeled inline cells; use existing `AgentMonitorPane` side panel for detailed status |
| Always-visible persistent agent activity log pane | Shows all agent events constantly | Competes with transcript for vertical space; most of the time it shows stale data when no delegation is happening. `AgentMonitorPane` already auto-hides when no agents are active — this is the correct behavior | `AgentMonitorPane` auto-hide is already implemented correctly; do not change this to always-visible |
| Per-agent token streaming with full internal tool call trace | "I want to see every bash command the agent ran" | Sub-agent internal tool calls stay inside the sub-agent conversation by design (Claude Agent SDK architecture); only the final result returns to the orchestrator. Attempting to show intermediate steps requires a parallel monitoring channel not currently provided by the SDK | Route state.json `activity` field or terminal-level hooks to the monitor pane; add drill-down to `.jsonl` file as a future feature |

---

## Feature Dependencies

```
[AgentCell widget]
    └──requires──> [agent_name + agent_role at delegation time]
                       └──requires──> [DelegationStarted carries agent identity]
                                           (currently DelegationStarted only has task_description)
    └──requires──> [AssistantCell streaming lifecycle pattern]
                       (already built — AgentCell reuses or extends it)

[Orchestrator status indicator]
    └──requires──> [DelegationStarted message] (already posted in messages.py)
    └──requires──> [AgentCell or status variant in transcript]
    └──enhances──> [AgentCell] — makes the phase transition visible

[Tool-use event interception]
    └──requires──> [SDK _stream_response already receives StreamEvent with tool_use]
    └──requires──> [Detect conductor_delegate tool calls specifically]
                       (other tool calls should not spawn AgentCells)
    └──requires──> [AgentCell widget] (target to mount when tool_use fires)

[State.json agent updates -> transcript]
    └──requires──> [AgentStateUpdated message] (already posted by AgentMonitorPane watcher)
    └──requires──> [Bridge: app routes AgentStateUpdated to TranscriptPane too]
                       (currently only AgentMonitorPane consumes this message)
    └──requires──> [AgentCell or event cell in TranscriptPane]

[Inline delegation event cells]
    └──requires──> [DelegationStarted message with task_description] (already exists)
    └──enhances──> [AgentCell] — provides context for what the cell represents

[Agent completion summaries inline]
    └──requires──> [AgentStateUpdated -> transcript bridge]
    └──requires──> [Track prior agent states to detect DONE transitions]
    └──enhances──> [AgentCell] — closes the cell with a summary on completion
```

### Dependency Notes

- **AgentCell needs agent identity at delegation time:** `DelegationStarted` currently only carries `task_description`. To show "Agent: frontend-builder (React)" in the cell header, the delegation path must also carry `agent_name` and `agent_role`. This requires modifying `DelegationStarted` or adding a new message.
- **Tool-use interception must distinguish conductor_delegate:** The SDK stream emits `tool_use` events for all tools. Only `conductor_delegate` tool calls should spawn `AgentCell` entries. Other tool calls (file reads, bash) should continue going to the existing `ToolActivity` message path.
- **AgentStateUpdated bridge to transcript:** `AgentMonitorPane` consumes `AgentStateUpdated` but `TranscriptPane` does not. The app (`ConductorApp`) needs to also handle this message and post transcript events. One clean approach: `ConductorApp.on_agent_state_updated()` handles both sinks.
- **DONE transition detection requires prior state tracking:** To detect when an agent transitions from WORKING to DONE, the bridge must compare old state to new state. The app needs to keep a snapshot of the previous agent statuses.

---

## MVP Definition

This is a subsequent milestone on existing shipped code. All four target features from PROJECT.md are MVP.

### Launch With (v2.2)

- [ ] **AgentCell widget** — New `TranscriptPane` cell type extending `AssistantCell` streaming lifecycle with `agent_name`, `agent_role` params; distinct CSS label/border; shimmer during agent work; summary on completion. This is the foundation all other features build on. Complexity: MEDIUM.
- [ ] **Orchestrator status display** — Change the label in the active cell from "Assistant" to "Orchestrator" during planning phase; show a delegation event cell when `DelegationStarted` fires. Complexity: LOW once `AgentCell` exists.
- [ ] **Tool-use event interception** — In `_stream_response`, detect `tool_use` events where `name == "conductor_delegate"`; mount an `AgentCell` in loading state; populate with agent identity from the tool input. Complexity: MEDIUM — requires parsing tool_use input for agent identity.
- [ ] **State.json agent updates -> transcript** — `ConductorApp.on_agent_state_updated()` bridges state changes to transcript: new WORKING agents get an `AgentCell` mounted; DONE transitions get a summary cell. Complexity: MEDIUM — requires prior-state tracking to detect transitions.

### Add After Validation (v2.3+)

- [ ] **Color-coded per-agent identity** — Different tint/accent color per agent role or per agent instance. Trigger: user has more than 2-3 concurrent agents and needs faster visual parsing. Complexity: LOW (CSS only once AgentCell has role data).
- [ ] **Agent completion summary with task output** — Include task `outputs` data in the completion cell. Trigger: user feedback that plain "completed" is insufficient. Complexity: LOW (data already in state.json `Task.outputs`).

### Future Consideration (v3+)

- [ ] **Drill-down to sub-agent transcript** — Link from `AgentCell` to the full sub-agent `.jsonl` transcript file. Trigger: power users debugging agent behavior (explicitly requested in Claude Code issues #9521 and #6007). Complexity: HIGH — requires file browsing UI.
- [ ] **Agent-to-agent message visibility** — Show escalation/coordination messages between agents inline. Trigger: ACP peer-to-peer is out of scope for v1; revisit when direct agent messaging is added. Complexity: HIGH.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| AgentCell widget | HIGH | MEDIUM | P1 |
| Orchestrator status label | HIGH | LOW | P1 |
| Tool-use event -> transcript | HIGH | MEDIUM | P1 |
| State.json agent updates -> transcript | HIGH | MEDIUM | P1 |
| Color-coded per-agent identity | MEDIUM | LOW | P2 |
| Agent completion summary with outputs | MEDIUM | LOW | P2 |
| Drill-down to sub-agent transcript | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Required for v2.2 to deliver "labeled per-agent output streams" goal
- P2: Polish pass — low effort, high return; add when P1 features are stable
- P3: Defer to v3+; valuable but not blocking visibility milestone

---

## Competitor Feature Analysis

| Feature | IttyBitty | Conduit | Claude Code (native) | Codex CLI multi-agent | Conductor v2.2 approach |
|---------|-----------|---------|---------------------|----------------------|-------------------------|
| Agent label display | Separate agent list panel (top) + agent log panel (right) | Tab per agent, tabs labeled with agent name | No multi-agent transcript visibility (issue #9521) | Proposed: colored @handle tags per agent (RFC #12047, not shipped) | Inline labeled `AgentCell` in primary transcript |
| Orchestrator status | Manager vs Worker type label in agent list | N/A (single-agent per tab) | Shows "Claude" regardless of orchestration role | Not yet implemented | Distinct "Orchestrator" label on active cell; changes at delegation |
| Streaming per agent | Watch one agent at a time via `ib watch` | Full stream per tab; switch between tabs | Sub-agent output is invisible by design | Proposed: separate per-agent output buffers | Inline streaming in `AgentCell` mounted at delegation time |
| Concurrent agent visibility | Separate side panels (spatial layout) | Tab switching | None | Not yet implemented | `AgentMonitorPane` side panel (existing) + inline transcript events |
| Agent completion events | `ib list` / `ib tree` CLI commands | Tab status badge updates | `SubagentStop` hook (prints to STDOUT only) | Not yet implemented | Inline completion cell in transcript when state.json shows DONE |

The defining choice for Conductor is **inline-in-transcript over separate panel/tab**, which preserves the conversation-centric mental model users already understand, avoids context switching, and builds on the existing `AssistantCell` streaming infrastructure.

---

## Sources

- Codebase: `/packages/conductor-core/src/conductor/tui/widgets/transcript.py` — HIGH confidence; direct inspection confirms `AssistantCell` streaming lifecycle, shimmer, `TranscriptPane` mount methods
- Codebase: `/packages/conductor-core/src/conductor/tui/widgets/agent_monitor.py` — HIGH confidence; confirms `AgentStateUpdated` consumption path, `AgentPanel` structure
- Codebase: `/packages/conductor-core/src/conductor/tui/messages.py` — HIGH confidence; confirms `DelegationStarted`, `ToolActivity`, `AgentStateUpdated` already exist; `DelegationStarted` lacks agent identity fields
- Codebase: `/packages/conductor-core/src/conductor/tui/app.py` — HIGH confidence; confirms `_stream_response` receives `StreamEvent` including tool_use events; `ToolActivity` is posted but not routed to a transcript cell
- Codebase: `/packages/conductor-core/src/conductor/state/models.py` — HIGH confidence; confirms `AgentRecord.name`, `AgentRecord.role`, `AgentStatus` enum with DONE state
- [Claude Code issue #9521: Support for inspecting subagent output](https://github.com/anthropics/claude-code/issues/9521) — MEDIUM confidence; confirms industry-wide pain point
- [Claude Code issue #6007: View and navigate sub-agent task sessions](https://github.com/anthropics/claude-code/issues/6007) — MEDIUM confidence; confirms users want transcript-level agent visibility
- [Codex multi-agent TUI RFC #12047](https://github.com/openai/codex/issues/12047) — MEDIUM confidence; confirms colored @handle tags pattern, rejection of interleaved output
- [IttyBitty multi-agent Claude Code TUI](https://adamwulf.me/2026/01/itty-bitty-ai-agent-orchestrator/) — MEDIUM confidence; confirms manager/worker label + side panel pattern
- [Conduit multi-agent TUI](https://getconduit.sh/) — MEDIUM confidence; confirms tab-per-agent as alternative pattern Conductor explicitly avoids
- [Claude Agent SDK subagents docs](https://platform.claude.com/docs/en/agent-sdk/subagents) — HIGH confidence; confirms sub-agent final-message-only return architecture

---
*Feature research for: Conductor v2.2 agent visibility (labeled per-agent output streams in TUI transcript)*
*Researched: 2026-03-12*
