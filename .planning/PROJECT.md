# Conductor

## What This Is

Conductor is an open-source multi-agent coding orchestration framework. You describe what to build, and Conductor's orchestrator — itself a Claude Code agent with orchestration skills — breaks the work down, spins up a dynamic team of ACP-compatible coding agents, manages their work in real-time, reviews output, and delivers coherent code. It ships with both a CLI and a web dashboard for full visibility into agent activity.

## Current Milestones

### v1.3 Orchestrator Intelligence (in progress)

**Goal:** Make Conductor's orchestrator smarter — wave-based parallel execution, model routing for cost control, structured agent communication, goal-backward verification, and complexity-informed task decomposition.

### v2.0 Textual TUI Redesign (complete)

**Goal:** Replace prompt_toolkit + Rich with a full Textual-based TUI inspired by Codex CLI — cell-based transcript, modal approval overlays, inline agent monitoring, syntax-highlighted output, and a polished terminal experience.

### v2.1 UX Polish (in progress)

**Goal:** Refine the Textual TUI to feel native and polished in the terminal — auto-focus, full alt-screen mode, borderless design, smooth animations, and external editor support.

**Target features:**
- Auto-focus input on TUI start
- Full alt-screen mode with clean entry/exit
- Borderless/minimal chrome design — content flows naturally
- Smooth animations and transitions
- Ctrl-G to open input in external editor (vim) for multiline composition

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

**v1.3 — Orchestrator Intelligence:**
- [ ] Wave-based parallel execution with pre-computed dependency waves
- [ ] Model routing per agent role (opus for planning, haiku for verification)
- [ ] Structured agent status protocol (DONE/BLOCKED/NEEDS_CONTEXT)
- [ ] Goal-backward verification (stub detection + wiring checks)
- [ ] Two-stage review (spec compliance then code quality)
- [ ] Smart decomposition with complexity scoring

**v2.0 — Textual TUI Redesign (complete):**
- [x] Textual-based TUI replacing prompt_toolkit + Rich
- [x] Cell-based transcript with streaming and markdown rendering
- [x] Modal approval overlays for agent actions
- [x] Inline agent monitoring panels in TUI
- [x] Syntax-highlighted diffs and code blocks
- [x] Status footer with model/tokens/mode
- [x] Slash command autocomplete popup

**v2.1 — UX Polish:**
- [ ] Auto-focus input on TUI start
- [ ] Full alt-screen mode with clean entry/exit
- [ ] Borderless/minimal chrome design
- [ ] Smooth animations and transitions
- [ ] Ctrl-G external editor (vim) for multiline input

### Out of Scope

- Direct agent-to-agent communication (ACP peer-to-peer) — orchestrator mediates all coordination
- Multi-user / team collaboration features — single user controlling the orchestrator for v1
- Mobile app — web dashboard is sufficient
- Custom LLM provider support — ACP-compatible agents only
- Billing / usage management — rely on underlying agent providers

## Context

Shipped v1.0 with 10,946 LOC (8,604 Python + 2,342 TypeScript). v1.1 delivered Interactive Chat TUI (19 requirements, 5 phases). v1.2 added task verification and build safety. v1.3 adding orchestrator intelligence (parallel track).
Tech stack: Python core (uv, Pydantic v2, asyncio, filelock) + Node.js dashboard (React, Vite, Tailwind, Vitest).
Current TUI: prompt_toolkit for input + Rich for output — functional but basic.
Distribution: `pip install conductor-ai` + `npm install -g conductor-dashboard`.
30 phases completed across v1.0-v1.2.

v2.0 TUI shipped with Textual (Python): cell-based transcript, modal approval overlays, shimmer animations, syntax-highlighted diffs, slash command autocomplete, status footer. 8 phases (31-38), 641 tests passing.
v2.1 polishing TUI to match Codex-level terminal integration: alt-screen, borderless chrome, smooth animations, external editor.

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
| Textual over Ratatui for TUI redesign | Stays in Python ecosystem, built by Rich author, CSS styling, widget-based — avoids Rust FFI complexity | — Pending |
| TUI and web dashboard coexist | TUI for primary terminal use, web dashboard for remote/detailed/mobile monitoring | — Pending |
| v2.0 TUI as parallel worktree to v1.3 | Unblocks UI work without pausing orchestrator intelligence improvements | — Pending |

---
*Last updated: 2026-03-11 after v2.1 UX Polish milestone started*
