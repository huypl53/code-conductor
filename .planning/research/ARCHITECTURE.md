# Architecture Research

**Domain:** Multi-agent coding orchestration framework
**Researched:** 2026-03-10
**Confidence:** HIGH (core components), MEDIUM (ACP integration specifics)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Human Layer                                │
│  ┌──────────────────────┐     ┌───────────────────────────────┐  │
│  │      CLI Interface   │     │     Web Dashboard (Node.js)   │  │
│  │  (Python, ACP client)│     │  React UI + WebSocket client  │  │
│  └──────────┬───────────┘     └──────────────┬────────────────┘  │
└─────────────┼────────────────────────────────┼───────────────────┘
              │ ACP (ndjson/stdio)              │ WebSocket / HTTP
              ▼                                ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Orchestration Layer (Python)                  │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              Orchestrator Process                           │  │
│  │  (Claude Code agent + orchestration skills via ACP)         │  │
│  │                                                             │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐ │  │
│  │  │ ACP Server   │  │ Agent Manager│  │  State Manager    │ │  │
│  │  │ (human link) │  │ (spawn/kill) │  │ (state.json r/w)  │ │  │
│  │  └──────────────┘  └──────┬───────┘  └───────────────────┘ │  │
│  └──────────────────────────┼──────────────────────────────────┘  │
│                              │ ACP (ndjson/stdio) per agent        │
│         ┌────────────────────┼───────────────────────┐            │
│         ▼                    ▼                        ▼            │
│  ┌─────────────┐    ┌─────────────────┐    ┌──────────────────┐  │
│  │  Sub-Agent  │    │   Sub-Agent     │    │   Sub-Agent      │  │
│  │  (ACP proc) │    │   (ACP proc)    │    │   (ACP proc)     │  │
│  └─────────────┘    └─────────────────┘    └──────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
              │                    │                        │
              ▼                    ▼                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Shared State Layer (Filesystem)              │
│                                                                   │
│  ┌──────────────────────┐  ┌─────────────┐  ┌────────────────┐  │
│  │ .conductor/state.json│  │  .memory/   │  │ .claude/ +     │  │
│  │ (task coordination)  │  │ (shared kb) │  │ CLAUDE.md      │  │
│  └──────────────────────┘  └─────────────┘  └────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| CLI Interface | Accept human input, stream orchestrator responses, display agent status | Python, ACP client connecting to orchestrator via stdio |
| Web Dashboard | Visual real-time view of all agents, tasks, logs; layered visibility | Node.js + React, WebSocket consumer of dashboard API |
| Dashboard API Server | Bridge between orchestrator state and dashboard clients | Python FastAPI or equivalent, WebSocket broadcast, REST for initial state |
| Orchestrator Process | Plan, delegate, review, intervene; respond to human via ACP; spawn/manage sub-agents | Claude Code agent process with orchestration skills |
| ACP Server (in orchestrator) | Receive messages from human-facing CLI; send status updates upstream | Python ACP adapter, wraps orchestrator's Claude agent |
| Agent Manager | Spawn sub-agent processes via ACP, track lifecycle, route messages | Python asyncio subprocess manager |
| State Manager | Read/write `.conductor/state.json` with safe concurrent access; watch for changes | Python with filelock, emit events on state changes |
| Sub-Agent Process | Execute assigned coding tasks; write status/output to state; ask questions via ACP | Any ACP-compatible agent (Claude Code, etc.) as subprocess |
| Shared State File | Single coordination backbone: task assignments, status, outputs, interfaces, dependencies | `.conductor/state.json`, JSON, file-locked writes |
| Shared Memory | Cross-agent knowledge: interfaces, decisions, context fragments | `.memory/` directory, Markdown/JSON files per topic |
| Repo Config | Project instructions inherited by all agents automatically | `.claude/`, `CLAUDE.md`, standard Claude Code discovery |

## Recommended Project Structure

```
conductor/                        # Python package (pip-installable)
├── __init__.py
├── cli/
│   ├── __init__.py
│   └── main.py                   # Entry point: `conductor run`, `conductor status`
├── orchestrator/
│   ├── __init__.py
│   ├── process.py                # Spawn/manage orchestrator Claude Code process
│   ├── acp_bridge.py             # ACP client: human → orchestrator, responses upstream
│   └── skills/                   # Orchestration skills installed into Claude Code
│       ├── plan.md
│       ├── delegate.md
│       └── review.md
├── agents/
│   ├── __init__.py
│   ├── manager.py                # Spawn/kill/track sub-agent processes
│   ├── acp_client.py             # ACP client per sub-agent connection
│   └── identity.py               # Agent identity model (name, role, target, materials)
├── state/
│   ├── __init__.py
│   ├── manager.py                # state.json read/write with file locking
│   ├── models.py                 # Pydantic models for Task, Agent, Dependency
│   └── watcher.py                # File watcher → emit events on changes
├── dashboard/
│   ├── __init__.py
│   ├── server.py                 # FastAPI server: REST + WebSocket for dashboard
│   └── broadcaster.py            # Fan-out state events to WebSocket clients
├── memory/
│   ├── __init__.py
│   └── manager.py                # Read/write .memory/ shared knowledge files
└── config.py                     # Conductor config (mode, paths, concurrency limits)

conductor-dashboard/               # Node.js package (npm-installable)
├── package.json
├── src/
│   ├── App.tsx                    # Root with WebSocket provider
│   ├── components/
│   │   ├── AgentCard.tsx          # Per-agent status: collapsed → expanded → live stream
│   │   ├── TaskBoard.tsx          # Task dependency graph, status overview
│   │   ├── LogStream.tsx          # Live log viewer with virtualization
│   │   └── Notifications.tsx      # Smart alerts: errors, completions, interventions
│   ├── hooks/
│   │   ├── useAgentState.ts       # Consume WebSocket state updates
│   │   └── useTaskGraph.ts        # Derive dependency graph from state
│   └── lib/
│       └── wsClient.ts            # WebSocket connection, reconnect logic
└── vite.config.ts
```

### Structure Rationale

- **orchestrator/**: The orchestrator is a Claude Code process managed externally — this keeps process lifecycle separate from agent logic
- **agents/**: Each sub-agent is an independent process connected via ACP; the manager tracks them as a pool
- **state/**: State management is isolated because it's the coordination backbone — file locking and change detection must be reliable
- **dashboard/**: Separate Python server bridges the Python orchestration world to the Node.js dashboard world via WebSocket; avoids tight coupling
- **conductor-dashboard/**: Independent npm package — can be installed and run separately, or bundled as a Python package asset

## Architectural Patterns

### Pattern 1: ACP All The Way Down

**What:** Use ACP as the single inter-process communication protocol at both layers. The human talks to the orchestrator via ACP. The orchestrator talks to each sub-agent via ACP. Same protocol, same primitives, same tooling.

**When to use:** Always — this is the core architectural constraint.

**Trade-offs:**
- Pro: orchestrator can observe sub-agent tool calls in real-time, stream agent activity to dashboard, intervene at any message boundary
- Pro: no custom protocol to maintain; interoperability with any ACP-compatible agent
- Con: ACP is relatively new; implementation details may shift; requires careful subprocess lifecycle management

**Example:**
```python
# Orchestrator as ACP client connecting to a sub-agent
async def spawn_agent(self, identity: AgentIdentity) -> AgentConnection:
    process = await asyncio.create_subprocess_exec(
        "claude", "--acp",  # Sub-agent speaks ACP over stdio
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    conn = ACPClient(process.stdin, process.stdout)
    await conn.send_spawn_prompt(identity.system_prompt)
    return AgentConnection(identity=identity, process=process, acp=conn)
```

### Pattern 2: Shared State File as Coordination Backbone

**What:** `.conductor/state.json` is the single source of truth. The orchestrator writes task assignments and dependency graphs. Sub-agents write status, outputs, and interface declarations. All agents can read the full state to understand the team's work. Writes are file-locked to prevent corruption.

**When to use:** For all inter-agent coordination that doesn't need real-time interaction — task assignment, status tracking, output publishing.

**Trade-offs:**
- Pro: durable (filesystem survives crashes); asynchronous reads (agents check when ready); simple mental model
- Pro: all agents can see the whole picture without message routing
- Con: not suitable for real-time question/answer (use ACP for that); requires file locking discipline; state can grow large on long runs

**Example:**
```python
from filelock import FileLock

class StateManager:
    def __init__(self, state_path: Path):
        self.path = state_path
        self.lock = FileLock(str(state_path) + ".lock")

    def update_task(self, task_id: str, update: dict):
        with self.lock:
            state = self._read()
            state["tasks"][task_id].update(update)
            self._write(state)
```

### Pattern 3: Layered Visibility for Verbose Agent Output

**What:** Agent conversations are extremely verbose. The dashboard presents three layers: (1) collapsed status card showing agent name, role, current task, status; (2) expanded view showing recent messages and tool calls; (3) live stream of full conversation. Each layer is opt-in.

**When to use:** Always in the dashboard. Avoid surfacing raw conversation dumps at the top level.

**Trade-offs:**
- Pro: prevents information overload; users see signal not noise
- Con: requires summary extraction from raw agent output (inference or heuristics)

### Pattern 4: Supervisor Pattern with Escalation Modes

**What:** Orchestrator mediates all coordination — sub-agents never communicate peer-to-peer. The orchestrator has two escalation modes: `--auto` (best judgment, log decisions) and interactive (ask the human when uncertain).

**When to use:** Always — no direct sub-agent communication is an explicit design constraint.

**Trade-offs:**
- Pro: all coordination visible to orchestrator; single intervention point; simpler reasoning about system state
- Con: orchestrator becomes bottleneck for high-frequency coordination; adds latency on question/answer cycles

## Data Flow

### Task Assignment Flow

```
Human describes feature
    ↓ ACP message
Orchestrator (Claude Code) plans work
    ↓ writes to .conductor/state.json
  [task_id: "auth-module", status: "assigned", agent: "agent-1", deps: ["..."] ]
    ↓ ACP spawn_prompt
Sub-Agent process starts, reads identity + task from state.json
    ↓ executes coding task (file edits, tests, etc.)
    ↓ writes to .conductor/state.json
  [task_id: "auth-module", status: "complete", output: "src/auth.py", interfaces: {...}]
    ↓ ACP idle notification → orchestrator
Orchestrator reviews output, gives feedback or marks done
    ↓ ACP message to human
Human sees result in CLI or dashboard
```

### Dashboard Real-Time Flow

```
State change (sub-agent writes state.json)
    ↓ State watcher detects file change
    ↓ State Manager reads new state
    ↓ Emits event internally (asyncio event bus or queue)
Dashboard API Server (Python FastAPI)
    ↓ Receives event
    ↓ Broadcasts delta via WebSocket
Web Dashboard (Node.js/React)
    ↓ Receives WebSocket message
    ↓ Updates component state
Human sees live agent status
```

### Human Intervention Flow (Interactive Mode)

```
Sub-agent encounters ambiguity
    ↓ ACP permission/question request → orchestrator
Orchestrator evaluates:
  [--auto mode] → uses best judgment → responds via ACP → logs decision
  [interactive mode] → escalates to human via ACP upstream
    ↓ CLI prints prompt / Dashboard shows notification
Human responds
    ↓ ACP message → orchestrator → ACP message → sub-agent
Sub-agent resumes
```

### Agent Lifecycle Flow

```
Orchestrator decides to spawn agent
    ↓ Agent Manager creates AgentIdentity (name, role, target, materials)
    ↓ Spawns subprocess (e.g., `claude --acp`)
    ↓ Sends spawn prompt via ACP
    ↓ Writes agent record to state.json
Agent works autonomously
    ↓ Writes status updates to state.json
    ↓ Asks questions via ACP (orchestrator answers)
Agent signals completion / goes idle
    ↓ Orchestrator reviews output
    ↓ Sends feedback or marks task complete in state.json
    ↓ Orchestrator either reassigns agent or sends shutdown via ACP
Agent acknowledges shutdown
    ↓ Process exits cleanly
    ↓ Agent Manager removes from pool
```

## Build Order (Dependencies)

The components have clear build dependencies. Build in this order:

```
Phase 1: Shared Foundation
  state/models.py          ← no dependencies
  state/manager.py         ← depends on models
  agents/identity.py       ← depends on models
  config.py                ← no dependencies

Phase 2: ACP Communication Layer
  agents/acp_client.py     ← depends on ACP library, identity
  orchestrator/acp_bridge.py ← depends on ACP library

Phase 3: Orchestrator Lifecycle
  orchestrator/process.py  ← depends on acp_bridge, state/manager
  orchestrator/skills/     ← plain text, no code dependencies
  agents/manager.py        ← depends on acp_client, state/manager, identity

Phase 4: CLI + Basic Loop
  cli/main.py              ← depends on orchestrator/process, agents/manager

Phase 5: State Watching + Dashboard Backend
  state/watcher.py         ← depends on state/manager
  dashboard/broadcaster.py ← depends on state/watcher
  dashboard/server.py      ← depends on broadcaster

Phase 6: Dashboard Frontend
  conductor-dashboard/     ← depends on dashboard/server being running
```

**Key dependency constraint:** The CLI provides a working product before the dashboard exists. Build phases 1-4 first to validate the core loop (human → orchestrator → agents → results) before investing in dashboard infrastructure.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-5 agents | Current design; state.json is fine; single orchestrator process |
| 5-20 agents | Monitor state.json file size; consider write batching; dashboard needs virtual list rendering for agent cards |
| 20+ agents | state.json write contention becomes real; consider splitting into per-agent files with a manifest; orchestrator may need sub-orchestrators |

### Scaling Priorities

1. **First bottleneck:** State file write contention. With many agents writing concurrently, file locking creates serialization. Fix: per-agent state files with an index, merge on read.
2. **Second bottleneck:** Orchestrator context window. Tracking many tasks/agents in one context hits limits. Fix: summarization/rolling context in orchestrator skills; sub-orchestrator delegation.

## Anti-Patterns

### Anti-Pattern 1: Peer-to-Peer Agent Communication

**What people do:** Allow agents to message each other directly when they need to coordinate.
**Why it's wrong:** Loses observability; orchestrator can't see or intervene in side-channel conversations; creates coordination cycles that are hard to reason about; explicitly out of scope per design.
**Do this instead:** All inter-agent coordination goes through state.json (async) or via orchestrator as ACP intermediary (real-time questions).

### Anti-Pattern 2: Raw Log Dumps in Dashboard

**What people do:** Stream every ACP message directly to the dashboard UI.
**Why it's wrong:** Agent conversations are extremely verbose; raw dumps cause information overload; important signals (errors, completions) get buried.
**Do this instead:** Implement layered visibility — status summary by default, expandable to messages, with opt-in live stream. Surface smart notifications for errors, completions, and intervention requests.

### Anti-Pattern 3: Blocking the Orchestrator on Sub-Agent Work

**What people do:** Have the orchestrator await each agent's completion sequentially before assigning the next task.
**Why it's wrong:** Eliminates the core value of multi-agent parallelism; makes orchestrator unavailable for human interaction and other agents' questions.
**Do this instead:** Orchestrator assigns tasks and monitors asynchronously via state.json changes and ACP idle notifications. Use asyncio event loop; never block on agent completion.

### Anti-Pattern 4: Skipping File Locking on State Writes

**What people do:** Write to state.json directly without locking because "it's fast enough."
**Why it's wrong:** Multiple agents writing simultaneously causes JSON corruption or partial writes. State corruption during a long run can destroy all work in progress.
**Do this instead:** Always use filelock (or equivalent) for state.json writes. Read-modify-write inside the lock. Keep critical sections short.

### Anti-Pattern 5: Hard-Coding Agent Count

**What people do:** Spawn a fixed number of agents at startup.
**Why it's wrong:** Over-allocates tokens on simple tasks; under-allocates on complex ones; orchestrator intelligence about team sizing is lost.
**Do this instead:** Let the orchestrator decide team size based on the work. Pass the orchestrator skills/instructions that teach it to reason about parallelism and cost.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Claude Code (orchestrator) | Subprocess with ACP stdio | Orchestrator IS a Claude Code process; spawn with `claude --acp` |
| Sub-agents (ACP-compatible) | Subprocess with ACP stdio per agent | Any ACP agent; identity injected via spawn prompt |
| @zed-industries/claude-agent-acp | npm adapter, imported by orchestrator Node.js shim if needed | Adapter between Claude Agent SDK and ACP; verify current package name |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| CLI ↔ Orchestrator Process | ACP over stdio | Human messages in, orchestrator responses + status out |
| Orchestrator ↔ Agent Manager | Python in-process function calls | Same Python process; agent manager is a library not a service |
| Agent Manager ↔ Sub-Agents | ACP over stdio per subprocess | One ACP connection per agent; asyncio-managed |
| State Manager ↔ All Agents | Filesystem (state.json) | File-locked writes; watched by state watcher for events |
| Orchestrator Process ↔ Dashboard Server | Python in-process event queue | State events fan out to WebSocket broadcaster |
| Dashboard Server ↔ Dashboard UI | WebSocket (delta events) + HTTP (initial load) | Node.js client subscribes; receives state diffs not full state |
| Python Package ↔ Node.js Dashboard | HTTP/WebSocket (dashboard server) | Two separate installable packages; dashboard connects to Python server |

## Sources

- [Claude Code Agent Teams Documentation](https://code.claude.com/docs/en/agent-teams) — official architecture reference for multi-agent coordination with shared task lists and ACP
- [Agent Client Protocol Overview](https://agentclientprotocol.com/) — ACP: ndjson over stdio, JSON-RPC 2.0, session lifecycle
- [ACP Protocol Deep Dive (KiloCode)](https://deepwiki.com/Kilo-Org/kilocode/13.3-acp-protocol) — ACP server/client message flow, permission handling, SSE events
- [Supervisor Agent Pattern](https://rajatpandit.com/agent-supervisor-pattern/) — Supervisor pattern: orchestrator mediates all coordination
- [Azure Scheduler-Agent-Supervisor Pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/scheduler-agent-supervisor) — Durable state store for task status; supervisor monitors for failures
- [Filesystem-Based Agent State](https://agentic-patterns.com/patterns/filesystem-based-agent-state/) — Using filesystem as coordination backbone for agents
- [FastAPI + WebSockets Real-Time Dashboard](https://testdriven.io/blog/fastapi-postgres-websockets/) — Python WebSocket broadcast architecture for real-time dashboards
- [Multi-Agent Orchestration Patterns (Azure)](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) — Supervisor, sequential, parallel patterns with trade-offs
- [Python asyncio Subprocess Management](https://docs.python.org/3/library/asyncio-subprocess.html) — Subprocess spawning, SIGTERM/SIGKILL lifecycle, graceful shutdown

---
*Architecture research for: Conductor — multi-agent coding orchestration framework*
*Researched: 2026-03-10*
