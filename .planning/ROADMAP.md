# Roadmap: Conductor

## Overview

Conductor is built from the ground up: shared state foundation first (preventing the concurrent-write corruption pitfall before any agents run), then the ACP communication layer, then orchestrator intelligence, then CLI validation of the end-to-end loop, then the dashboard backend and frontend, and finally packaging for distribution. Every phase delivers a coherent, testable capability. The CLI produces a working multi-agent product by Phase 8; Phases 9-11 add the web dashboard and make the system installable anywhere.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Monorepo Foundation** - Python + Node.js monorepo scaffold with CI, linting, and project structure (completed 2026-03-10)
- [x] **Phase 2: Shared State Infrastructure** - Safe `.conductor/state.json` with file-locked reads/writes and Pydantic models (completed 2026-03-10)
- [x] **Phase 3: ACP Communication Layer** - ACP client/server runtime with permission flow, timeout, and safe defaults (completed 2026-03-10)
- [x] **Phase 4: Orchestrator Core** - Orchestrator agent that plans, decomposes, delegates, and manages file ownership (completed 2026-03-10)
- [ ] **Phase 5: Orchestrator Intelligence** - Real-time sub-agent monitoring, output review, and feedback loops
- [x] **Phase 6: Escalation and Intervention** - Auto/interactive mode logic, cancel, inject-mid-stream, and pause/escalate (completed 2026-03-10)
- [x] **Phase 7: Agent Runtime** - Context inheritance, shared memory, session persistence, and dynamic team sizing (completed 2026-03-10)
- [x] **Phase 8: CLI Interface** - Terminal interface for chatting with orchestrator, viewing agent status, and intervening (completed 2026-03-10)
- [ ] **Phase 9: Dashboard Backend** - State watcher, WebSocket broadcast server, and server-side event filtering
- [x] **Phase 10: Dashboard Frontend** - React dashboard with layered visibility, live stream, and intervention controls (completed 2026-03-10)
- [x] **Phase 11: Packaging and Distribution** - pip and npm packages with installation and getting-started guide (completed 2026-03-10)
- [x] **Phase 12: Fix CLI Cancel/Redirect Signatures** - Fix cancel_agent() signature mismatch and redirect command parameter errors (gap closure) (completed 2026-03-11)
- [x] **Phase 13: Wire Escalation Router + Pause Surface** - Connect EscalationRouter to ACPClient and add pause command to CLI/dashboard (gap closure) (completed 2026-03-11)
- [x] **Phase 14: Fix Getting-Started Guide .env Claim** - Remove or implement .env auto-loading claim in getting-started guide (gap closure) (completed 2026-03-11)
- [x] **Phase 15: Fix Dashboard Server Cancel Type Mismatch** - Fix server.py passing TaskSpec instead of str|None to cancel_agent (gap closure) (completed 2026-03-11)
- [ ] **Phase 16: Fix Agent Status Lifecycle** - Add DONE and WAITING status mutations to orchestrator (gap closure)
- [ ] **Phase 17: Fix Production WebSocket URL** - Add runtime backend URL configuration for production deployment (gap closure)

## Phase Details

### Phase 1: Monorepo Foundation
**Goal**: A developer can clone the repo, install dependencies, and confirm the project structure works — both Python core and Node.js dashboard sides are wired together in one monorepo
**Depends on**: Nothing (first phase)
**Requirements**: PKG-03
**Success Criteria** (what must be TRUE):
  1. `uv sync` in the Python core directory installs all dependencies without errors
  2. `pnpm install` in the dashboard directory installs all dependencies without errors
  3. Python linting and type checking pass on an empty module scaffold
  4. A `conductor --help` command runs without errors (even if it does nothing yet)
  5. CI runs both Python and Node.js checks on every push
**Plans:** 2/2 plans complete
Plans:
- [ ] 01-01-PLAN.md — Root configs + Python package scaffold with CLI entry point
- [ ] 01-02-PLAN.md — Dashboard scaffold (Vite/React/Tailwind/Biome) + CI workflow

### Phase 2: Shared State Infrastructure
**Goal**: A `.conductor/state.json` file can be safely read and written by multiple processes without corruption — the single coordination backbone is reliable before any agent touches it
**Depends on**: Phase 1
**Requirements**: CORD-01, CORD-02, CORD-03, CORD-06
**Success Criteria** (what must be TRUE):
  1. A Task, Agent, and Dependency record can be written to `state.json` and read back with full fidelity
  2. Concurrent writes from two processes do not corrupt `state.json` (filelock prevents races)
  3. Orchestrator can write a task assignment and a sub-agent can read it from the same state file
  4. Sub-agent can update its own task status and the orchestrator can observe the change
  5. All agents can read the full task list and see every other agent's current task and status
**Plans:** 2/2 plans complete
Plans:
- [ ] 02-01-PLAN.md — Dependencies + Pydantic models, enums, and error classes
- [ ] 02-02-PLAN.md — StateManager with file-locked atomic read/write (TDD)

### Phase 3: ACP Communication Layer
**Goal**: The orchestrator can open an ACP session to a sub-agent, send messages, receive streamed responses, and answer sub-agent questions — with permission prompts handled safely and without deadlock
**Depends on**: Phase 2
**Requirements**: COMM-01, COMM-02
**Success Criteria** (what must be TRUE):
  1. Orchestrator can spawn a sub-agent via ACP and receive its streamed tool calls in real time
  2. Sub-agent can send a question (permission prompt, clarification) and receive an answer from the orchestrator
  3. A permission prompt that receives no response within the timeout resolves to a safe default (deny) rather than hanging
  4. Orchestrator can open, use, and close an ACP session without resource leaks
**Plans:** 2/2 plans complete
Plans:
- [ ] 03-01-PLAN.md — ACP error hierarchy + PermissionHandler with timeout safe-default (TDD)
- [ ] 03-02-PLAN.md — ACPClient wrapping ClaudeSDKClient with session lifecycle (TDD)

### Phase 4: Orchestrator Core
**Goal**: The orchestrator can take a feature description, decompose it into discrete tasks, spawn sub-agents with identities (name, role, target, materials), manage task dependencies, and prevent concurrent file edit conflicts
**Depends on**: Phase 3
**Requirements**: ORCH-01, ORCH-02, ORCH-06, CORD-04, CORD-05
**Success Criteria** (what must be TRUE):
  1. Orchestrator receives a feature description and produces a task list with explicit dependency declarations (requires/produces)
  2. Orchestrator spawns a sub-agent with a complete identity: name, role, target file/component, and material files
  3. Orchestrator assigns file ownership to agents before work begins — no two agents are assigned overlapping files
  4. Orchestrator sequences or parallelizes tasks correctly based on declared dependencies
  5. Orchestrator enforces a `max_agents` cap and does not exceed it during execution
**Plans:** 3/3 plans complete
Plans:
- [ ] 04-01-PLAN.md — Orchestrator types: error hierarchy, TaskSpec/TaskPlan models, AgentIdentity, Task model extension
- [ ] 04-02-PLAN.md — DependencyScheduler (graphlib) + file ownership validation (TDD)
- [ ] 04-03-PLAN.md — TaskDecomposer (SDK structured output) + Orchestrator main class

### Phase 5: Orchestrator Intelligence
**Goal**: The orchestrator monitors sub-agent work in real time, reviews completed output for quality and coherence, and can request revisions before marking a task complete
**Depends on**: Phase 4
**Requirements**: ORCH-03, ORCH-04, ORCH-05
**Success Criteria** (what must be TRUE):
  1. Orchestrator sees sub-agent tool calls and file edits as they happen via ACP streaming (not just at completion)
  2. When a sub-agent completes a task, the orchestrator reviews the output and either approves or requests changes
  3. Orchestrator can send structured feedback to a sub-agent and the sub-agent revises accordingly
  4. A task is only marked complete after orchestrator review passes — not immediately when the sub-agent reports done
**Plans:** 1/2 plans executed
Plans:
- [ ] 05-01-PLAN.md — StreamMonitor + ReviewVerdict/review_output + state model extension (TDD)
- [ ] 05-02-PLAN.md — Wire _run_agent_loop into Orchestrator with observe-review-revise cycle (TDD)

### Phase 6: Escalation and Intervention
**Goal**: The orchestrator handles sub-agent questions and intervention commands correctly in both `--auto` and interactive modes — questions get answered, work can be cancelled or redirected, and critical decisions reach the human when needed
**Depends on**: Phase 5
**Requirements**: COMM-03, COMM-04, COMM-05, COMM-06, COMM-07
**Success Criteria** (what must be TRUE):
  1. In `--auto` mode, the orchestrator answers sub-agent questions using project context and logs its decisions — the human is never interrupted
  2. In interactive mode, the orchestrator escalates questions it cannot confidently answer to the human via the CLI
  3. The orchestrator can cancel a sub-agent's current work and reassign it with corrected instructions
  4. The orchestrator can inject a guidance message to a running sub-agent without stopping or restarting it
  5. The orchestrator can pause a sub-agent and present the human with a decision prompt before resuming
**Plans:** 2/2 plans complete
Plans:
- [ ] 06-01-PLAN.md — EscalationRouter with auto/interactive mode routing + error types (TDD)
- [ ] 06-02-PLAN.md — Orchestrator intervention methods: cancel, inject, pause/resume (TDD)

### Phase 7: Agent Runtime
**Goal**: Agents reliably inherit repository context, persist knowledge across sessions, survive restarts, and the orchestrator dynamically sizes the team based on work complexity
**Depends on**: Phase 6
**Requirements**: RUNT-01, RUNT-02, RUNT-03, RUNT-04, RUNT-05, RUNT-06
**Success Criteria** (what must be TRUE):
  1. A sub-agent spawned in a repo with `.claude/` and `CLAUDE.md` picks up those files without any extra configuration
  2. Any agent can write to `.memory/[agent-id].md` and another agent (or the orchestrator) can read it in a later session
  3. After killing and restarting Conductor mid-session, the orchestrator resumes where it left off — task progress and agent assignments are not lost
  4. In `--auto` mode, the orchestrator starts fully autonomous after an upfront spec review — it does not ask the human questions during execution
  5. In interactive mode, the orchestrator pauses and asks the human when it encounters ambiguity
  6. The orchestrator spawns 1-N sub-agents based on task decomposition complexity — not a fixed user-configured count
**Plans:** 3/3 plans complete
Plans:
- [ ] 07-01-PLAN.md — State model extensions, memory-aware system prompt, ACPClient defaults, max_agents=10
- [ ] 07-02-PLAN.md — ACPClient resume parameter + SessionRegistry for session persistence
- [ ] 07-03-PLAN.md — Orchestrator mode wiring, .memory/ creation, session resume, pre_run_review

### Phase 8: CLI Interface
**Goal**: A developer can run `conductor` from the terminal, describe a feature, watch agents work, and intervene (cancel, redirect, feedback) — without needing the web dashboard
**Depends on**: Phase 7
**Requirements**: CLI-01, CLI-02, CLI-03
**Success Criteria** (what must be TRUE):
  1. `conductor run "add dark mode to the settings page"` starts the orchestrator and shows agent activity in the terminal
  2. The terminal displays each agent's name, role, and current task status in a live-updating view
  3. The user can type a CLI command to cancel an agent, redirect it with new instructions, or inject feedback — and the change takes effect without restarting the session
**Plans:** 2/2 plans complete
Plans:
- [ ] 08-01-PLAN.md — Typer app + Rich Live agent display + run/status commands
- [ ] 08-02-PLAN.md — Input loop + intervention commands (cancel, feedback, redirect)

### Phase 9: Dashboard Backend
**Goal**: A FastAPI server streams real-time agent state changes to connected dashboard clients over WebSocket — with server-side event filtering that prevents raw ACP log dumps from overwhelming the client
**Depends on**: Phase 8
**Requirements**: DASH-04
**Success Criteria** (what must be TRUE):
  1. The dashboard backend starts alongside Conductor and is reachable at a local URL
  2. When agent state changes (task assigned, status updated, task completed), the WebSocket client receives a delta event within 1 second
  3. Smart notification events (errors, completions, intervention needed) are identified and flagged server-side — the client does not filter raw events
  4. A new WebSocket client connecting mid-session receives the full current state via REST before receiving incremental updates
**Plans:** 1/2 plans executed
Plans:
- [ ] 09-01-PLAN.md — EventType, DeltaEvent, classify_delta with smart notification flags (TDD)
- [ ] 09-02-PLAN.md — FastAPI server, WebSocket broadcast, state watcher, CLI --dashboard-port flag

### Phase 10: Dashboard Frontend
**Goal**: The web dashboard gives a developer full visibility into all running agents with layered detail — collapsed summary by default, expandable to recent actions, expandable further to live stream — and supports interventions without leaving the browser
**Depends on**: Phase 9
**Requirements**: DASH-01, DASH-02, DASH-03, DASH-05, DASH-06
**Success Criteria** (what must be TRUE):
  1. The dashboard shows every active agent as a card with name, role, current task, and progress — all visible at a glance without scrolling on a typical monitor at 5 agents
  2. Clicking an agent card expands it to show recent actions, files modified, and current activity
  3. Expanding further opens the live stream: real-time tool calls and streaming output as they happen
  4. Verbose agent conversation is collapsed by default — the developer sees summaries, not raw logs, until they choose to expand
  5. The developer can cancel, redirect, or send feedback to an agent directly from the dashboard without touching the CLI
**Plans:** 3/3 plans complete
Plans:
- [ ] 10-01-PLAN.md — Test infra, TypeScript types, Vite proxy, backend intervention extension
- [ ] 10-02-PLAN.md — WebSocket hook, StatusBadge, AgentCard, AgentGrid, App layout
- [ ] 10-03-PLAN.md — Detail view, LiveStream, InterventionPanel, NotificationProvider

### Phase 11: Packaging and Distribution
**Goal**: Conductor can be installed into any repository with `pip install conductor-ai` and `npm install -g conductor-dashboard` — and a developer who has never seen the project can get it running from the getting-started guide
**Depends on**: Phase 10
**Requirements**: PKG-01, PKG-02, PKG-04
**Success Criteria** (what must be TRUE):
  1. `pip install conductor-ai` in a fresh virtual environment installs the CLI and Python core with no errors
  2. `npm install -g conductor-dashboard` installs the dashboard package with no errors
  3. A developer following only the getting-started guide (no prior knowledge of the codebase) can run their first multi-agent session
  4. Both packages have correct version metadata and are installable from their respective registries (PyPI / npm)
**Plans:** 2/2 plans complete
Plans:
- [ ] 11-01-PLAN.md — Python PyPI metadata + npm distribution config + LICENSE + READMEs
- [ ] 11-02-PLAN.md — Getting-started guide + human verification of builds

### Phase 12: Fix CLI Cancel/Redirect Signatures
**Goal:** CLI cancel and redirect commands execute without TypeError — cancel_agent() accepts the arguments the CLI actually passes, and redirect constructs valid parameters
**Depends on**: Phase 8, Phase 6
**Requirements:** CLI-01, CLI-03, COMM-05
**Gap Closure:** Closes CLI-CANCEL-SIGNATURE, CLI-REDIRECT-SIGNATURE, "CLI cancel command" flow
**Success Criteria** (what must be TRUE):
  1. `cancel agent-1` from CLI executes without TypeError
  2. `redirect agent-1 "new instructions"` from CLI executes without TypeError
  3. Integration test confirms cancel/redirect round-trip through orchestrator
**Plans:** 1/1 plans complete
Plans:
- [ ] 12-01-PLAN.md — Fix cancel_agent signature + integration tests for cancel/redirect

### Phase 13: Wire Escalation Router + Pause Surface
**Goal:** EscalationRouter is connected to ACPClient so AskUserQuestion routing works, and pause_for_human_decision is reachable from CLI and dashboard
**Depends on**: Phase 6, Phase 3, Phase 8
**Requirements:** COMM-03, COMM-04, COMM-07
**Gap Closure:** Closes ESCALATION-ROUTER-UNWIRED, PAUSE-UNREACHABLE
**Success Criteria** (what must be TRUE):
  1. ACPClient sessions use EscalationRouter as their permission_handler
  2. CLI `pause` command invokes pause_for_human_decision on the orchestrator
  3. Dashboard InterventionPanel has a "Pause" action that triggers pause_for_human_decision
**Plans:** 2/2 plans complete
Plans:
- [ ] 13-01-PLAN.md — Wire EscalationRouter into ACPClient + pause command in CLI and dashboard backend
- [ ] 13-02-PLAN.md — Add Pause button to dashboard frontend InterventionPanel

### Phase 14: Fix Getting-Started Guide .env Claim
**Goal:** Getting-started guide is accurate — either .env auto-loading works or the claim is removed
**Depends on**: Phase 11
**Requirements:** PKG-04
**Gap Closure:** Closes "Getting-started guide .env path" flow
**Success Criteria** (what must be TRUE):
  1. Getting-started guide does not claim functionality that doesn't exist
  2. A developer following the guide encounters no incorrect instructions
**Plans:** 1/1 plans complete
Plans:
- [ ] 14-01-PLAN.md — Remove false .env claims, add shell profile persistence guidance

### Phase 15: Fix Dashboard Server Cancel Type Mismatch
**Goal:** Dashboard cancel and redirect commands execute correctly — server.py passes the right argument types to cancel_agent() and redirect
**Depends on**: Phase 10, Phase 12
**Requirements:** COMM-05, DASH-06
**Gap Closure:** Closes dashboard cancel/redirect type mismatch from audit
**Success Criteria** (what must be TRUE):
  1. Dashboard cancel action calls `cancel_agent()` with `str|None` (not TaskSpec)
  2. Dashboard redirect action constructs valid parameters for redirect
  3. Test suite validates correct argument types (no longer masks wrong contract)
**Plans:** 1/1 plans complete
Plans:
- [ ] 15-01-PLAN.md — Fix server.py cancel/redirect branches + update test assertions

### Phase 16: Fix Agent Status Lifecycle
**Goal:** AgentRecord.status accurately reflects agent lifecycle — transitions to DONE on completion and WAITING on pause, enabling dashboard status display and intervention_needed notifications
**Depends on**: Phase 5, Phase 6
**Requirements:** DASH-01, DASH-04
**Gap Closure:** Closes agent status stuck at WORKING and missing WAITING state
**Success Criteria** (what must be TRUE):
  1. AgentRecord.status transitions to DONE when task completes
  2. AgentRecord.status transitions to WAITING when pause_for_human_decision is called
  3. Dashboard intervention_needed notification fires when agent enters WAITING state

### Phase 17: Fix Production WebSocket URL
**Goal:** npm dashboard package connects to the correct FastAPI backend in production — not the sirv static file server port
**Depends on**: Phase 11
**Requirements:** PKG-02
**Gap Closure:** Closes production WebSocket URL mismatch
**Success Criteria** (what must be TRUE):
  1. Dashboard supports runtime backend URL configuration (environment variable or config)
  2. Production deployment connects WebSocket to FastAPI port, not sirv port
  3. npm package documentation reflects production deployment configuration

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11 -> 12 -> 13 -> 14 -> 15 -> 16 -> 17

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Monorepo Foundation | 2/2 | Complete   | 2026-03-10 |
| 2. Shared State Infrastructure | 2/2 | Complete   | 2026-03-10 |
| 3. ACP Communication Layer | 2/2 | Complete   | 2026-03-10 |
| 4. Orchestrator Core | 3/3 | Complete   | 2026-03-10 |
| 5. Orchestrator Intelligence | 1/2 | In Progress|  |
| 6. Escalation and Intervention | 2/2 | Complete   | 2026-03-10 |
| 7. Agent Runtime | 3/3 | Complete   | 2026-03-10 |
| 8. CLI Interface | 2/2 | Complete   | 2026-03-10 |
| 9. Dashboard Backend | 1/2 | In Progress|  |
| 10. Dashboard Frontend | 3/3 | Complete    | 2026-03-10 |
| 11. Packaging and Distribution | 2/2 | Complete    | 2026-03-10 |
| 12. Fix CLI Cancel/Redirect Signatures | 1/1 | Complete    | 2026-03-11 |
| 13. Wire Escalation Router + Pause Surface | 2/2 | Complete    | 2026-03-11 |
| 14. Fix Getting-Started Guide .env Claim | 1/1 | Complete    | 2026-03-11 |
| 15. Fix Dashboard Server Cancel Type Mismatch | 1/1 | Complete    | 2026-03-11 |
| 16. Fix Agent Status Lifecycle | 0/0 | Not Started |  |
| 17. Fix Production WebSocket URL | 0/0 | Not Started |  |
