# Architecture Research

**Domain:** Interactive Chat TUI — v1.1 addition to multi-agent orchestration framework
**Researched:** 2026-03-11
**Confidence:** HIGH — based on live codebase inspection + official SDK documentation

---

## Context: What Already Exists (v1.0 Baseline)

This document focuses on the v1.1 additions. Understanding what exists is mandatory before designing new components.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     conductor CLI (Typer + Rich)                      │
│  ┌───────────────────┐  ┌────────────────┐  ┌────────────────────┐   │
│  │  `conductor run`  │  │  input_loop.py  │  │  display_loop.py   │   │
│  │  (batch mode)     │  │  (cmd dispatch) │  │  (Rich Live table)  │   │
│  └─────────┬─────────┘  └───────┬────────┘  └─────────┬──────────┘   │
│            │                    │ human_in/out queues   │ state poll   │
├────────────▼────────────────────▼────────────────────────▼────────────┤
│                         Orchestrator (Python)                          │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  orchestrator.py: run() / run_auto() / resume()                  │  │
│  │  ├── TaskDecomposer (SDK query(), structured JSON output)        │  │
│  │  ├── DependencyScheduler (asyncio.wait FIRST_COMPLETED)         │  │
│  │  ├── _run_agent_loop (ACPClient per task, review/revise cycle)  │  │
│  │  ├── EscalationRouter (auto vs. human via asyncio.Queue pair)   │  │
│  │  └── Interventions: cancel_agent, inject_guidance, pause         │  │
│  └─────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────── ┤
│                       ACP / Claude Agent SDK                           │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │  ACPClient (per sub-agent): ClaudeSDKClient wrapper            │    │
│  │  send() → stream_response() → interrupt()                      │    │
│  │  PermissionHandler → EscalationRouter.resolve()                │    │
│  └───────────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────────── ┤
│                         State Layer (Filesystem)                       │
│  ┌──────────────┐  ┌───────────────────────┐  ┌──────────────────┐   │
│  │ StateManager │  │ .conductor/state.json │  │  SessionRegistry  │   │
│  │ (filelock)   │  │ (ConductorState model)│  │ sessions.json     │   │
│  └──────────────┘  └───────────────────────┘  └──────────────────┘   │
├─────────────────────────────────────────────────────────────────────── ┤
│                  Dashboard (FastAPI + React, optional)                  │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │  dashboard/server.py → WebSocket → conductor-dashboard npm    │     │
│  └──────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

**Critical observation:** `cli/__init__.py` sets `no_args_is_help=True`, so `conductor` with no arguments currently prints help text. The v1.1 TUI requires a new default path when no args are given.

---

## Target Architecture (v1.1 additions in context)

The TUI adds a **conversational loop** execution mode where the orchestrator itself operates as a stateful, multi-turn Claude session with direct tool access — rather than as a one-shot decomposer that spawns agents.

```
┌──────────────────────────────────────────────────────────────────────┐
│                     conductor CLI (Typer + Rich)                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ `conductor run`  │  │  `conductor`      │  │ `conductor       │   │
│  │ (batch mode,     │  │  (no args →      │  │  status`         │   │
│  │  UNCHANGED)      │  │  chat TUI NEW)    │  │  UNCHANGED)      │   │
│  └──────────────────┘  └────────┬─────────┘  └──────────────────┘   │
│                                  │ NEW                                 │
├──────────────────────────────────▼─────────────────────────────────── ┤
│                        Chat TUI Layer (NEW)                            │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  cli/chat.py — ChatSession                                       │  │
│  │  ├── _chat_loop(): async REPL — send prompt, stream response     │  │
│  │  ├── _render_stream(): incremental Rich output per message       │  │
│  │  ├── delegation hook: PostToolUse on Delegate custom tool        │  │
│  │  └── _spawn_agents(): await Orchestrator.run(task_desc)          │  │
│  └────────┬──────────────────────────────────────┬──────────────── ┘  │
│           │ persistent ClaudeSDKClient session    │ fresh Orchestrator │
├───────────▼──────────────────────────────────────▼─────────────────── ┤
│     ClaudeSDKClient (orchestrator chat)      Orchestrator (batch)      │
│  ┌─────────────────────────────┐  ┌──────────────────────────────┐   │
│  │  Persistent session_id       │  │  orchestrator.run(task_desc) │   │
│  │  Tools: Read/Edit/Bash/etc   │  │  (existing v1.0 path,        │   │
│  │  Custom tool: Delegate       │  │   UNCHANGED)                 │   │
│  │  setting_sources: ["project"]│  └──────────────────────────────┘   │
│  └─────────────────────────────┘                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## New Components

### Component 1: `cli/chat.py` — ChatSession

The central new component. Owns the conversational loop end-to-end.

| Responsibility | Implementation |
|---------------|----------------|
| Maintain orchestrator's persistent SDK session | `ClaudeSDKClient` (not `query()`), kept open for the full session lifetime |
| Accept user input | `asyncio.to_thread(input, "> ")` — same pattern as existing `_ainput()` in input_loop.py |
| Send to SDK and stream response | `client.query(user_input)` then `client.receive_response()` |
| Render streaming output | Rich `Console.print()` incremental output per `AssistantMessage` |
| Intercept delegation decisions | `PostToolUse` hook registered on the `Delegate` custom tool |
| Call `Orchestrator.run()` on delegation | `await orchestrator.run(task_desc)` inside the async hook |
| Resume sessions across restarts | Read `session_id` from `chat_persistence.py`, pass `resume=session_id` to `ClaudeSDKClient` |

`ClaudeSDKClient` is the correct API here. The official SDK docs are explicit: `query()` creates a new session each call; `ClaudeSDKClient` is for "continuous conversations, chat interfaces, REPLs" with context preserved across `.query()` calls.

**Confidence:** HIGH — ClaudeSDKClient is the explicitly documented API for this use case.

### Component 2: `cli/commands/chat.py` — Typer command wiring

CLI entry point for the interactive mode. Registers a `chat` command on the Typer app. The `cli/__init__.py` modification also sets `invoke_without_command=True` and a default callback so `conductor` (no args) calls `chat` rather than printing help.

```python
# cli/__init__.py change
app = typer.Typer(
    name="conductor",
    help="Conductor: AI agent orchestration",
    invoke_without_command=True,
)

@app.callback()
def main_callback(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        chat()  # default to chat mode
```

This preserves all existing subcommands without change.

**Confidence:** HIGH — Typer `invoke_without_command` is a documented feature.

### Component 3: `cli/chat_persistence.py` — Chat session store

Reads/writes `.conductor/chat_session.json` with `{"session_id": "...", "started_at": "..."}`. Used to resume the orchestrator's chat session across `conductor` invocations. Follows the same pattern as the existing `SessionRegistry` for sub-agents. Single writer (the one chat session), no filelock required.

### Component 4: Chat system prompt

The orchestrator's identity in chat mode differs from its batch decomposer role. The chat system prompt establishes:
- Role as a senior engineer / coding agent with direct tool access
- Permission to use tools directly for simple/focused tasks
- When to delegate: multi-file features, tasks requiring a team, complex dependency graphs
- How to signal delegation: call the `Delegate` custom tool with a task description

This is a prompt artifact, not a code module, but it drives the smart delegation behavior. Requires iterative tuning.

### Component 5: `Delegate` custom in-process tool

An in-process custom tool (MCP-style, no subprocess) defined using the SDK's tool definition API. The orchestrator SDK session calls this tool when it decides to spawn sub-agents. `ChatSession` intercepts the `PostToolUse` hook, runs `Orchestrator.run(task)`, and returns a summary as the tool result.

```python
DELEGATE_TOOL_SCHEMA = {
    "name": "Delegate",
    "description": "Spawn a team of sub-agents to implement a complex multi-file feature.",
    "input_schema": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "Feature description for the agent team (as if passed to conductor run)"
            }
        },
        "required": ["task"]
    }
}
```

**Confidence:** HIGH — custom in-process tools are a first-class SDK feature, already used conceptually in the existing `ACPClient` via `PermissionHandler`.

---

## What Changes vs. What Stays Unchanged

| Module | Status | Change |
|--------|--------|--------|
| `cli/__init__.py` | MODIFY | Add `chat` command; set `invoke_without_command=True`, add default callback |
| `cli/commands/run.py` | UNCHANGED | Batch mode stays identical |
| `cli/commands/status.py` | UNCHANGED | Status display stays identical |
| `cli/display.py` | UNCHANGED, REUSED | `_build_table()` reused to show agent progress during delegation |
| `cli/input_loop.py` | UNCHANGED | Still used exclusively by `conductor run` |
| `orchestrator/orchestrator.py` | UNCHANGED | `run()`, `run_auto()` called as-is when delegating |
| `acp/client.py` | UNCHANGED | Sub-agents still use `ACPClient` |
| `state/` (all files) | UNCHANGED | `StateManager` + `ConductorState` models unchanged |
| `dashboard/` | UNCHANGED | Optional, still started via `--dashboard-port` |
| **NEW: `cli/chat.py`** | NEW | `ChatSession` class, chat loop, streaming, delegation hook |
| **NEW: `cli/chat_persistence.py`** | NEW | Load/save `.conductor/chat_session.json` |
| **NEW: `cli/commands/chat.py`** | NEW | Typer command wiring |

---

## Data Flow

### Flow 1: Direct Task (Orchestrator Handles Itself)

```
User types: "Show me what files auth.py imports"
    │
    ▼
ChatSession._chat_loop() → client.query(user_input)
    │
    ▼
SDK agent loop: Claude calls Read tool on auth.py
    │
    ▼
client.receive_response() yields AssistantMessage (text + tool calls)
    │
    ▼
ChatSession._render_stream() prints incrementally to terminal
    │
    ▼
ResultMessage received: session complete
    │
    ▼
Session context preserved for next turn (context window accumulates)
```

### Flow 2: Delegated Task (Orchestrator Spawns Sub-Agents)

```
User types: "Implement OAuth login with Google, include tests"
    │
    ▼
ChatSession._chat_loop() → client.query(user_input)
    │
    ▼
SDK agent loop: Claude decides this is multi-file/complex work
Claude calls: Delegate(task="Implement OAuth login with Google, include tests")
    │
    ▼
PostToolUse hook fires in ChatSession._delegation_hook()
    │
    ▼
ChatSession._spawn_agents(task_desc):
    fresh_orchestrator = Orchestrator(state_manager, repo_path, ...)
    await fresh_orchestrator.run(task_desc)  ← existing v1.0 path
    │  spawns agent-A (auth module)
    │  spawns agent-B (tests)
    │  review/revise cycle per agent (unchanged)
    │
    ▼
Orchestrator.run() completes
    │
    ▼
Hook returns: {"result": "Completed 2 tasks: src/auth.py, tests/test_auth.py"}
    │
    ▼
SDK agent loop resumes: Claude reads tool result, produces final response
    │
    ▼
ChatSession._render_stream() displays Claude's summary to user
    │
    ▼
Full delegation captured in orchestrator's context window
```

### Flow 3: Session Resume (Restart Continuity)

```
User closes terminal, reopens next day, runs `conductor`
    │
    ▼
ChatSession.__init__: read .conductor/chat_session.json → session_id found
    │
    ▼
ClaudeSDKClient(options=..., resume=session_id)
    │
    ▼
Full prior context restored by SDK (files read, tasks delegated, decisions)
    │
    ▼
User types: "How did the auth implementation go?"
Claude has full context: answers accurately referencing prior work
```

### Flow 4: Agent Escalation During Delegation

```
Delegation running: Orchestrator.run() active
    │
Sub-agent hits low-confidence action (e.g., "delete production data")
    │
    ▼
EscalationRouter: interactive mode → push HumanQuery to human_out queue
    │
    ▼
ChatSession: human_out queue watcher wakes up
    │
    ▼
Terminal prints: "\n[Agent question]: Are you sure you want to delete X?"
    │
    ▼
User types answer → human_in queue
    │
    ▼
EscalationRouter reads answer, resumes sub-agent
    │
    ▼
Delegation continues, eventually hook returns result to SDK session
```

---

## Project Structure (new files only)

```
packages/conductor-core/src/conductor/
├── acp/                              # UNCHANGED
├── dashboard/                        # UNCHANGED
├── orchestrator/                     # UNCHANGED
├── state/                            # UNCHANGED
└── cli/
    ├── __init__.py                   # MODIFY: invoke_without_command, default callback
    ├── display.py                    # UNCHANGED (reused)
    ├── input_loop.py                 # UNCHANGED
    ├── chat.py                       # NEW: ChatSession, _chat_loop, hooks, delegation
    ├── chat_persistence.py           # NEW: .conductor/chat_session.json read/write
    └── commands/
        ├── __init__.py               # UNCHANGED
        ├── run.py                    # UNCHANGED
        ├── status.py                 # UNCHANGED
        └── chat.py                   # NEW: Typer command wiring
```

### Structure Rationale

- **`cli/chat.py`** is separate from `cli/commands/chat.py` following the existing pattern (`run.py` wires the command; the actual logic is in `commands/run.py` calling functions from `cli/`). Core logic in `chat.py` is independently unit-testable.
- **`cli/chat_persistence.py`** mirrors the `SessionRegistry` pattern already in the codebase. Small and focused.
- **All new code in `cli/`** because chat is a presentation/interaction concern. Orchestration logic stays in `orchestrator/`.

---

## Architectural Patterns

### Pattern 1: ClaudeSDKClient for the Persistent Orchestrator Session

**What:** Use `ClaudeSDKClient` (not `query()`) for the orchestrator's chat session. `ClaudeSDKClient` maintains a persistent SDK process with full conversation history across `.query()` calls.

**When to use:** Any time the orchestrator needs context continuity across user messages. "It" needs to refer back to files it read, decisions it made, tasks it ran.

**Trade-offs:** More complex lifecycle (must manage `async with ClaudeSDKClient`) but necessary for chat. `query()` would close and reopen the SDK process each message, losing context despite `resume=session_id` because in-process hook registrations are lost.

```python
async with ClaudeSDKClient(options=ClaudeAgentOptions(
    cwd=str(repo_path),
    system_prompt=CHAT_SYSTEM_PROMPT,
    allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    custom_tools=[DELEGATE_TOOL_SCHEMA],
    setting_sources=["project"],
    resume=prior_session_id,  # None on first run
)) as client:
    while True:
        user_input = await _ainput("> ")
        if user_input.lower() in ("exit", "quit"):
            break
        await client.query(user_input)
        async for message in client.receive_response():
            render(message)
```

**Confidence:** HIGH — official SDK docs explicitly list "interactive applications, chat interfaces, REPLs" as the ClaudeSDKClient use case.

### Pattern 2: PostToolUse Hook for Delegation Interception

**What:** Register a `PostToolUse` hook on the `Delegate` custom tool. When the orchestrator SDK session calls `Delegate`, the hook captures the call, runs `Orchestrator.run()`, and returns a summary as the tool result.

**When to use:** Any time you need Python code to execute in response to Claude calling a specific tool. The hook runs in-process, supports `async`, and controls the tool result that Claude sees.

**Trade-offs:** Elegant decoupling — Claude decides when to delegate; Python decides how to execute it. The tool result summary is critical: Claude forms its final response based on what the hook returns.

```python
async def _delegation_hook(input_data, tool_use_id, context):
    task_desc = input_data["tool_input"]["task"]
    orchestrator = Orchestrator(state_manager=self._state, repo_path=self._repo)
    await orchestrator.run(task_desc)
    state = self._state.read_state()
    completed = [t for t in state.tasks if t.status == "completed"]
    summary = f"Completed {len(completed)} tasks: " + ", ".join(t.target_file for t in completed)
    return {"result": summary}
```

**Confidence:** HIGH — PostToolUse hooks are a first-class SDK feature documented officially.

### Pattern 3: Fresh Orchestrator Per Delegation

**What:** Construct a new `Orchestrator` instance for each delegation call, sharing only the `StateManager` and `repo_path`.

**When to use:** Always for delegation calls. Never reuse an `Orchestrator` instance across `run()` calls.

**Trade-offs:** Adds construction overhead (negligible — no I/O in `__init__`). Prevents stale `_active_clients`, `_active_tasks`, `_semaphore` state from a prior run contaminating a new one.

**Confidence:** HIGH — from direct inspection of `Orchestrator.__init__` which initializes mutable dict state.

### Pattern 4: Rich Live Rendering Over Textual for v1.1

**What:** Use Rich `Console.print()` for incremental streaming output during chat, and `_build_table()` from `display.py` for delegation progress. No Textual dependency in v1.1.

**When to use:** v1.1 baseline. Textual can be added in a later phase for full TUI widgets (scrollable history, input line, status panel).

**Trade-offs:** Rich is already a dependency; zero new packages; proven in `conductor run`. Textual would give a richer layout (scrollable message history, persistent input bar) but requires owning the event loop (incompatible with bare `asyncio.to_thread(input)` pattern).

---

## Anti-Patterns

### Anti-Pattern 1: Using `query()` for the Chat Loop

**What people do:** Use the existing `query()` function with `resume=session_id` for each user message, since the decomposer and reviewer already use `query()`.

**Why it's wrong:** `query()` creates and destroys a `ClaudeSDKClient` per call. While `resume=session_id` restores remote message history, it loses in-process hook registrations on every call. The `Delegate` hook would need to be re-registered each turn — error-prone and non-obvious.

**Do this instead:** Use `ClaudeSDKClient` as an `async with` context manager for the entire chat session lifetime.

### Anti-Pattern 2: `asyncio.run()` Inside a Running Event Loop

**What people do:** Call `asyncio.run(orchestrator.run(...))` from inside the `PostToolUse` hook handler.

**Why it's wrong:** `asyncio.run()` creates a new event loop and raises `RuntimeError: This event loop is already running` when called from inside a running loop.

**Do this instead:** `await orchestrator.run(task_desc)` directly inside the async hook callback. The hook is already running in the asyncio event loop.

### Anti-Pattern 3: Reusing an Orchestrator Instance Across Delegations

**What people do:** Pass a single `Orchestrator` instance to `ChatSession` and call `run()` on it multiple times across chat turns.

**Why it's wrong:** `Orchestrator.__init__` initializes `_active_clients`, `_active_tasks`, and `_semaphore` for one run. A second `run()` call may see stale `_active_tasks` from a previous completed run, causing state management errors.

**Do this instead:** Construct a fresh `Orchestrator(state_manager, repo_path)` inside the delegation hook. Cheap — `__init__` does no I/O.

### Anti-Pattern 4: Skipping Session Persistence

**What people do:** Start a fresh `ClaudeSDKClient` on every `conductor` invocation (no `resume`).

**Why it's wrong:** The orchestrator loses all context from prior conversation turns: files it read, tasks it ran, decisions it made. Users cannot continue a work session after closing the terminal.

**Do this instead:** Read `chat_session.json` on startup, pass `resume=session_id` to `ClaudeSDKClient`. Capture `session_id` from the `SystemMessage(subtype="init")` on first run and persist it.

### Anti-Pattern 5: Blocking Input Inside Textual

**What people do:** Use `asyncio.to_thread(input)` inside a Textual app to get user input.

**Why it's wrong:** Textual owns the event loop. Its `Input` widget handles user text through `on_input_submitted` events. Blocking `input()` in a thread fights Textual's rendering thread.

**Do this instead:** Use `asyncio.to_thread(input)` only in a pure asyncio context (no Textual). If Textual is added later, use the `Input` widget and handle `on_input_submitted`.

---

## Integration Points

### New-to-Existing Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `ChatSession` → `Orchestrator` | `await orchestrator.run(task_desc)` inside delegation hook | Fresh instance per delegation; share only `StateManager` and `repo_path` |
| `ChatSession` → `StateManager` | Shared instance passed into `ChatSession.__init__` | Chat mode reads state to show delegation progress |
| `ChatSession` → `ClaudeSDKClient` | `async with ClaudeSDKClient(options)` | One persistent session per `conductor` invocation |
| `ChatSession` → `display.py._build_table()` | Direct import, no modification | Delegation progress shown using existing table builder |
| `cli/commands/chat.py` → `cli/__init__.py` | Typer `app.command("chat")` | Minimal wiring change; existing commands unchanged |
| `chat_persistence.py` → filesystem | `.conductor/chat_session.json` (JSON) | Single reader/writer; no filelock needed |
| `ChatSession` → `EscalationRouter` | `human_out`/`human_in` asyncio.Queue passed through to Orchestrator | Agent questions surface in the chat terminal during delegation |

### External Service Boundaries

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Claude Agent SDK (chat) | `ClaudeSDKClient` persistent session | Orchestrator's chat session; lives for the `conductor` process lifetime |
| Claude Agent SDK (sub-agents) | Existing `ACPClient` wrapper (unchanged) | Sub-agents spawned by `Orchestrator.run()` during delegation |
| `.conductor/state.json` | Existing `StateManager.mutate()` + `read_state()` | Delegation writes task/agent records; chat mode reads for progress |
| `.conductor/chat_session.json` | Simple JSON via `chat_persistence.py` | Chat-mode-only; not shared with batch mode |

---

## Build Order

This ordering minimizes integration risk by building from pure data modules outward to complex interaction.

1. **`cli/chat_persistence.py`** — Pure data, no dependencies. Load/save `{session_id, started_at}`. Testable in isolation.

2. **Chat system prompt** (constant in `cli/chat.py`) — Draft the orchestrator's chat identity and delegation heuristics. Not runnable yet; needed for step 3.

3. **`ChatSession` skeleton in `cli/chat.py`** — `ClaudeSDKClient` wiring, system prompt, basic `_chat_loop()` with `asyncio.to_thread(input)` and `receive_response()` rendering. No delegation. Smoke test: direct tool use (read file, run shell command).

4. **`cli/commands/chat.py` + `cli/__init__.py` changes** — Register `chat` command, wire `invoke_without_command`. Validate that `conductor` with no args launches the loop.

5. **`Delegate` custom tool + delegation hook** — Define the in-process tool schema, write `_delegation_hook()` calling `Orchestrator.run()`. End-to-end test: type a delegation request, watch agents run.

6. **Escalation integration during delegation** — Pass `human_out`/`human_in` queues through to `Orchestrator` inside the hook. Test that agent questions surface correctly during delegation.

7. **Session persistence** — Load `chat_session.json` on startup, pass `resume=session_id`, save `session_id` from init `SystemMessage`. Test restart continuity.

8. **Smart delegation heuristics** — Tune the system prompt so the orchestrator makes accurate direct vs. delegate decisions for representative inputs. Iterative prompt engineering; no architecture change.

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| `ClaudeSDKClient` for chat loop | HIGH | Official docs explicitly list chat/REPL as its use case; `query()` comparison table confirms |
| `PostToolUse` hook for delegation | HIGH | Hooks are first-class SDK features; same pattern already used in `ACPClient` |
| `Delegate` custom in-process tool | HIGH | Custom tools documented officially; returns async-compatible hook results |
| Rich Live rendering (no Textual) | HIGH | Already proven in `conductor run`, same library, no new deps |
| Fresh `Orchestrator` per delegation | HIGH | Direct inspection of `Orchestrator.__init__` confirms mutable state that must not be reused |
| Session persistence via JSON file | HIGH | Mirrors existing `SessionRegistry` pattern exactly |
| Textual for richer TUI (future) | MEDIUM | Textual is mature but requires re-owning the event loop; not v1.1 scope |

---

## Sources

- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) — official overview, custom tools, hooks, sessions
- [How the agent loop works](https://platform.claude.com/docs/en/agent-sdk/agent-loop) — message types, PostToolUse hooks, session continuity
- [Python SDK reference: ClaudeSDKClient vs query()](https://platform.claude.com/docs/en/agent-sdk/python) — explicit comparison table; confirms ClaudeSDKClient for chat
- [Textual workers guide](https://textual.textualize.io/guide/workers/) — async worker patterns for future Textual integration
- [Textual App Basics](https://textual.textualize.io/guide/app/) — event loop ownership considerations
- Live codebase inspection: `conductor-core/src/conductor/` (2026-03-11)

---

*Architecture research for: Interactive Chat TUI — Conductor v1.1*
*Researched: 2026-03-11*
