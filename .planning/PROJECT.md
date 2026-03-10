# Conductor

## What This Is

Conductor is an open-source multi-agent coding orchestration framework. You describe what to build, and Conductor's orchestrator — itself a Claude Code agent with orchestration skills — breaks the work down, spins up a dynamic team of ACP-compatible coding agents, manages their work in real-time, reviews output, and delivers coherent code. It ships with both a CLI and a web dashboard for full visibility into agent activity.

## Core Value

A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Orchestrator agent that plans, delegates, reviews, and gives feedback to sub-agents
- [ ] Sub-agents that execute coding tasks via ACP (any ACP-compatible agent)
- [ ] Agent identity system (name, role, target, materials per agent)
- [ ] Shared state file (`.conductor/state.json`) as coordination backbone — task descriptions, status, outputs, interfaces, dependencies
- [ ] Shared `.memory/` folder for cross-agent knowledge persistence
- [ ] Repo-inherited context — agents pick up `.claude/`, `CLAUDE.md`, project config naturally
- [ ] Orchestrator-as-ACP-client — receives and answers sub-agent questions (GSD questions, permission prompts, clarifications)
- [ ] Escalation logic — in `--auto` mode orchestrator uses best judgment; in interactive mode escalates to human
- [ ] Multi-level intervention — cancel/reassign, inject guidance mid-stream, pause/escalate to human
- [ ] Dynamic agent scaling — orchestrator decides team size based on work
- [ ] Dependency management — orchestrator identifies task dependencies, decides strategy (sequence, stubs-first, parallel)
- [ ] Concurrency management — orchestrator plans work to avoid file conflicts, resolves them when they happen
- [ ] Flexible GSD scope — orchestrator decides per-task whether sub-agent needs full planning or just executes instructions
- [ ] Two modes: `--auto` (think critically on specs upfront, then fully autonomous) and interactive (can ask human)
- [ ] Full session persistence — agent identities, conversations, task progress, shared memory survive restarts
- [ ] CLI interface for chatting with orchestrator and seeing agent status
- [ ] Web dashboard (v1 core) with layered visibility — summary by default, expandable detail, live stream, smart notifications
- [ ] Installable as pip package (Python core) + npm package (Node.js dashboard)

### Out of Scope

- Direct agent-to-agent communication (ACP peer-to-peer) — orchestrator mediates all coordination
- Multi-user / team collaboration features — single user controlling the orchestrator for v1
- Mobile app — web dashboard is sufficient
- Custom LLM provider support — ACP-compatible agents only for v1
- Billing / usage management — rely on underlying agent providers

## Context

**ACP (Agent Communication Protocol):**
ACP is a bidirectional protocol (ndjson over stdio) that enables clients to interact with AI agents. It supports streaming tool calls, permission flows, session management, and real-time monitoring. The orchestrator uses ACP to both BE a client (spawning/managing sub-agents) and BE an agent (responding to the human via CLI/dashboard). Key: `@zed-industries/claude-agent-acp` package provides the adapter between Claude Agent SDK and ACP.

**Architectural insight — ACP all the way down:**
The human talks to the orchestrator via ACP. The orchestrator talks to sub-agents via ACP. This means the orchestrator can watch sub-agent tool calls in real-time, see file edits as they happen, and intervene at any point. The same protocol powers both layers.

**Shared state model:**
`.conductor/state.json` is the single source of truth for coordination. Orchestrator writes task assignments and resolves conflicts. Sub-agents write their own status updates and outputs. All agents can read the full state to understand the team's work.

**Orchestration intelligence:**
The orchestrator gets its planning/review/delegation intelligence from installed skills and workflows (similar to how GSD skills teach Claude Code project management). These skills define how to break work down, assign roles, review output, and manage dependencies.

**UX challenge:**
Agent conversations are extremely verbose. The dashboard must handle this with layered visibility: collapsed status summaries by default, expandable to see detail, with smart notifications for events (errors, completions, intervention needs). Avoid raw conversation dumps.

## Constraints

- **Tech stack**: Python core (orchestration, ACP communication) + Node.js web dashboard — monorepo
- **Protocol**: ACP is the only inter-agent communication protocol — no custom protocols
- **Distribution**: pip package + npm package, installable into any repo
- **Orchestrator runtime**: Must work as a Claude Code agent — the orchestrator IS a Claude Code instance with orchestration skills

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Orchestrator is a Claude Code agent via ACP | Reuses existing agent capabilities; same protocol for both layers; orchestrator can use all Claude Code tools | — Pending |
| Shared state file over direct agent messaging | Simpler coordination model; file system is durable; all agents can read asynchronously; avoids complex message routing | — Pending |
| Python core + Node.js dashboard monorepo | Python for orchestration logic and ACP bindings; Node.js for reactive web UI; each package plays to language strengths | — Pending |
| Layered visibility over raw logs | Solves the verbosity UX problem; summary → detail → live stream prevents information overload | — Pending |
| Mode-dependent escalation | `--auto` keeps flow moving (best judgment + logging); interactive respects human oversight; matches different use cases | — Pending |
| Flexible GSD scope per sub-agent | Simple tasks don't need full planning overhead; complex tasks benefit from sub-agent reasoning; orchestrator judges | — Pending |
| Web dashboard as v1 core | Multi-agent visibility requires more than CLI; seeing parallel agent activity needs spatial layout | — Pending |

---
*Last updated: 2025-03-10 after initialization*
