# Project Research Summary

**Project:** Conductor — multi-agent coding orchestration framework
**Domain:** Multi-agent coding orchestration (Python core + Node.js dashboard monorepo)
**Researched:** 2026-03-10
**Confidence:** HIGH

## Executive Summary

Conductor is a multi-agent coding orchestration framework built on top of the Agent Client Protocol (ACP). The established approach is a supervisor architecture: a single orchestrator Claude Code process plans work, spawns sub-agents via ACP stdio, mediates all inter-agent coordination through a shared state file, and answers sub-agent questions in real time. This is not a new pattern — CrewAI, AutoGen, LangGraph, and ccswarm all follow hierarchical coordinator models — but Conductor's differentiation lies in three things no existing tool does well: ACP-native bidirectional orchestration (same protocol at every layer), layered web dashboard visibility (not raw log dumps), and orchestrator-mediated file ownership that prevents concurrent edit conflicts.

The recommended stack is unambiguous: `claude-agent-sdk` 0.1.48 (`ClaudeSDKClient`, not the deprecated `query()`) for agent process management, `asyncio.TaskGroup` for concurrency, Pydantic v2 + `filelock` for safe shared state, FastAPI + Uvicorn for the WebSocket bridge, and React 19 + Zustand + TanStack Query for the dashboard. The monorepo uses `uv` for Python and `pnpm` workspaces for Node.js. The CLI is the minimum viable interface; the web dashboard is a core product promise, not an afterthought.

The dominant risks are concrete and well-documented: shared state file corruption from concurrent writes (an open bug in Claude Code itself), runaway token costs from unbounded agent proliferation (887K tokens/minute case study exists), missed sequential dependencies that cause incompatible parallel outputs, and orchestrator context drift where the LLM starts coding instead of coordinating. All four must be addressed in the infrastructure and orchestrator intelligence phases before any parallel agent work begins — retrofitting these protections is significantly harder than building them in from day one.

---

## Key Findings

### Recommended Stack

The stack is split between a Python core (orchestration, ACP, state, API bridge) and a Node.js dashboard (React SPA). The two packages are independently installable (`pip install conductor-ai` / `npm install -g conductor-dashboard`) but communicate via WebSocket. `claude-agent-sdk` 0.1.48 is the only supported programmatic interface to Claude Code — the previously common `claude-code-sdk` was deprecated in September 2025. The dashboard is a Vite SPA (not Next.js) served by the Python backend; there is no need for SSR. Key deprecated or anti-recommended paths: LangChain/LangGraph/CrewAI (wrong abstraction for ACP subprocess model), `asyncio.create_subprocess_shell` (injection risk), threading (wrong concurrency model), Celery (adds Redis dependency for a problem `asyncio.TaskGroup` solves in-process).

**Core technologies:**
- `claude-agent-sdk` 0.1.48 (`ClaudeSDKClient`): spawn and converse with sub-agents via ACP — the only official programmatic interface
- Python 3.11+ / `asyncio.TaskGroup`: concurrent subprocess management without threading pitfalls
- Pydantic v2 + `filelock`: state schema validation and safe concurrent file writes
- FastAPI + Uvicorn: dual REST + WebSocket bridge to dashboard; first-class async, no impedance mismatch
- `watchfiles` 1.1.1: Rust-backed async file watcher for pushing state changes to dashboard clients
- React 19 + Zustand 5 + TanStack Query 5: dashboard UI with targeted re-renders for high-frequency WebSocket updates
- `shadcn/ui` + Tailwind CSS 4: copy-owned component library; collapsible panel pattern built in
- `uv` + `pnpm` workspaces: fast, deterministic dependency management for both language ecosystems

### Expected Features

The full feature breakdown with dependency graph and competitor analysis is in `.planning/research/FEATURES.md`. Summary below.

**Must have (table stakes):**
- Orchestrator agent that plans, decomposes work, delegates, and reviews — without this, nothing works
- ACP client/server runtime — the protocol layer for all inter-process communication
- Agent identity system (name, role, target, materials) — prevents agents trampling each other's scope
- Shared state file (`.conductor/state.json`) — single coordination backbone
- Task list with status tracking and dependency management — parallel work without this breaks
- Conflict prevention for concurrent file edits — orchestrator-enforced file ownership per agent
- Orchestrator-as-ACP-client answering sub-agent questions — key differentiator, prevents agent stalling
- Session persistence (state + `.memory/`) — long sessions must survive restarts
- CLI interface — minimum viable interface for human interaction
- Web dashboard with layered visibility (summary → expanded → live stream) — core product promise

**Should have (competitive differentiators, add at v1.x):**
- Dynamic team sizing: orchestrator decides agent count based on task complexity, not user config
- Quality review loops with feedback before marking tasks complete
- Multi-level intervention vocabulary: cancel, reassign, inject mid-stream, pause/escalate
- Smart notifications: only completions, errors, and escalations — not every event
- Per-task GSD scope flexibility: simple tasks execute directly, complex tasks get full planning

**Defer (v2+):**
- Multi-user / team collaboration — requires auth, access control, entirely new product surface
- Additional ACP-compatible agent types beyond Claude Code — wait for ACP ecosystem to mature
- CI integration (auto-fix failing builds) — powerful but complex; defer until core is solid
- Git worktree isolation per agent — useful but adds complexity; evaluate after v1 usage data

**Explicit anti-features (do not build):**
- Direct agent-to-agent peer messaging — creates coordination chaos, loses observability
- Custom LLM provider support (non-ACP) — scope explosion with no v1 payoff
- Raw conversation log streaming as primary dashboard UI — information overload, the core UX problem to solve

### Architecture Approach

The system has four layers: Human Layer (CLI + Web Dashboard), Orchestration Layer (Python orchestrator process with Agent Manager and State Manager), Sub-Agent Layer (ACP subprocess pool), and Shared State Layer (filesystem: `state.json`, `.memory/`, `.claude/`). The dashboard is a separate Node.js package that connects to a FastAPI WebSocket server embedded in the Python core. All inter-process communication uses ACP (ndjson over stdio); there is no custom protocol. The build order follows clear dependencies: shared state models → ACP communication layer → orchestrator lifecycle → CLI → state watching + dashboard backend → dashboard frontend. The CLI produces a working product at phase 4, before the dashboard exists — validate the core loop first.

**Major components:**
1. **Orchestrator Process** — Claude Code agent with orchestration skills; plans, delegates, reviews, mediates all coordination; never writes code directly
2. **Agent Manager** — asyncio subprocess pool; spawns/kills/tracks sub-agent processes via ACP stdio; one `ClaudeSDKClient` instance per agent
3. **State Manager** — file-locked read/write of `.conductor/state.json`; emits events on changes; the coordination backbone
4. **Dashboard API Server** — FastAPI + Uvicorn; broadcasts state change events over WebSocket; REST for initial state load
5. **Web Dashboard** — React 19 SPA; Zustand for WebSocket state, TanStack Query for REST; AgentCard with three-tier visibility
6. **Shared Memory** — `.memory/` per-agent-keyed files; cross-agent persistent knowledge; merged by orchestrator on demand

### Critical Pitfalls

The full pitfall catalog with warning signs, recovery strategies, and phase-to-pitfall mapping is in `.planning/research/PITFALLS.md`. Top six critical pitfalls:

1. **State file corruption from concurrent writes** — Use orchestrator-mediated writes or per-agent namespaced keys with `filelock`; never allow two processes to write the same key simultaneously. This is an active production bug in Claude Code itself (GitHub #28847, #29036).
2. **Runaway token costs from unbounded agent proliferation** — Enforce hard `max_agents` cap (6-8), per-session `max_turns`, agent idle timeouts, and token velocity alerts. Use cheaper models for sub-agents; reserve expensive models for orchestrator planning only.
3. **Over-parallelization with missed sequential dependencies** — Require a contracts-first step: orchestrator defines shared interfaces before any sub-agent begins coding. Every task must declare explicit `requires:` and `produces:` fields.
4. **Context window exhaustion mid-task with silent state loss** — Require sub-agents to write progress notes to `.memory/[agent-id].md` at regular intervals. Design tasks to be resumable from checkpoints.
5. **Orchestrator intelligence drift (LLM starts coding instead of coordinating)** — Repeatedly re-anchor the orchestrator's role in skills/prompts: "You are a coordinator. Do not write code." Route sub-agent output summaries, not full outputs, to orchestrator context.
6. **ACP permission prompt deadlock** — Pre-authorize common tool classes at session start. Implement async fast-path for permission responses separate from LLM inference. Set timeout with safe-default (deny) if no response within N seconds.

---

## Implications for Roadmap

Based on the architecture's explicit build order, feature dependencies, and pitfall-to-phase mapping from research:

### Phase 1: Shared Foundation and State Infrastructure

**Rationale:** Everything depends on safe, reliable state management. The concurrent-write corruption pitfall (Pitfall 1) must be solved before any multi-agent work begins — it cannot be retrofitted. This phase has no external dependencies and produces immediately testable components.

**Delivers:** Pydantic models for Task/Agent/Dependency; `StateManager` with `filelock`; agent identity model; project config structure.

**Addresses features:** Shared state file (`.conductor/state.json`), agent identity system, task list data model.

**Avoids:** State file corruption (Pitfall 1) — enforce write discipline from day one, not as a patch later.

**Research flag:** Standard patterns — file locking with `filelock` and Pydantic v2 are well-documented. No deeper research needed.

---

### Phase 2: ACP Communication Layer

**Rationale:** The orchestrator and all sub-agents communicate exclusively via ACP. This layer must exist before any agent can be spawned. `ClaudeSDKClient` (not `query()`) is required for persistent sessions and mid-stream interrupts — getting this right early prevents a costly migration.

**Delivers:** `agents/acp_client.py` per sub-agent ACP connection; `orchestrator/acp_bridge.py` for human-to-orchestrator link; ACP permission flow with timeout and safe default.

**Addresses features:** ACP client/server runtime, orchestrator-as-ACP-client for answering sub-agent questions.

**Avoids:** ACP permission deadlock (Pitfall 6) — async permission fast-path and timeout must be built into this layer, not the orchestrator layer.

**Research flag:** Needs verification — `ClaudeSDKClient` API details (session management, interrupt semantics) should be validated against current SDK 0.1.48 docs before implementation. ACP ndjson parsing edge cases (partial lines, SIGPIPE on subprocess exit) need careful handling.

---

### Phase 3: Orchestrator Lifecycle and Skills

**Rationale:** The orchestrator's planning quality and role discipline determine correctness of the entire system. Orchestrator intelligence drift (Pitfall 5) and over-parallelization (Pitfall 3) both originate here. Cost controls (Pitfall 2) must be baked into orchestrator skills from day one.

**Delivers:** `orchestrator/process.py` for Claude Code subprocess lifecycle; orchestrator skills files (`plan.md`, `delegate.md`, `review.md`) with explicit role anchoring, dependency declaration requirements, contracts-first step, and `max_agents` enforcement; `agents/manager.py` asyncio subprocess pool.

**Addresses features:** Orchestrator agent (planning + delegation), dependency management, conflict prevention via file ownership, output coherence / integration review, `--auto` vs interactive mode.

**Avoids:** Over-parallelization (Pitfall 3) via contracts-first and explicit task dependency declaration; orchestrator role drift (Pitfall 5) via re-anchoring language in skills; runaway costs (Pitfall 2) via `max_agents` cap and model tiering in skills.

**Research flag:** Needs phase research — orchestrator skill/prompt engineering for role anchoring under long sessions is not well-documented. Recommend research-phase during planning for orchestrator prompt design and dependency declaration schema.

---

### Phase 4: CLI and Core Loop Validation

**Rationale:** Architecture research explicitly states the CLI provides a working product before the dashboard exists. This phase validates the end-to-end loop (human → orchestrator → agents → results) with a minimal interface. All subsequent phases build on a proven foundation.

**Delivers:** `cli/main.py` with Typer; `conductor run` and `conductor status` commands; Rich live display for agent status in terminal; working multi-agent session from CLI.

**Addresses features:** CLI interface, `--auto` mode + interactive mode, repo context inheritance (CLAUDE.md discovery), session persistence.

**Avoids:** Context exhaustion mid-task (Pitfall 4) — `.memory/` checkpoint writes must be implemented here, tested before dashboard distracts focus.

**Research flag:** Standard patterns — Typer + Rich are well-documented and the Conductor authors are familiar with the stack.

---

### Phase 5: State Watching and Dashboard Backend

**Rationale:** The dashboard frontend cannot be built until the Python server exists. The state watcher is the bridge between filesystem state changes and real-time WebSocket events. This phase must implement event filtering at the backend — not the frontend — to prevent streaming full ACP events to the dashboard (a performance trap that breaks at 3+ active agents).

**Delivers:** `state/watcher.py` with `watchfiles` `awatch()`; `dashboard/broadcaster.py` fan-out; `dashboard/server.py` FastAPI REST + WebSocket; delta events (not full state) over WebSocket.

**Addresses features:** Web dashboard data feed, smart notifications (server-side filtering), session history REST endpoint.

**Avoids:** Verbose output UX overload (UX pitfall) — event aggregation/filtering must be implemented at backend before the frontend renders anything.

**Research flag:** Standard patterns — FastAPI WebSocket broadcast and `watchfiles` async API are well-documented.

---

### Phase 6: Web Dashboard Frontend

**Rationale:** The dashboard is a core product differentiator — layered visibility is what sets Conductor apart from tools that dump raw logs. Build last because it depends on all previous phases, but it is not an optional add-on.

**Delivers:** `conductor-dashboard` npm package; AgentCard with three-tier visibility (collapsed → expanded → live stream); TaskBoard with dependency graph; LogStream with virtual list rendering; smart notifications (completions, errors, escalations only); WebSocket reconnect logic.

**Addresses features:** Web dashboard with layered visibility, multi-level intervention UI, smart notifications, per-agent status hierarchy.

**Avoids:** Raw log dump as primary UI (anti-feature), identical visual treatment for all agents (UX pitfall), missing error states for crashed agents (looks-done-but-isn't checklist).

**Research flag:** Standard patterns for React 19 + Zustand + TanStack Query + shadcn/ui. The virtual list rendering for agent cards at 5-20 agents scale may need research into `@tanstack/react-virtual` or equivalent.

---

### Phase 7: v1.x Enhancements

**Rationale:** Add after the core loop is proven working in phases 1-6. These features add significant value but require a stable base to tune correctly.

**Delivers:** Dynamic team sizing; quality review loops with feedback; full multi-level intervention vocabulary; per-task GSD scope flexibility.

**Addresses features:** All P2 features from FEATURES.md prioritization matrix.

**Research flag:** Dynamic team sizing needs research — the orchestrator judgment for "how many agents for this task" is not well-documented and will likely require experimentation.

---

### Phase Ordering Rationale

- **Foundation-first:** State management and ACP communication must be correct before orchestrator logic, which must be correct before the CLI, which must work before the dashboard. The architecture's build order is non-negotiable because each layer has hard dependencies on the layer below.
- **Validate before invest:** Phase 4 (CLI) produces a working product. Dashboard work in phases 5-6 is significant investment — validate that the core agent loop actually works before committing to frontend build.
- **Pitfall timing:** The three most costly pitfalls (state corruption, cost explosion, parallelization failures) must all be addressed in phases 1-3. These cannot be patched in after agents are running in parallel.
- **Skills before scaling:** Orchestrator intelligence (Phase 3) precedes adding more features. An orchestrator that drifts into coding behavior or over-parallelizes makes everything built on top of it unreliable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (ACP Layer):** `ClaudeSDKClient` session management, interrupt semantics, and ACP ndjson edge cases should be validated against current SDK 0.1.48 docs before implementation begins.
- **Phase 3 (Orchestrator Skills):** Orchestrator prompt engineering for role anchoring under long (50+ turn) sessions is not well-documented. Recommend `/gsd:research-phase` focused on multi-agent prompt patterns, contracts-first step design, and dependency declaration schema.
- **Phase 7 (Dynamic Team Sizing):** Orchestrator judgment criteria for "how many agents" is experimental territory. Recommend `/gsd:research-phase` when approaching this feature.

Phases with standard patterns (skip research-phase):
- **Phase 1 (State Foundation):** Pydantic v2, `filelock`, Pydantic models — all well-documented.
- **Phase 4 (CLI Core Loop):** Typer + Rich patterns are established.
- **Phase 5 (Dashboard Backend):** FastAPI WebSocket + `watchfiles` are well-documented.
- **Phase 6 (Dashboard Frontend):** React 19 + Zustand + shadcn/ui patterns are established; virtual list rendering is the only potential gap.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core Python and Node.js stack verified against official docs and PyPI. `claude-agent-sdk` 0.1.48 confirmed as correct SDK. Only medium-confidence items are ACP third-party wiki and community articles on TanStack Query + WebSocket hybrid pattern. |
| Features | HIGH | Primary sources are official Anthropic Claude Code docs and peer-reviewed research. Competitor analysis covers all major frameworks. MVP definition is well-grounded in feature dependencies. |
| Architecture | HIGH (core), MEDIUM (ACP integration specifics) | Supervisor pattern, shared state backbone, and layered dashboard are well-established. ACP stdio integration specifics (partial line handling, SIGPIPE, interrupt semantics) have medium confidence — need validation against live SDK. |
| Pitfalls | HIGH | State corruption pitfall verified via official GitHub issues. Token cost explosion verified via real-world case study. Over-parallelization failure rate backed by peer-reviewed research (arXiv 2503.13657). Security pitfalls from OWASP official. |

**Overall confidence:** HIGH

### Gaps to Address

- **ACP `ClaudeSDKClient` interrupt semantics:** Exactly how mid-stream interrupts work (can orchestrator interrupt a sub-agent mid-tool-call?), and how session IDs are managed for restart recovery, needs live SDK validation during Phase 2 planning.
- **Orchestrator role anchoring prompt design:** No definitive source documents optimal prompt structure for keeping an LLM in a coordinator role over 100+ turns. This is the highest-risk unknown and warrants dedicated research-phase before Phase 3 implementation.
- **State.json write architecture decision:** Two valid approaches (orchestrator-mediated writes vs. per-agent namespaced keys with `filelock`) have different complexity/latency tradeoffs. The decision needs to be made explicitly during Phase 1 planning, not deferred.
- **Dashboard virtual rendering at scale:** At 5-20 agents the dashboard needs virtual list rendering. `@tanstack/react-virtual` is the likely solution but needs confirmation during Phase 6 planning.

---

## Sources

### Primary (HIGH confidence)
- [Claude Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python) — ClaudeSDKClient API, session management, streaming
- [claude-agent-sdk PyPI](https://pypi.org/project/claude-agent-sdk/) — version 0.1.48, Python 3.10+
- [Claude Code Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams) — official architecture reference for multi-agent coordination
- [Manage costs effectively — Claude Code official docs](https://code.claude.com/docs/en/costs) — token cost controls
- [Race condition: .claude.json corruption — GitHub Issues #28847, #29036, #29153](https://github.com/anthropics/claude-code/issues/28847) — verified state corruption bug
- [Why Do Multi-Agent LLM Systems Fail? — arXiv 2503.13657](https://arxiv.org/html/2503.13657v1) — peer-reviewed, 150+ execution traces, 79% failure from spec/coordination failures
- [Effective harnesses for long-running agents — Anthropic Engineering](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — official Anthropic guidance
- [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) — security pitfalls
- [Prompt injection / cross-agent trust boundary attacks — arXiv 2506.23260](https://arxiv.org/html/2506.23260v1) — peer-reviewed security research
- [watchfiles PyPI](https://pypi.org/project/watchfiles/) — version 1.1.1, asyncio `awatch()` API
- [FastAPI PyPI](https://pypi.org/project/fastapi/) — version 0.135.1
- [Pydantic v2.12 release notes](https://pydantic.dev/articles/pydantic-v2-12-release) — v2 stability

### Secondary (MEDIUM confidence)
- [zed-industries/claude-code-acp DeepWiki](https://deepwiki.com/zed-industries/claude-code-acp/2.2-basic-usage) — ACP protocol, NDJSON over stdio
- [ACP Server Protocol](https://acpserver.org/) — JSON-RPC message format
- [Claude Code Sub-Agent Cost Explosion — AICosts.ai](https://www.aicosts.ai/blog/claude-code-subagent-cost-explosion-887k-tokens-minute-crisis) — real-world 887K tokens/minute case study
- [TanStack Query + WebSockets](https://blog.logrocket.com/tanstack-query-websockets-real-time-react-data-fetching/) — hybrid React Query + WebSocket pattern
- [React State Management 2025](https://dev.to/cristiansifuentes/react-state-management-in-2025-context-api-vs-zustand-385m) — Zustand as default for dashboards
- [ccswarm GitHub](https://github.com/nwiizo/ccswarm) — active OSS multi-agent reference implementation
- [ComposioHQ agent-orchestrator](https://github.com/ComposioHQ/agent-orchestrator) — active OSS reference for CI-integrated orchestration
- [Multi-agent workflows often fail — GitHub Blog](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/) — practical guidance
- [Simon Willison — Agentic Engineering Patterns: Anti-patterns](https://simonwillison.net/guides/agentic-engineering-patterns/anti-patterns/) — authoritative practitioner
- [Human-In-The-Loop Software Development Agents — arXiv 2025](https://arxiv.org/abs/2411.12924) — peer-reviewed research on intervention patterns

---
*Research completed: 2026-03-10*
*Ready for roadmap: yes*
