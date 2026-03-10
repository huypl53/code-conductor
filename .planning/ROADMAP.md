# Roadmap: Conductor

## Overview

Conductor is built from the ground up: shared state foundation first (preventing the concurrent-write corruption pitfall before any agents run), then the ACP communication layer, then orchestrator intelligence, then CLI validation of the end-to-end loop, then the dashboard backend and frontend, and finally packaging for distribution. Every phase delivers a coherent, testable capability. The CLI produces a working multi-agent product by Phase 8; Phases 9-11 add the web dashboard and make the system installable anywhere.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Monorepo Foundation** - Python + Node.js monorepo scaffold with CI, linting, and project structure (completed 2026-03-10)
- [ ] **Phase 2: Shared State Infrastructure** - Safe `.conductor/state.json` with file-locked reads/writes and Pydantic models
- [ ] **Phase 3: ACP Communication Layer** - ACP client/server runtime with permission flow, timeout, and safe defaults
- [ ] **Phase 4: Orchestrator Core** - Orchestrator agent that plans, decomposes, delegates, and manages file ownership
- [ ] **Phase 5: Orchestrator Intelligence** - Real-time sub-agent monitoring, output review, and feedback loops
- [ ] **Phase 6: Escalation and Intervention** - Auto/interactive mode logic, cancel, inject-mid-stream, and pause/escalate
- [ ] **Phase 7: Agent Runtime** - Context inheritance, shared memory, session persistence, and dynamic team sizing
- [ ] **Phase 8: CLI Interface** - Terminal interface for chatting with orchestrator, viewing agent status, and intervening
- [ ] **Phase 9: Dashboard Backend** - State watcher, WebSocket broadcast server, and server-side event filtering
- [ ] **Phase 10: Dashboard Frontend** - React dashboard with layered visibility, live stream, and intervention controls
- [ ] **Phase 11: Packaging and Distribution** - pip and npm packages with installation and getting-started guide

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
**Plans:** 2 plans
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
**Plans**: TBD

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
**Plans**: TBD

### Phase 5: Orchestrator Intelligence
**Goal**: The orchestrator monitors sub-agent work in real time, reviews completed output for quality and coherence, and can request revisions before marking a task complete
**Depends on**: Phase 4
**Requirements**: ORCH-03, ORCH-04, ORCH-05
**Success Criteria** (what must be TRUE):
  1. Orchestrator sees sub-agent tool calls and file edits as they happen via ACP streaming (not just at completion)
  2. When a sub-agent completes a task, the orchestrator reviews the output and either approves or requests changes
  3. Orchestrator can send structured feedback to a sub-agent and the sub-agent revises accordingly
  4. A task is only marked complete after orchestrator review passes — not immediately when the sub-agent reports done
**Plans**: TBD

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
**Plans**: TBD

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
**Plans**: TBD

### Phase 8: CLI Interface
**Goal**: A developer can run `conductor` from the terminal, describe a feature, watch agents work, and intervene (cancel, redirect, feedback) — without needing the web dashboard
**Depends on**: Phase 7
**Requirements**: CLI-01, CLI-02, CLI-03
**Success Criteria** (what must be TRUE):
  1. `conductor run "add dark mode to the settings page"` starts the orchestrator and shows agent activity in the terminal
  2. The terminal displays each agent's name, role, and current task status in a live-updating view
  3. The user can type a CLI command to cancel an agent, redirect it with new instructions, or inject feedback — and the change takes effect without restarting the session
**Plans**: TBD

### Phase 9: Dashboard Backend
**Goal**: A FastAPI server streams real-time agent state changes to connected dashboard clients over WebSocket — with server-side event filtering that prevents raw ACP log dumps from overwhelming the client
**Depends on**: Phase 8
**Requirements**: DASH-04
**Success Criteria** (what must be TRUE):
  1. The dashboard backend starts alongside Conductor and is reachable at a local URL
  2. When agent state changes (task assigned, status updated, task completed), the WebSocket client receives a delta event within 1 second
  3. Smart notification events (errors, completions, intervention needed) are identified and flagged server-side — the client does not filter raw events
  4. A new WebSocket client connecting mid-session receives the full current state via REST before receiving incremental updates
**Plans**: TBD

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
**Plans**: TBD

### Phase 11: Packaging and Distribution
**Goal**: Conductor can be installed into any repository with `pip install conductor-ai` and `npm install -g conductor-dashboard` — and a developer who has never seen the project can get it running from the getting-started guide
**Depends on**: Phase 10
**Requirements**: PKG-01, PKG-02, PKG-04
**Success Criteria** (what must be TRUE):
  1. `pip install conductor-ai` in a fresh virtual environment installs the CLI and Python core with no errors
  2. `npm install -g conductor-dashboard` installs the dashboard package with no errors
  3. A developer following only the getting-started guide (no prior knowledge of the codebase) can run their first multi-agent session
  4. Both packages have correct version metadata and are installable from their respective registries (PyPI / npm)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Monorepo Foundation | 2/2 | Complete   | 2026-03-10 |
| 2. Shared State Infrastructure | 0/2 | Not started | - |
| 3. ACP Communication Layer | 0/TBD | Not started | - |
| 4. Orchestrator Core | 0/TBD | Not started | - |
| 5. Orchestrator Intelligence | 0/TBD | Not started | - |
| 6. Escalation and Intervention | 0/TBD | Not started | - |
| 7. Agent Runtime | 0/TBD | Not started | - |
| 8. CLI Interface | 0/TBD | Not started | - |
| 9. Dashboard Backend | 0/TBD | Not started | - |
| 10. Dashboard Frontend | 0/TBD | Not started | - |
| 11. Packaging and Distribution | 0/TBD | Not started | - |
