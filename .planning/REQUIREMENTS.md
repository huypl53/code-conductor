# Requirements: Conductor

**Defined:** 2026-03-10
**Core Value:** A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Orchestration

- [ ] **ORCH-01**: Orchestrator agent (Claude Code via ACP) can receive a feature description and decompose it into discrete coding tasks
- [ ] **ORCH-02**: Orchestrator can spawn sub-agents via ACP and assign them tasks with role, target, and materials
- [ ] **ORCH-03**: Orchestrator monitors sub-agent progress in real-time via ACP streaming (tool calls, file edits)
- [ ] **ORCH-04**: Orchestrator reviews sub-agent output for quality and coherence before marking work complete
- [ ] **ORCH-05**: Orchestrator can give feedback to sub-agents and request revisions
- [ ] **ORCH-06**: Each agent has identity: name, role, target (what they're building), materials (files/context they need)

### Coordination

- [ ] **CORD-01**: Shared state file (`.conductor/state.json`) tracks all tasks, agent assignments, status, outputs, and interfaces
- [ ] **CORD-02**: Orchestrator writes task assignments and resolves conflicts in shared state
- [ ] **CORD-03**: Sub-agents update their own task status and outputs in shared state
- [ ] **CORD-04**: Orchestrator identifies task dependencies and decides strategy per dependency (sequence, stubs-first, parallel)
- [ ] **CORD-05**: Orchestrator prevents concurrent file edit conflicts by assigning file ownership to agents
- [ ] **CORD-06**: Task list is visible to all agents — each agent can see what others are working on and their status

### Communication

- [ ] **COMM-01**: Orchestrator acts as ACP client for sub-agents — receives their questions (permission prompts, clarifications, GSD questions)
- [ ] **COMM-02**: Orchestrator answers sub-agent questions using project context and shared state knowledge
- [ ] **COMM-03**: In `--auto` mode, orchestrator uses best judgment to answer questions and logs decisions
- [ ] **COMM-04**: In interactive mode, orchestrator escalates questions it can't confidently answer to the human
- [ ] **COMM-05**: Orchestrator can cancel a sub-agent's work and reassign with corrected instructions
- [ ] **COMM-06**: Orchestrator can inject guidance to a sub-agent mid-stream without stopping their work
- [ ] **COMM-07**: Orchestrator can pause a sub-agent and escalate to human for a decision

### Agent Runtime

- [ ] **RUNT-01**: Sub-agents inherit repo context (`.claude/`, `CLAUDE.md`, project config) naturally
- [ ] **RUNT-02**: All agents share a `.memory/` folder for cross-agent knowledge persistence
- [ ] **RUNT-03**: Full session persistence — agent identities, conversations, task progress, shared memory survive restarts
- [ ] **RUNT-04**: `--auto` mode: orchestrator thinks critically on specs upfront, then runs fully autonomous
- [ ] **RUNT-05**: Interactive mode: orchestrator can ask human questions during execution
- [ ] **RUNT-06**: Orchestrator dynamically decides how many sub-agents to spawn based on task decomposition

### User Interface — CLI

- [ ] **CLI-01**: User can chat with the orchestrator via CLI terminal
- [ ] **CLI-02**: User can see which agents exist, their roles, and current task status
- [ ] **CLI-03**: User can intervene (cancel, redirect, provide feedback) via CLI commands

### User Interface — Web Dashboard

- [ ] **DASH-01**: Web dashboard shows agent status summary (name, role, current task, progress)
- [ ] **DASH-02**: Dashboard supports expandable detail view per agent (recent actions, files modified, current activity)
- [ ] **DASH-03**: Dashboard supports live stream view per agent (real-time tool calls, streaming output)
- [ ] **DASH-04**: Dashboard sends smart notifications for key events (errors, completions, intervention needed)
- [ ] **DASH-05**: Dashboard handles conversation verbosity with layered visibility — collapsed by default, expand on demand
- [ ] **DASH-06**: User can intervene from dashboard (cancel, redirect, provide feedback to agents)

### Packaging

- [ ] **PKG-01**: Python core distributed as pip package (orchestration, ACP communication, state management)
- [ ] **PKG-02**: Node.js dashboard distributed as npm package (web UI)
- [ ] **PKG-03**: Monorepo structure with Python core + Node.js dashboard
- [ ] **PKG-04**: Installation instructions and getting-started guide

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhanced Orchestration

- **ORCH-07**: Per-task GSD scope flexibility — orchestrator decides whether sub-agent runs full planning or just executes
- **ORCH-08**: Quality review loops with structured feedback cycles (revise → re-review → approve)

### Enhanced Runtime

- **RUNT-07**: Git worktree isolation per agent for large parallel workloads
- **RUNT-08**: CI integration — auto-fix failing builds by spawning agents

### Multi-User

- **MULTI-01**: Multiple developers using same orchestrator on shared repos
- **MULTI-02**: Authentication and access control for dashboard

### Ecosystem

- **ECO-01**: Plugin/extension system for custom agent behaviors
- **ECO-02**: Support for additional ACP-compatible agent types beyond Claude Code

## Out of Scope

| Feature | Reason |
|---------|--------|
| Direct agent-to-agent peer messaging | Creates coordination chaos — race conditions, deadlocks, loops with no coordinator to resolve. Orchestrator mediates all coordination |
| Custom LLM provider support (non-ACP) | Massively increases complexity. Each provider has different capabilities, auth, tool schemas. ACP-only for v1 |
| Per-agent billing / usage dashboards | Billing logic varies by provider, changes frequently. Rely on underlying providers (Anthropic Console, etc.) |
| Mobile app | Responsive web dashboard covers monitoring. Agents need real intervention, not mobile-first UX |
| Unlimited parallel agent scaling | Token costs scale linearly, coordination overhead super-linearly. Dynamic scaling with caps instead |
| General-purpose agent framework | Loses coding-specific advantages: repo context, git integration, code review loops. Domain specificity is a feature |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| (populated during roadmap creation) | | |

**Coverage:**
- v1 requirements: 30 total
- Mapped to phases: 0
- Unmapped: 30 ⚠️

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-10 after initial definition*
