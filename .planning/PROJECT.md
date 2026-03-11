# Conductor

## What This Is

Conductor is an open-source multi-agent coding orchestration framework. You describe what to build, and Conductor's orchestrator — itself a Claude Code agent with orchestration skills — breaks the work down, spins up a dynamic team of ACP-compatible coding agents, manages their work in real-time, reviews output, and delivers coherent code. It ships with both a CLI and a web dashboard for full visibility into agent activity.

## Current Milestone: v1.1 Interactive Chat TUI

**Goal:** Add an interactive conversational TUI so users can chat with the orchestrator like a coding agent CLI (similar to Claude Code / Codex CLI).

**Target features:**
- Interactive chat TUI via `conductor` command (no args)
- Orchestrator as conversational brain with direct tool use (file read/edit, shell commands)
- Smart delegation — handles simple tasks directly, spawns sub-agent teams for complex work
- Existing `conductor run "..."` stays as non-interactive batch mode

## Core Value

A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## Requirements

### Validated

- ✓ Orchestrator agent that plans, delegates, reviews, and gives feedback to sub-agents — v1.0
- ✓ Sub-agents that execute coding tasks via ACP (any ACP-compatible agent) — v1.0
- ✓ Agent identity system (name, role, target, materials per agent) — v1.0
- ✓ Shared state file (`.conductor/state.json`) as coordination backbone — v1.0
- ✓ Shared `.memory/` folder for cross-agent knowledge persistence — v1.0
- ✓ Repo-inherited context — agents pick up `.claude/`, `CLAUDE.md`, project config naturally — v1.0
- ✓ Orchestrator-as-ACP-client — receives and answers sub-agent questions — v1.0
- ✓ Escalation logic — auto mode uses best judgment; interactive mode escalates to human — v1.0
- ✓ Multi-level intervention — cancel/reassign, inject guidance mid-stream, pause/escalate — v1.0
- ✓ Dynamic agent scaling — orchestrator decides team size based on work — v1.0
- ✓ Dependency management — orchestrator identifies task dependencies, decides strategy — v1.0
- ✓ Concurrency management — file ownership prevents conflicts — v1.0
- ✓ Two modes: `--auto` (autonomous after spec review) and interactive (can ask human) — v1.0
- ✓ Full session persistence — agent identities, conversations, task progress survive restarts — v1.0
- ✓ CLI interface for chatting with orchestrator and seeing agent status — v1.0
- ✓ Web dashboard with layered visibility, live stream, smart notifications — v1.0
- ✓ Installable as pip package (Python core) + npm package (Node.js dashboard) — v1.0

### Active

- [ ] Interactive chat TUI — conversational coding agent interface via `conductor` command
- [ ] Direct tool use — orchestrator reads/edits files, runs shell commands in chat mode
- [ ] Smart delegation — orchestrator decides when to handle directly vs. spawn sub-agents
- [ ] Per-task GSD scope flexibility — orchestrator decides whether sub-agent runs full planning or just executes
- [ ] Quality review loops with structured feedback cycles (revise → re-review → approve)
- [ ] Git worktree isolation per agent for large parallel workloads
- [ ] CI integration — auto-fix failing builds by spawning agents

### Out of Scope

- Direct agent-to-agent communication (ACP peer-to-peer) — orchestrator mediates all coordination
- Multi-user / team collaboration features — single user controlling the orchestrator for v1
- Mobile app — web dashboard is sufficient
- Custom LLM provider support — ACP-compatible agents only
- Billing / usage management — rely on underlying agent providers

## Context

Shipped v1.0 with 10,946 LOC (8,604 Python + 2,342 TypeScript).
Tech stack: Python core (uv, Pydantic v2, asyncio, filelock) + Node.js dashboard (React, Vite, Tailwind, Vitest).
Distribution: `pip install conductor-ai` + `npm install -g conductor-dashboard`.
17 phases completed across 32 plans in 2 days.

Known tech debt:
- `get_server_info()` wrapped in broad `except Exception` — session_id persistence silently fails
- Human verification needed for clean-environment installs (pip/npm/docs walkthrough)
- ~10 SUMMARY frontmatter missing `requirements_completed` fields

## Constraints

- **Tech stack**: Python core (orchestration, ACP communication) + Node.js web dashboard — monorepo
- **Protocol**: ACP is the only inter-agent communication protocol — no custom protocols
- **Distribution**: pip package + npm package, installable into any repo
- **Orchestrator runtime**: Must work as a Claude Code agent — the orchestrator IS a Claude Code instance with orchestration skills

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Orchestrator is a Claude Code agent via ACP | Reuses existing agent capabilities; same protocol for both layers | ✓ Good — clean two-layer ACP architecture |
| Shared state file over direct agent messaging | Simpler coordination model; file system is durable; avoids complex message routing | ✓ Good — filelock prevents corruption |
| Python core + Node.js dashboard monorepo | Python for orchestration logic; Node.js for reactive web UI | ✓ Good — each language plays to strengths |
| Layered visibility over raw logs | summary → detail → live stream prevents information overload | ✓ Good — dashboard UX is clean |
| Mode-dependent escalation | `--auto` keeps flow; interactive respects human oversight | ✓ Good — both modes work |
| Web dashboard as v1 core | Multi-agent visibility requires spatial layout beyond CLI | ✓ Good — dashboard adds real value |
| StrEnum + ConfigDict for JSON serialization | Clean enum values in state.json without repr leaking | ✓ Good — no serialization issues |
| asyncio.wait(FIRST_COMPLETED) for spawn loop | Ready tasks unblock as dependencies complete without waiting for whole wave | ✓ Good — efficient parallelism |
| Watch parent directory for state changes | watchfiles misses atomic os.replace inode swaps on direct file watch | ✓ Good — solved production bug |

---
*Last updated: 2026-03-11 after v1.1 milestone started*
