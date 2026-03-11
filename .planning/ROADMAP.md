# Roadmap: Conductor

## Milestones

- ✅ **v1.0 MVP** — Phases 1-17 (shipped 2026-03-11)
- ✅ **v1.1 Interactive Chat TUI** — Phases 18-22 (completed 2026-03-11)
- ✅ **v1.2 Task Verification & Build Safety** — Phases 23-25 (completed 2026-03-11)
- ✅ **v1.3 Orchestrator Intelligence** — Phases 26-30 (completed 2026-03-11)
- ✅ **v2.0 Textual TUI Redesign** — Phases 31-38 (completed 2026-03-11)
- ✅ **v2.1 UX Polish** — Phases 39-42 (shipped 2026-03-12)
- 🚧 **v2.2 Agent Visibility** — Phases 43-46 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-17) — SHIPPED 2026-03-11</summary>

- [x] Phase 1: Monorepo Foundation (2/2 plans) — completed 2026-03-10
- [x] Phase 2: Shared State Infrastructure (2/2 plans) — completed 2026-03-10
- [x] Phase 3: ACP Communication Layer (2/2 plans) — completed 2026-03-10
- [x] Phase 4: Orchestrator Core (3/3 plans) — completed 2026-03-10
- [x] Phase 5: Orchestrator Intelligence (2/2 plans) — completed 2026-03-10
- [x] Phase 6: Escalation and Intervention (2/2 plans) — completed 2026-03-10
- [x] Phase 7: Agent Runtime (3/3 plans) — completed 2026-03-10
- [x] Phase 8: CLI Interface (2/2 plans) — completed 2026-03-10
- [x] Phase 9: Dashboard Backend (2/2 plans) — completed 2026-03-10
- [x] Phase 10: Dashboard Frontend (3/3 plans) — completed 2026-03-10
- [x] Phase 11: Packaging and Distribution (2/2 plans) — completed 2026-03-10
- [x] Phase 12: Fix CLI Cancel/Redirect Signatures (1/1 plan) — completed 2026-03-11
- [x] Phase 13: Wire Escalation Router + Pause Surface (2/2 plans) — completed 2026-03-11
- [x] Phase 14: Fix Getting-Started Guide .env Claim (1/1 plan) — completed 2026-03-11
- [x] Phase 15: Fix Dashboard Server Cancel Type Mismatch (1/1 plan) — completed 2026-03-11
- [x] Phase 16: Fix Agent Status Lifecycle (1/1 plan) — completed 2026-03-11
- [x] Phase 17: Fix Production WebSocket URL (1/1 plan) — completed 2026-03-11

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v1.1 Interactive Chat TUI (Phases 18-22) — COMPLETED 2026-03-11</summary>

- [x] **Phase 18: CLI Foundation and Input Layer** — completed 2026-03-11
- [x] **Phase 19: Streaming Display and Session Lifecycle** — completed 2026-03-11
- [x] **Phase 20: Session Resumption** — completed 2026-03-11
- [x] **Phase 21: Smart Delegation and Orchestrator Integration** — completed 2026-03-11
- [x] **Phase 22: Sub-Agent Visibility and Escalation Bridge** — completed 2026-03-11

</details>

<details>
<summary>✅ v1.2 Task Verification & Build Safety (Phases 23-25) — COMPLETED 2026-03-11</summary>

- [x] **Phase 23: Resume Robustness** — completed 2026-03-11
- [x] **Phase 24: Task Verification and Quality Loops** — completed 2026-03-11
- [x] **Phase 25: Post-Run Build Verification** — completed 2026-03-11

</details>

<details>
<summary>✅ v1.3 Orchestrator Intelligence (Phases 26-30) — COMPLETED 2026-03-11</summary>

- [x] **Phase 26: Models & Scheduler Infrastructure** — completed 2026-03-11
- [x] **Phase 27: Execution & Routing Pipeline** — completed 2026-03-11
- [x] **Phase 28: Agent Communication Protocol** — completed 2026-03-11
- [x] **Phase 29: Verification & Review Pipeline** — completed 2026-03-11
- [x] **Phase 30: Smart Decomposition** — completed 2026-03-11

</details>

<details>
<summary>✅ v2.0 Textual TUI Redesign (Phases 31-38) — COMPLETED 2026-03-11</summary>

- [x] **Phase 31: TUI Foundation** — completed 2026-03-11
- [x] **Phase 32: Static TUI Shell** — completed 2026-03-11
- [x] **Phase 33: SDK Streaming** — completed 2026-03-11
- [x] **Phase 34: Rich Output** — completed 2026-03-11
- [x] **Phase 35: Agent Monitoring** — completed 2026-03-11
- [x] **Phase 36: Approval Modals** — completed 2026-03-11
- [x] **Phase 37: Slash Commands & Dashboard Coexistence** — completed 2026-03-11
- [x] **Phase 38: Session Persistence & Polish** — completed 2026-03-11

</details>

<details>
<summary>✅ v2.1 UX Polish (Phases 39-42) — SHIPPED 2026-03-12</summary>

- [x] **Phase 39: Auto-Focus & Alt-Screen** — completed 2026-03-11
- [x] **Phase 40: Borderless Design** — completed 2026-03-11
- [x] **Phase 41: Smooth Cell Animations** — completed 2026-03-11
- [x] **Phase 42: Ctrl-G External Editor** — completed 2026-03-12

Full details: `.planning/milestones/v2.1-ROADMAP.md`

</details>

### v2.2 Agent Visibility (In Progress)

**Milestone Goal:** Surface real-time agent activity in the TUI transcript — labeled per-agent cells with name, role, and status; orchestrator status during planning/delegation; tool-use event interception from SDK stream; and state.json agent updates feeding the transcript.

- [x] **Phase 43: Agent Cell Widgets** - Create AgentCell and OrchestratorStatusCell widget classes with full lifecycle (completed 2026-03-11)
- [x] **Phase 44: TranscriptPane Extensions and State Bridge** - Extend TranscriptPane with agent_cells registry and state.json fan-out (completed 2026-03-11)
- [x] **Phase 45: SDK Stream Interception and Orchestrator Status** - Wire stream loop to detect conductor_delegate and show orchestrator phase labels (completed 2026-03-11)
- [ ] **Phase 46: Visual Polish and Verification** - CSS accent colors, inline delegation event cells, agent completion summaries, pitfall checklist

## Phase Details

### Phase 43: Agent Cell Widgets
**Goal**: AgentCell and OrchestratorStatusCell widget classes exist with full lifecycle methods, correct CSS styling, and safe widget IDs — enabling all subsequent phases to build on them
**Depends on**: Phase 42 (existing transcript.py widget patterns)
**Requirements**: ACELL-04
**Success Criteria** (what must be TRUE):
  1. An AgentCell widget can be mounted in the transcript showing agent name, role, and task title in a labeled badge header
  2. AgentCell.update_status() transitions the cell display (working shimmer → waiting → done) without errors
  3. AgentCell.finalize() works correctly whether or not streaming was ever started (defensive finalize)
  4. OrchestratorStatusCell can be created, updated, and finalized as an ephemeral status cell
  5. Multiple AgentCells with different agent_id values render independently with no CSS ID collisions (sanitized IDs with distinct prefixes)
**Plans**: 1 plan
Plans:
- [x] 43-01-PLAN.md — TDD: AgentCell + OrchestratorStatusCell widgets

### Phase 44: TranscriptPane Extensions and State Bridge
**Goal**: TranscriptPane receives AgentStateUpdated messages from the state.json watcher and mounts AgentCells for new WORKING agents, updating and finalizing them as state transitions occur
**Depends on**: Phase 43
**Requirements**: BRDG-01, BRDG-02, ACELL-01, ACELL-02, ACELL-03
**Success Criteria** (what must be TRUE):
  1. When a new agent transitions to WORKING in state.json, a labeled AgentCell appears in the transcript showing the agent name, role, and task title
  2. When an agent's status changes (working → waiting → done), the AgentCell in the transcript updates to reflect the new state
  3. When an agent reaches DONE, the AgentCell shows a completion summary with final status
  4. The transcript maintains a _agent_cells dict so each agent_id maps to exactly one cell — no duplicate cells created for the same agent across state updates
  5. Scroll position is preserved when new AgentCells are mounted while the user has scrolled up (no jump to bottom)
**Plans**: 1 plan
Plans:
- [ ] 44-01-PLAN.md — TDD: TranscriptPane state bridge and AgentCell lifecycle

### Phase 45: SDK Stream Interception and Orchestrator Status
**Goal**: The SDK stream loop detects conductor_delegate tool-use events, creates OrchestratorStatusCells, and changes the active cell label from "Assistant" to "Orchestrator" during delegation phases
**Depends on**: Phase 44
**Requirements**: STRM-01, STRM-02, ORCH-01, ORCH-02
**Success Criteria** (what must be TRUE):
  1. When the orchestrator enters a planning/delegation phase, the active cell label in the transcript changes from "Assistant" to "Orchestrator — delegating" (not just "Assistant")
  2. When conductor_delegate tool-use fires, an OrchestratorStatusCell appears in the transcript showing which agents were spawned and what tasks they received
  3. Tool-use input (task description, agent config) accumulated across input_json_delta events is correctly parsed — the delegation cell shows real task content, not empty labels
  4. The SDK stream loop continues receiving events without stutter — widget creation uses post_message, not await mount
**Plans**: 1 plan
Plans:
- [ ] 45-01-PLAN.md — TDD: SDK stream interception and orchestrator status

### Phase 46: Visual Polish and Verification
**Goal**: Agent and orchestrator cells are visually distinct with accent colors, inline delegation event cells orient the user between stream and state-driven phases, and all pitfall checklist items are verified
**Depends on**: Phase 45
**Requirements**: (no new requirements — polish and verification pass)
**Success Criteria** (what must be TRUE):
  1. AgentCell and OrchestratorStatusCell have visually distinct CSS accent colors that differentiate them from AssistantCell (CSS-only change)
  2. A brief inline delegation event cell appears in the transcript before sub-agent cells, keeping the user oriented without requiring side-panel attention
  3. Agent completion cells include the final task summary so the user can see what each agent delivered
  4. With 3+ concurrent agents active, shimmer timers are cleaned up on finalize and no lingering animations remain after all agents complete
**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Monorepo Foundation | v1.0 | 2/2 | Complete | 2026-03-10 |
| 2. Shared State Infrastructure | v1.0 | 2/2 | Complete | 2026-03-10 |
| 3. ACP Communication Layer | v1.0 | 2/2 | Complete | 2026-03-10 |
| 4. Orchestrator Core | v1.0 | 3/3 | Complete | 2026-03-10 |
| 5. Orchestrator Intelligence | v1.0 | 2/2 | Complete | 2026-03-10 |
| 6. Escalation and Intervention | v1.0 | 2/2 | Complete | 2026-03-10 |
| 7. Agent Runtime | v1.0 | 3/3 | Complete | 2026-03-10 |
| 8. CLI Interface | v1.0 | 2/2 | Complete | 2026-03-10 |
| 9. Dashboard Backend | v1.0 | 2/2 | Complete | 2026-03-10 |
| 10. Dashboard Frontend | v1.0 | 3/3 | Complete | 2026-03-10 |
| 11. Packaging and Distribution | v1.0 | 2/2 | Complete | 2026-03-10 |
| 12. Fix CLI Cancel/Redirect | v1.0 | 1/1 | Complete | 2026-03-11 |
| 13. Wire Escalation + Pause | v1.0 | 2/2 | Complete | 2026-03-11 |
| 14. Fix Getting-Started .env | v1.0 | 1/1 | Complete | 2026-03-11 |
| 15. Fix Dashboard Cancel Type | v1.0 | 1/1 | Complete | 2026-03-11 |
| 16. Fix Agent Status Lifecycle | v1.0 | 1/1 | Complete | 2026-03-11 |
| 17. Fix Production WebSocket URL | v1.0 | 1/1 | Complete | 2026-03-11 |
| 18. CLI Foundation and Input Layer | v1.1 | 1/1 | Complete | 2026-03-11 |
| 19. Streaming Display and Session Lifecycle | v1.1 | 1/1 | Complete | 2026-03-11 |
| 20. Session Resumption | v1.1 | 1/1 | Complete | 2026-03-11 |
| 21. Smart Delegation and Orchestrator Integration | v1.1 | 1/1 | Complete | 2026-03-11 |
| 22. Sub-Agent Visibility and Escalation Bridge | v1.1 | 1/1 | Complete | 2026-03-11 |
| 23. Resume Robustness | v1.2 | 1/1 | Complete | 2026-03-11 |
| 24. Task Verification and Quality Loops | v1.2 | 1/1 | Complete | 2026-03-11 |
| 25. Post-Run Build Verification | v1.2 | 1/1 | Complete | 2026-03-11 |
| 26. Models & Scheduler Infrastructure | v1.3 | 1/1 | Complete | 2026-03-11 |
| 27. Execution & Routing Pipeline | v1.3 | 1/1 | Complete | 2026-03-11 |
| 28. Agent Communication Protocol | v1.3 | 1/1 | Complete | 2026-03-11 |
| 29. Verification & Review Pipeline | v1.3 | 2/2 | Complete | 2026-03-11 |
| 30. Smart Decomposition | v1.3 | 1/1 | Complete | 2026-03-11 |
| 31. TUI Foundation | v2.0 | 1/1 | Complete | 2026-03-11 |
| 32. Static TUI Shell | v2.0 | 1/1 | Complete | 2026-03-11 |
| 33. SDK Streaming | v2.0 | 2/2 | Complete | 2026-03-11 |
| 34. Rich Output | v2.0 | 1/1 | Complete | 2026-03-11 |
| 35. Agent Monitoring | v2.0 | 1/1 | Complete | 2026-03-11 |
| 36. Approval Modals | v2.0 | 2/2 | Complete | 2026-03-11 |
| 37. Slash Commands & Dashboard Coexistence | v2.0 | 1/1 | Complete | 2026-03-11 |
| 38. Session Persistence & Polish | v2.0 | 1/1 | Complete | 2026-03-11 |
| 39. Auto-Focus & Alt-Screen | v2.1 | 1/1 | Complete | 2026-03-11 |
| 40. Borderless Design | v2.1 | 1/1 | Complete | 2026-03-11 |
| 41. Smooth Cell Animations | v2.1 | 1/1 | Complete | 2026-03-11 |
| 42. Ctrl-G External Editor | v2.1 | 1/1 | Complete | 2026-03-12 |
| 43. Agent Cell Widgets | v2.2 | 1/1 | Complete | 2026-03-11 |
| 44. TranscriptPane Extensions and State Bridge | 1/1 | Complete    | 2026-03-11 | - |
| 45. SDK Stream Interception and Orchestrator Status | 1/1 | Complete    | 2026-03-11 | - |
| 46. Visual Polish and Verification | v2.2 | 0/? | Not started | - |
