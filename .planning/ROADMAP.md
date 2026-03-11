# Roadmap: Conductor

## Milestones

- ✅ **v1.0 MVP** — Phases 1-17 (shipped 2026-03-11)
- 🚧 **v1.1 Interactive Chat TUI** — Phases 18-22 (in progress)

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

### 🚧 v1.1 Interactive Chat TUI (In Progress)

**Milestone Goal:** Add an interactive conversational TUI so users can chat with the orchestrator like a coding agent CLI — direct tool use for simple tasks, smart sub-agent delegation for complex work, accessible via `conductor` with no arguments.

- [ ] **Phase 18: CLI Foundation and Input Layer** — Fix entry point, adopt prompt_toolkit, wire safe terminal lifecycle
- [ ] **Phase 19: Streaming Display and Session Lifecycle** — Stream tokens, show tool activity, persist chat history, warn on context exhaustion
- [ ] **Phase 20: Session Resumption** — Resume prior sessions by timestamp selection via `conductor --resume`
- [ ] **Phase 21: Smart Delegation and Orchestrator Integration** — Direct tool use for simple tasks, sub-agent spawning for complex work, visible delegation decisions
- [ ] **Phase 22: Sub-Agent Visibility and Escalation Bridge** — Live per-agent status lines during delegation, escalation questions surfaced in chat

## Phase Details

### Phase 18: CLI Foundation and Input Layer
**Goal**: Users can open an interactive chat session by running `conductor` with no arguments, type and submit prompts with full input control (history, multiline, interrupt), and use basic slash commands to navigate
**Depends on**: Phase 17 (v1.0 complete)
**Requirements**: CHAT-01, CHAT-03, CHAT-04, CHAT-05, SESS-01, SESS-02
**Success Criteria** (what must be TRUE):
  1. Running `conductor` with no arguments opens an interactive input prompt instead of showing help text
  2. Pressing Up/Down arrow keys cycles through prompts submitted earlier in the current session
  3. Pasting multi-line text into the prompt does not submit prematurely — user must press Enter on an empty line or a designated submit key
  4. First Ctrl+C while a response is running stops the agent and returns to the prompt with a cancellation notice; second Ctrl+C in quick succession exits the TUI cleanly
  5. `/help` displays all slash commands with descriptions; `/exit` terminates cleanly and restores the terminal to its pre-launch state
**Plans**: TBD

### Phase 19: Streaming Display and Session Lifecycle
**Goal**: Users see orchestrator responses rendered token-by-token as they arrive, with a working indicator before the first token, human-readable tool activity lines, and a warning when context is running low — and all of this survives crashes because chat history is persisted to disk
**Depends on**: Phase 18
**Requirements**: CHAT-02, CHAT-06, CHAT-07, CHAT-08, SESS-05
**Success Criteria** (what must be TRUE):
  1. Orchestrator response tokens appear incrementally in the chat as they are generated — the user never waits for the full response before seeing output
  2. A spinner or working indicator is visible from the moment a prompt is submitted until the first response token appears
  3. Each direct tool invocation (file read, file edit, shell command) shows a human-readable status line in the chat (e.g. "Reading src/auth.py...") rather than raw JSON
  4. When conversation context reaches approximately 75% utilization, the user receives a warning with an option to summarize and continue
  5. Chat history written to disk so that a subsequent `conductor --resume` can restore it after a crash or process kill
**Plans**: TBD

### Phase 20: Session Resumption
**Goal**: Users can resume a prior chat session from exactly where they left off — conversation history is restored before the input prompt activates — so context is never lost across restarts
**Depends on**: Phase 19
**Requirements**: SESS-04
**Success Criteria** (what must be TRUE):
  1. Running `conductor --resume` shows a numbered list of recent sessions with timestamp and first prompt text for each
  2. Selecting a session from the list restores the full conversation history in the chat before the input prompt activates
  3. Resuming a session that was active during a crash or kill recovers all turns that were persisted before the interruption
**Plans**: TBD

### Phase 21: Smart Delegation and Orchestrator Integration
**Goal**: The orchestrator handles simple coding tasks (file edits, shell commands) directly in-context and transparently delegates complex tasks to a sub-agent team — every request produces a visible delegation decision before work begins
**Depends on**: Phase 19
**Requirements**: DELG-01, DELG-02, DELG-03, DELG-04, SESS-03
**Success Criteria** (what must be TRUE):
  1. A simple request (e.g. "rename variable X to Y in auth.py") completes via direct file edit with no delegation announcement or sub-agent overhead
  2. A complex request (e.g. "add OAuth login") triggers a "Delegating to team..." announcement and spawns a sub-agent team via the existing orchestrator
  3. Every request — simple or complex — produces a visible decision line ("Handling directly" or "Delegating to team") before any work begins
  4. When sub-agents are spawned, the delegation announcement includes the dashboard URL
  5. `/status` displays a table of active sub-agents with ID, task, and elapsed time; shows "No active agents" when none are running
**Plans**: TBD

### Phase 22: Sub-Agent Visibility and Escalation Bridge
**Goal**: Users can see live per-agent progress during delegation without switching to the dashboard, and escalation questions from sub-agents surface directly in the chat with the agent ID so users can reply without leaving the TUI
**Depends on**: Phase 21
**Requirements**: VISB-01, VISB-02
**Success Criteria** (what must be TRUE):
  1. While sub-agents are active, the chat displays a per-agent status line that updates as each agent progresses through its task
  2. When all sub-agents complete, the per-agent status lines are removed from the chat display
  3. When a sub-agent escalates a question, it appears in the chat prefixed with the agent ID and the input field activates immediately so the user can reply without any additional steps
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 18 → 19 → 20 → 21 → 22

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
| 18. CLI Foundation and Input Layer | v1.1 | 0/? | Not started | - |
| 19. Streaming Display and Session Lifecycle | v1.1 | 0/? | Not started | - |
| 20. Session Resumption | v1.1 | 0/? | Not started | - |
| 21. Smart Delegation and Orchestrator Integration | v1.1 | 0/? | Not started | - |
| 22. Sub-Agent Visibility and Escalation Bridge | v1.1 | 0/? | Not started | - |
