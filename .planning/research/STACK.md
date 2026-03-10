# Stack Research

**Domain:** Multi-agent coding orchestration framework (Python core + Node.js dashboard monorepo)
**Researched:** 2026-03-10
**Confidence:** HIGH (core Python agent stack verified against official docs; Node.js dashboard stack verified against current sources)

---

## Recommended Stack

### Python Core — Agent Orchestration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `claude-agent-sdk` | 0.1.48 | Spawn and converse with Claude Code sub-agents; receive streaming ACP messages | Official Anthropic SDK — the only supported way to drive Claude Code programmatically. Bundles Claude Code CLI, handles session management, interrupts, and streaming. `ClaudeSDKClient` (not `query()`) is the right class because Conductor needs persistent sessions and mid-stream interrupts. |
| Python | 3.11+ | Runtime | 3.11+ for `asyncio.TaskGroup` (clean parallel agent concurrency), tomllib stdlib, and better error messages. SDK requires 3.10+; 3.11 is the safe minimum for production features. |
| `asyncio` (stdlib) | 3.11 | Concurrent process management | The natural event loop for managing multiple ACP stdio streams without threads. `asyncio.create_subprocess_exec` + `StreamReader` is the idiomatic pattern for line-by-line NDJSON parsing from subprocesses. |
| `pydantic` | 2.12.x | State schema validation + JSON serialization | v2 is Rust-backed (10× faster). Models `state.json` schema precisely with `.model_dump_json()` for atomic file writes. Required for FastAPI integration. Use `model_config = ConfigDict(validate_assignment=True)` to catch state corruption at assignment time. |
| `fastapi` | 0.135.x | REST + WebSocket API bridge to dashboard | Dual-role: serves REST endpoints for state snapshots AND WebSocket connections for live agent event streaming. First-class async support, no impedance mismatch with asyncio subprocess management. |
| `uvicorn` | 0.34.x | ASGI server | The standard production ASGI server for FastAPI. Run with `--lifespan on` to wire FastAPI startup events to the orchestrator event loop. |
| `typer` | 0.24.x | CLI interface | Type-hint–based CLI on top of Click. Matches FastAPI's style (same author), autocompletion built in, `async` command support added in 0.10.0. For Conductor's `conductor chat` and `conductor status` commands. |
| `rich` | 14.x | Terminal output / live CLI display | Live multi-panel CLI display (`rich.live.Live`) for showing agent status in the terminal without a full TUI. Paired with Typer for the `conductor chat` interactive mode. Typer uses Rich internally so it's a zero-cost dependency. |
| `watchfiles` | 1.1.1 | Watch `.conductor/state.json` for changes | Rust-backed file watcher, asyncio-native (`awatch` async API). Used by dashboard backend to push state changes to WebSocket clients without polling. Faster and lighter than `watchdog`. |

### Node.js Dashboard

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| React | 19.x | UI framework | React 19 makes concurrent rendering the default, not opt-in. Handles high-frequency WebSocket updates without manual batching. `useTransition` prevents agent activity streams from blocking input. |
| Vite | 6.x | Build tool + dev server | De-facto standard for React SPAs in 2025. HMR is instant. No Next.js overhead needed — Conductor dashboard is a SPA served by the Python backend, not a Next.js app. |
| TypeScript | 5.x | Type safety | Shared ACP message types between dashboard and Python schema (via generated JSON Schema → TypeScript types) prevent contract drift. |
| `shadcn/ui` | latest | Component library | Copy-owned components (not a black-box dependency). Ships Tailwind CSS v4 compatible primitives. The collapsible panel pattern needed for layered agent visibility is built in. Use `Accordion` + `Sheet` for the expand-on-demand agent detail view. |
| Tailwind CSS | 4.x | Styling | Required by shadcn/ui. v4 uses native CSS cascade layers, no separate config file needed for most projects. |
| Zustand | 5.x | Client state management | Minimal boilerplate for managing real-time state from WebSocket messages. Zustand's `subscribeWithSelector` middleware enables targeted component re-renders when only one agent's status changes — critical for preventing full-tree re-renders in a multi-agent dashboard. |
| TanStack Query | 5.x | Server state + REST polling | Manages REST endpoint state (agent list, task history, session data). Use alongside Zustand: TanStack Query for REST, Zustand for WebSocket push. `refetchInterval` as WebSocket fallback. |
| `@zed-industries/claude-code-acp` | 0.16.0 | ACP protocol adapter (Node.js) | The reference ACP implementation for JavaScript. Only needed if the dashboard's Node.js layer needs to speak ACP directly (e.g., if the Node.js server acts as an ACP relay). For v1, this is optional — the Python backend handles all ACP communication and exposes WebSocket to the dashboard. Include in `devDependencies` for ACP message type reference. |

### Monorepo Tooling

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `pnpm` workspaces | 9.x | Node.js monorepo dependency management | Disk-efficient content-addressable store. Built-in workspace protocol (`workspace:*`) for internal package references. No Turborepo needed for a two-package monorepo. |
| `uv` | 0.5.x | Python dependency management + packaging | 10–100× faster than pip. Generates deterministic `uv.lock` cross-platform lockfiles. `uv build` + `uv publish` replaces setuptools for distributing the pip package. Standard in 2025 Python ecosystem. |
| `pyproject.toml` (uv_build backend) | — | Python package definition | Standard since PEP 517. `uv_build` is the zero-config backend for pure-Python packages. Defines the `conductor` CLI entry point. |
| `package.json` + `npm` | — | Node.js dashboard package | Standard. `conductor-dashboard` npm package for the web UI. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` + `pytest-asyncio` | Python test runner with async support | `asyncio_mode = "auto"` in `pyproject.toml` avoids per-test decorators. |
| `ruff` | Python linting + formatting | Replaces flake8, isort, black in one Rust-backed tool. Run via `uv run ruff check`. |
| `mypy` | Python static type checking | Catches pydantic model misuse at CI time. |
| Vitest | Node.js test runner | Vite-native, same config as build. Jest-compatible API. |
| ESLint + `typescript-eslint` | TypeScript linting | Standard for React/TypeScript projects. |

---

## Installation

```bash
# Python core (development)
uv sync
# or: uv add claude-agent-sdk fastapi "uvicorn[standard]" pydantic typer rich watchfiles

# Python core (user install from pip)
pip install conductor-ai

# Node.js dashboard (development)
pnpm install

# Node.js dashboard (user install from npm)
npm install -g conductor-dashboard
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `claude-agent-sdk` (`ClaudeSDKClient`) | Direct `asyncio.create_subprocess_exec` + raw NDJSON parsing | Only if ACP protocol changes and SDK lags behind; adds significant protocol maintenance burden |
| `fastapi` WebSocket bridge | Separate Node.js Express server that reads `state.json` | If dashboard needed to be fully standalone with no Python runtime dependency; increases deployment complexity for v1 |
| `watchfiles` | Polling `state.json` on a timer | If the file lives on a remote/network filesystem where inotify isn't available |
| `zustand` | Redux Toolkit | Redux appropriate for teams >5 or complex undo/redo workflows; Zustand is sufficient and far simpler for a single-user dashboard |
| `shadcn/ui` | Radix UI directly | Use Radix directly only if Tailwind CSS is rejected; shadcn/ui is just Radix + Tailwind with pre-styled examples |
| Vite SPA | Next.js | Next.js adds SSR/routing complexity with no benefit for a locally-run dashboard that's always online |
| `uv` + `uv_build` | Poetry | Poetry is fine but slower; uv is the 2025 default for new Python projects |
| `pydantic` v2 | `dataclasses` + `json` stdlib | Only if runtime validation overhead is measured as a bottleneck (unlikely for state.json sizes) |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `claude-code-sdk` (PyPI) | Deprecated in September 2025, no longer maintained | `claude-agent-sdk` 0.1.48+ |
| LangChain / LangGraph | Heavyweight abstraction built for LLM chains, not ACP subprocess orchestration. Adds >50 transitive dependencies for features Conductor doesn't need | Direct `claude-agent-sdk` + asyncio |
| CrewAI / AutoGen | Prescriptive agent frameworks that assume their own communication model; ACP is the required protocol, not optional | Direct `claude-agent-sdk` |
| Socket.io | Adds polling fallback + room abstraction overhead; browser native WebSocket API + Zustand is sufficient | Native `WebSocket` + Zustand |
| Redux / Redux Toolkit | Excessive for a single-user dashboard; verbose boilerplate slows feature velocity | Zustand |
| `asyncio.create_subprocess_shell` | Shell injection risk when constructing agent commands with user-provided paths | `asyncio.create_subprocess_exec` with args as list |
| `threading` for agent concurrency | Thread safety with subprocess stdio streams is error-prone; asyncio is the right model | `asyncio.TaskGroup` |
| Celery / task queues | Adds Redis/broker dependency for a problem that asyncio.TaskGroup solves in-process | `asyncio.TaskGroup` |

---

## Stack Patterns by Variant

**For the orchestrator's sub-agent lifecycle (spawn → converse → complete):**
- Use `ClaudeSDKClient` (not `query()`) — needs persistent session + interrupt support
- One `ClaudeSDKClient` instance per sub-agent, managed in an asyncio TaskGroup
- Session IDs persisted to `state.json` for restart recovery

**For the dashboard ↔ Python bridge:**
- Use FastAPI WebSocket endpoint at `/ws/events`
- Python backend broadcasts state change events (derived from `watchfiles` + pydantic diffs)
- Dashboard Zustand store subscribes to WebSocket and applies event patches
- TanStack Query handles REST polling for initial state load and session history

**For the CLI interactive mode (`conductor chat`):**
- Use Typer command with `rich.live.Live` context manager
- The CLI itself speaks to the orchestrator's ACP server (same pattern as sub-agents)
- Avoid mixing stdout with ACP NDJSON — route logs to stderr, ACP messages to stdout

**For the Python pip distribution:**
- Entry point: `[project.scripts] conductor = "conductor.cli:app"`
- `uv_build` backend in `pyproject.toml`
- Bundle `@zed-industries/claude-code-acp` Node binary is NOT needed — `claude-agent-sdk` bundles Claude Code CLI directly

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `claude-agent-sdk` ≥0.1.48 | Python 3.10–3.13 | Use Python 3.11 minimum for `TaskGroup` |
| `fastapi` 0.135.x | `pydantic` 2.x only | FastAPI 0.100+ dropped pydantic v1 support |
| `pydantic` 2.12.x | Python 3.10–3.14 | v2.13 in beta; use 2.12.x for stability |
| `shadcn/ui` latest | Tailwind CSS 4.x, React 19 | Tailwind v4 is required from shadcn/ui late-2025 releases onward |
| `watchfiles` 1.1.1 | Python 3.9–3.14 | Asyncio `awatch()` API is stable |
| `typer` 0.24.x | `rich` ≥10.x | Typer bundles Rich for help output; explicit `rich` dep for `Live` display |

---

## Sources

- [Claude Agent SDK Python Reference](https://platform.claude.com/docs/en/agent-sdk/python) — ClaudeSDKClient API, session management, streaming (HIGH confidence, official Anthropic docs)
- [claude-agent-sdk PyPI](https://pypi.org/project/claude-agent-sdk/) — version 0.1.48, Python 3.10+, bundled CLI (HIGH confidence, verified)
- [zed-industries/claude-code-acp DeepWiki](https://deepwiki.com/zed-industries/claude-code-acp/2.2-basic-usage) — ACP protocol, NDJSON over stdio, `@zed-industries/claude-code-acp` 0.16.0 (MEDIUM confidence, third-party wiki)
- [ACP Server Protocol](https://acpserver.org/) — JSON-RPC message format, stdio subprocess model (MEDIUM confidence, official protocol site)
- [watchfiles PyPI](https://pypi.org/project/watchfiles/) — version 1.1.1, asyncio `awatch()` API (HIGH confidence, verified)
- [FastAPI PyPI](https://pypi.org/project/fastapi/) — version 0.135.1, Python 3.10+ (HIGH confidence, verified)
- [Pydantic v2.12 release notes](https://pydantic.dev/articles/pydantic-v2-12-release) — v2 stability, Python 3.14 support (HIGH confidence, official)
- [Python Build Backends 2025](https://medium.com/@dynamicy/python-build-backends-in-2025-what-to-use-and-why-uv-build-vs-hatchling-vs-poetry-core-94dd6b92248f) — uv vs hatchling recommendation (MEDIUM confidence, community article)
- [TanStack Query + WebSockets](https://blog.logrocket.com/tanstack-query-websockets-real-time-react-data-fetching/) — hybrid React Query + WebSocket pattern (MEDIUM confidence, verified against TanStack docs)
- [React State Management 2025](https://dev.to/cristiansifuentes/react-state-management-in-2025-context-api-vs-zustand-385m) — Zustand as default for dashboards (MEDIUM confidence, community consensus)

---
*Stack research for: Conductor — multi-agent coding orchestration framework*
*Researched: 2026-03-10*
