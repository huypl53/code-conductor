# Conductor

Multi-agent coding orchestration. Describe what to build, and Conductor breaks it down, spawns a team of AI coding agents, manages their work in real-time, reviews output, and delivers coherent code.

```
conductor run "Add user authentication with JWT" --auto
```

```
 Agent              Task                              Status
 ─────────────────────────────────────────────────── ───────────
 agent-abc-001      Add auth middleware                complete
 agent-def-002      Create JWT token service           running
 agent-ghi-003      Write auth integration tests       running
```

Or chat interactively:

```
$ conductor
conductor> Add a REST endpoint for user profiles
Handling directly — reading existing routes...
```

## How It Works

1. **You describe a feature** in plain language
2. **The orchestrator** (a Claude Code agent) decomposes it into parallel sub-tasks
3. **Specialized agents** are spawned — one per sub-task — and work concurrently
4. **The orchestrator reviews** each agent's output, sends feedback if needed, and the agent revises
5. **Target files are verified** — the orchestrator checks that each agent's output file exists on disk before marking the task complete
6. **An optional build check** runs after all tasks finish — catching cross-file errors that per-task review cannot detect
7. **You get working code** when all tasks pass review and verification

Agents coordinate through a shared state file (`.conductor/state.json`) with file-level ownership to prevent conflicts. The orchestrator manages dependencies, decides team size dynamically, and handles escalation.

## Features

- **Interactive chat TUI** — run `conductor` with no args for a conversational coding interface
- **Smart delegation** — simple tasks handled directly, complex work spawned to sub-agent teams
- **Dynamic decomposition** — orchestrator breaks work into parallel tasks based on complexity
- **Concurrent agents** — multiple agents work simultaneously with dependency-aware scheduling
- **Code review loop** — orchestrator reviews output, sends structured feedback, agents revise
- **Task verification** — target file existence checks prevent tasks from being marked complete when output is missing
- **Build verification** — optional post-run build command (e.g. `npx tsc --noEmit`) catches cross-file errors
- **Two modes** — `--auto` for autonomous execution, interactive for human-in-the-loop
- **Session persistence** — agent state, conversations, and progress survive restarts
- **Resume support** — `conductor run --resume` picks up interrupted orchestrations; `conductor --resume` restores chat sessions
- **Intervention controls** — cancel, redirect, or send feedback to agents mid-task
- **File ownership** — prevents merge conflicts by assigning file-level locks per agent
- **Web dashboard** — real-time agent monitoring with expandable detail cards
- **ACP protocol** — agents communicate via the Agent Communication Protocol

## Installation

**Core CLI** (requires Python 3.12+):

```bash
pip install conductor-ai
```

**Web dashboard** (optional, requires Node.js 22+):

```bash
npm install -g conductor-dashboard
```

**API key:**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## Quick Start

### Interactive chat

```bash
cd ~/my-project
conductor
```

Type requests naturally. The orchestrator decides whether to handle directly (simple edits) or delegate to a sub-agent team (complex features). Slash commands:

| Command    | Effect                                     |
|------------|--------------------------------------------|
| `/help`    | Show all available commands                 |
| `/status`  | Show active sub-agents and their progress   |
| `/resume`  | Resume a previous orchestration             |
| `/exit`    | Exit the chat                               |

### Batch mode (automatic)

```bash
conductor run "Add a REST endpoint for user profiles" --auto
```

### Batch mode (interactive)

```bash
conductor run "Refactor the payment module"
```

The orchestrator asks clarifying questions before starting. During execution you can intervene:

| Command    | Effect                                  |
|------------|-----------------------------------------|
| `cancel`   | Cancel an agent and reassign its task   |
| `feedback` | Send a message to a running agent       |
| `redirect` | Change an agent's direction mid-task    |

### Build verification

Add `--build-command` to catch cross-file errors after all tasks complete:

```bash
conductor run "Add OAuth login" --auto --build-command "npx tsc --noEmit"
```

The build command can also be set in `.conductor/config.json` so it persists across runs:

```json
{
  "build_command": "npx tsc --noEmit"
}
```

Common build commands by language:

| Language   | Command                         |
|------------|---------------------------------|
| TypeScript | `npx tsc --noEmit`              |
| Rust       | `cargo check`                   |
| Go         | `go build ./...`                |
| Python     | `mypy src/` or `ruff check src/`|

### Resume interrupted work

```bash
# Resume an interrupted batch orchestration
conductor run --resume --repo ~/my-project

# Resume a chat session (opens picker)
conductor --resume
```

Resume verifies that completed tasks' target files actually exist on disk. If a file is missing (e.g. an agent was marked complete but never wrote the file), the task is automatically re-run.

### With web dashboard

The `--dashboard-port` flag works with all modes — batch, interactive chat, and resume:

```bash
# Terminal 1 — batch mode with dashboard
conductor run "Add dark mode" --auto --dashboard-port 8000

# Terminal 1 — interactive chat with dashboard
conductor --dashboard-port 8000

# Terminal 1 — resume a chat session with dashboard
conductor --resume --dashboard-port 8000

# Terminal 2 — start the dashboard frontend
conductor-dashboard 4173

# Open http://localhost:4173
```

## Architecture

```
┌──────────────────────────────────────────────────┐
│                  You (CLI / Dashboard)            │
└──────────┬───────────────────────┬───────────────┘
           │                       │
    ┌──────▼──────┐      ┌────────▼────────┐
    │  CLI (Rich) │      │  Web Dashboard  │
    │  Python     │      │  React + Vite   │
    └──────┬──────┘      └────────┬────────┘
           │                      │ WebSocket
    ┌──────▼──────────────────────▼─────────┐
    │            Orchestrator               │
    │  Decomposer → Scheduler → Monitor    │
    │  Reviewer → Verification → Build     │
    └──────┬──────────┬──────────┬─────────┘
           │ ACP      │ ACP      │ ACP
    ┌──────▼───┐ ┌────▼────┐ ┌──▼────────┐
    │ Agent 1  │ │ Agent 2 │ │ Agent N   │
    └──────────┘ └─────────┘ └───────────┘
           │          │            │
    ┌──────▼──────────▼────────────▼───────┐
    │     .conductor/state.json            │
    │     (shared state, file-locked)      │
    └──────────────────────────────────────┘
```

### Packages

| Package | Language | Description |
|---------|----------|-------------|
| `conductor-ai` | Python | Orchestrator, ACP client, state management, CLI |
| `conductor-dashboard` | TypeScript | React web dashboard with real-time WebSocket updates |

### Core modules

| Module | Purpose |
|--------|---------|
| `orchestrator/decomposer` | Breaks features into parallel sub-tasks |
| `orchestrator/orchestrator` | Spawn loop, file verification gate, build check, resume logic |
| `orchestrator/scheduler` | Dependency-aware task scheduling with `asyncio.wait(FIRST_COMPLETED)` |
| `orchestrator/reviewer` | Reviews agent output and provides structured feedback |
| `orchestrator/escalation` | Routes decisions — auto mode uses best judgment, interactive escalates to human |
| `orchestrator/ownership` | File-level locks to prevent agent conflicts |
| `acp/client` | ACP protocol communication with agents |
| `state/manager` | File-locked shared state with Pydantic v2 models |
| `cli/chat` | Interactive chat TUI with streaming, session persistence |
| `cli/delegation` | Smart delegation — direct tool use vs sub-agent spawning |
| `dashboard/` | FastAPI backend serving WebSocket updates to the React frontend |

## Project Configuration

**`CLAUDE.md`** — Place in your project root. Agents read this at startup for codebase conventions:

```markdown
# My Project
- Use TypeScript strict mode
- All API routes go in src/api/
- Write tests in Vitest, not Jest
```

**`.conductor/config.json`** — Persistent configuration for the orchestrator:

```json
{
  "build_command": "npx tsc --noEmit"
}
```

**`.memory/`** — Agents write cross-session knowledge here so future agents benefit without rediscovering patterns.

## Tech Stack

- **Core:** Python 3.12+, asyncio, Pydantic v2, filelock, FastAPI, Claude Agent SDK
- **Dashboard:** React 19, Vite 7, Tailwind CSS 4, TypeScript
- **Protocol:** ACP (Agent Communication Protocol)
- **Distribution:** pip + npm, monorepo with uv + pnpm

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full development guide.

```bash
# Clone and install
git clone https://github.com/your-org/conductor.git
cd conductor
uv sync
pnpm install

# Run tests
cd packages/conductor-core && uv run pytest
cd packages/conductor-dashboard && pnpm test

# Dev dashboard
cd packages/conductor-dashboard && pnpm dev
```

## License

MIT
