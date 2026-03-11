# Conductor

## What This Is

Conductor is an open-source multi-agent coding orchestration framework. You describe what to build, and Conductor's orchestrator — itself a Claude Code agent with orchestration skills — breaks the work down, spins up a dynamic team of ACP-compatible coding agents, manages their work in real-time, reviews output, and delivers coherent code. It ships with both a CLI and a web dashboard for full visibility into agent activity.

## Current Milestones

All milestones through v2.1 are complete. No active milestone.

### Completed Milestones

- **v1.0 MVP** — Phases 1-17 (shipped 2026-03-11)
- **v1.1 Interactive Chat TUI** — Phases 18-22 (completed 2026-03-11)
- **v1.2 Task Verification & Build Safety** — Phases 23-25 (completed 2026-03-11)
- **v1.3 Orchestrator Intelligence** — Phases 26-30 (completed 2026-03-11)
- **v2.0 Textual TUI Redesign** — Phases 31-38 (completed 2026-03-11)
- **v2.1 UX Polish** — Phases 39-42 (shipped 2026-03-12)

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
- ✓ Wave-based parallel execution with pre-computed dependency waves — v1.3
- ✓ Model routing per agent role (opus for planning, haiku for verification) — v1.3
- ✓ Structured agent status protocol (DONE/BLOCKED/NEEDS_CONTEXT) — v1.3
- ✓ Goal-backward verification (stub detection + wiring checks) — v1.3
- ✓ Two-stage review (spec compliance then code quality) — v1.3
- ✓ Smart decomposition with complexity scoring — v1.3
- ✓ Textual-based TUI replacing prompt_toolkit + Rich — v2.0
- ✓ Cell-based transcript with streaming and markdown rendering — v2.0
- ✓ Modal approval overlays for agent actions — v2.0
- ✓ Inline agent monitoring panels in TUI — v2.0
- ✓ Syntax-highlighted diffs and code blocks — v2.0
- ✓ Status footer with model/tokens/mode — v2.0
- ✓ Slash command autocomplete popup — v2.0
- ✓ Auto-focus input on TUI start — v2.1
- ✓ Full alt-screen mode with clean entry/exit — v2.1
- ✓ Borderless/minimal chrome design — v2.1
- ✓ Smooth animations and transitions — v2.1
- ✓ Ctrl-G external editor (vim) for multiline input — v2.1

### Out of Scope

- Direct agent-to-agent communication (ACP peer-to-peer) — orchestrator mediates all coordination
- Multi-user / team collaboration features — single user controlling the orchestrator for v1
- Mobile app — web dashboard is sufficient
- Custom LLM provider support — ACP-compatible agents only
- Billing / usage management — rely on underlying agent providers

## Context

Shipped v2.1 UX Polish with 20,155 Python LOC total, 663 tests passing. 42 phases completed across v1.0-v2.1.
Tech stack: Python core (uv, Pydantic v2, asyncio, filelock, Textual) + Node.js dashboard (React, Vite, Tailwind, Vitest).
TUI: Textual-based with cell transcript, modal approvals, agent monitoring, syntax highlighting, shimmer animations, auto-focus, borderless design, smooth fade-in animations, Ctrl-G external editor.
Distribution: `pip install conductor-ai` + `npm install -g conductor-dashboard`.

Known tech debt:
- `get_server_info()` wrapped in broad `except Exception` — session_id persistence silently fails
- Human verification needed for clean-environment installs (pip/npm/docs walkthrough)

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
| Textual over Ratatui for TUI redesign | Stays in Python ecosystem, built by Rich author, CSS styling, widget-based — avoids Rust FFI complexity | ✓ Good — Textual delivered full TUI in 12 phases |
| TUI and web dashboard coexist | TUI for primary terminal use, web dashboard for remote/detailed/mobile monitoring | ✓ Good — both serve distinct use cases |

---
*Last updated: 2026-03-12 after v2.1 UX Polish milestone shipped*
