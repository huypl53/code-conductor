# Phase 3: ACP Communication Layer - Research

**Researched:** 2026-03-10
**Domain:** Claude Agent SDK (claude-agent-sdk 0.1.48), async Python, permission prompt handling
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMM-01 | Orchestrator acts as ACP client for sub-agents — receives their questions (permission prompts, clarifications, GSD questions) | `ClaudeSDKClient` with `can_use_tool` callback intercepts all tool permission requests and `AskUserQuestion` calls from the sub-agent |
| COMM-02 | Orchestrator answers sub-agent questions using project context and shared state knowledge | `canUseTool` callback receives full tool name + input dict; orchestrator reads `ConductorState` to build context-aware answers; returns `PermissionResultAllow` or `PermissionResultDeny` |
</phase_requirements>

---

## Summary

Phase 3 must be built on the **Claude Agent SDK** (`claude-agent-sdk`), not the deprecated `claude-code-sdk`. The SDK was renamed in late 2025 and version 0.1.48 (released 2026-03-07) is the current stable release. The core abstraction for this phase is `ClaudeSDKClient`, which maintains a live session with a sub-agent and exposes two complementary capabilities: (1) streaming all messages from the sub-agent as an async iterator, and (2) intercepting every tool-use request through a `can_use_tool` callback before execution.

Permission prompts are not a separate protocol — they are tool-use approval events delivered through the same `can_use_tool` callback, and so are `AskUserQuestion` clarifying questions. The orchestrator simply inspects `tool_name` to route each event. Critically, the SDK does not have a built-in timeout for `can_use_tool`; if the orchestrator never returns from the callback the sub-agent hangs indefinitely. The safe-default-on-timeout requirement (COMM-01 success criterion 3) must be implemented in application code using `asyncio.wait_for` wrapping the callback's inner logic.

The session lifecycle follows a clean async context-manager pattern: `async with ClaudeSDKClient(options=...) as client`. All resources including the subprocess are released on exit, preventing resource leaks (success criterion 4).

**Primary recommendation:** Use `ClaudeSDKClient` (not the stateless `query()` function) because it supports interrupts, multi-turn sessions, and the `can_use_tool` callback requires streaming mode that `ClaudeSDKClient` provides natively.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude-agent-sdk` | 0.1.48 | Spawn sub-agents, stream tool calls, intercept permission prompts | Official Anthropic SDK; `claude-code-sdk` deprecated |
| `anyio` | (bundled with SDK) | Async I/O abstraction used internally by SDK | SDK dependency; use `asyncio` directly in orchestrator code |
| `pydantic` | >=2.10 | Already in project deps; parse state for context answers | Already established in Phase 2 |
| `filelock` | >=3.16 | Already in project deps; read shared state for context answers | Already established in Phase 2 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest-asyncio` | >=0.23 | Run async test functions with pytest | Required for every test in this phase (all ACP code is async) |
| `asyncio` (stdlib) | stdlib | `asyncio.wait_for`, `asyncio.timeout_context` for permission timeout | Built-in; no install needed |
| `unittest.mock` | stdlib | Mock `ClaudeSDKClient` and `query()` in unit tests | Avoids spawning real Claude processes in tests |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ClaudeSDKClient` | stateless `query()` | `query()` creates a new session per call — no interrupt support, no mid-session permission interception. Wrong tool for this phase. |
| `can_use_tool` callback | hooks (`PreToolUse`) | Hooks run at a different lifecycle point and cannot block for async I/O from the orchestrator. `can_use_tool` is the correct intercept point for question-answering. |
| `asyncio.wait_for` for timeout | `asyncio.timeout` context manager | Both work; `asyncio.wait_for` is marginally more explicit and works on Python 3.10+; `asyncio.timeout` requires 3.11+. The project targets 3.12 so either is fine — prefer `asyncio.wait_for` for familiarity. |

**Installation:**
```bash
uv add claude-agent-sdk
uv add --dev pytest-asyncio
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/conductor/acp/
├── __init__.py          # Public surface: ACPClient, SessionOptions
├── client.py            # ACPClient wrapping ClaudeSDKClient with session lifecycle
├── permission.py        # PermissionHandler: can_use_tool callback + timeout logic
└── errors.py            # ACPError, SessionError, PermissionTimeout

tests/
├── test_acp_client.py   # Session lifecycle, streaming (COMM-01, COMM-02)
└── test_acp_permission.py  # Permission routing, timeout safe-default (COMM-01)
```

### Pattern 1: Session Lifecycle with Context Manager

**What:** Wrap `ClaudeSDKClient` in a thin `ACPClient` that holds session options and exposes the same async context manager interface. All resource cleanup (subprocess termination) happens automatically on `__aexit__`.

**When to use:** Every time the orchestrator spawns a sub-agent. One `ACPClient` instance per sub-agent.

**Example:**
```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

async with ClaudeSDKClient(options=ClaudeAgentOptions(
    cwd="/path/to/repo",
    allowed_tools=["Read", "Edit", "Bash", "Glob", "Grep"],
    permission_mode="default",
    can_use_tool=permission_handler,
    setting_sources=["project"],  # Load CLAUDE.md from repo
    hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[dummy_keepalive])]},
)) as client:
    await client.query(task_prompt)
    async for message in client.receive_response():
        yield message  # Stream to orchestrator in real time
```

**Note:** The `dummy_keepalive` hook (`PreToolUse` returning `{"continue_": True}`) is required when using `can_use_tool` with streaming input. Without it, the stream closes before the permission callback fires. This is a documented SDK quirk (Python only).

### Pattern 2: Permission Intercept with Timeout Safe Default

**What:** The `can_use_tool` callback is the single entry point for all tool approvals AND `AskUserQuestion` calls. Route by `tool_name`. Wrap the orchestrator's answer logic in `asyncio.wait_for` with a configurable timeout. On timeout, return `PermissionResultDeny` (safe default = deny).

**When to use:** Always. Every `ClaudeSDKClient` session must have a `can_use_tool` callback — without one, tool requests fall through to `permission_mode` which may be too permissive or too restrictive depending on configuration.

**Example:**
```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
# Source: https://platform.claude.com/docs/en/agent-sdk/user-input
import asyncio
from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

PERMISSION_TIMEOUT_SECONDS = 30.0  # configurable

async def permission_handler(
    tool_name: str,
    input_data: dict,
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    try:
        return await asyncio.wait_for(
            _route_permission(tool_name, input_data),
            timeout=PERMISSION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return PermissionResultDeny(
            message=f"Permission timeout after {PERMISSION_TIMEOUT_SECONDS}s — denied by safe default"
        )

async def _route_permission(tool_name: str, input_data: dict) -> PermissionResultAllow | PermissionResultDeny:
    if tool_name == "AskUserQuestion":
        return await _answer_question(input_data)  # Read state, apply context
    # All other tool requests: orchestrator decides allow/deny
    return PermissionResultAllow(updated_input=input_data)  # default allow

async def _answer_question(input_data: dict) -> PermissionResultAllow:
    # Build answers from state + context, return structured response
    answers = {}
    for q in input_data.get("questions", []):
        answers[q["question"]] = "proceed"  # orchestrator's best judgment
    return PermissionResultAllow(
        updated_input={"questions": input_data["questions"], "answers": answers}
    )
```

### Pattern 3: Streaming Tool Calls in Real Time

**What:** Use `client.receive_response()` (not `receive_messages()`) to stream until a `ResultMessage` is received. Inspect each yielded `Message` for `ToolUseBlock` to observe tool calls as they happen.

**When to use:** Whenever the orchestrator needs to monitor sub-agent progress (success criterion 1).

**Example:**
```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
from claude_agent_sdk import AssistantMessage, ToolUseBlock, ResultMessage

await client.query(task_prompt)
async for message in client.receive_response():
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                # Real-time tool call observation
                await update_state_with_tool_call(block.name, block.input)
```

### Pattern 4: `ClaudeAgentOptions` for Sub-Agent Identity

**What:** Pass `cwd`, `system_prompt`, `allowed_tools`, and `setting_sources` to give the sub-agent its working context. Use `system_prompt` to inject the agent's role, name, and task target.

**When to use:** Every spawned sub-agent needs a distinct identity (ORCH-06 upstream; established here as the options model).

**Example:**
```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
from claude_agent_sdk import ClaudeAgentOptions

options = ClaudeAgentOptions(
    system_prompt=(
        "You are Ariel, a backend developer agent. "
        "Your task: implement the /api/users endpoint in packages/api/src/routes/users.py. "
        "Stay focused on this task only."
    ),
    cwd="/path/to/repo",
    allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
    permission_mode="default",
    can_use_tool=permission_handler,
    setting_sources=["project"],  # Picks up CLAUDE.md
    max_turns=50,  # Guard against runaway agents
)
```

### Anti-Patterns to Avoid

- **Using `query()` (stateless) for sub-agents:** No interrupt support, no mid-session permission handling possible. Use `ClaudeSDKClient` for all sub-agent sessions.
- **No `can_use_tool` callback:** If omitted, tool requests fall through to `permission_mode`. In `bypassPermissions` mode this is dangerous. In `default` mode it silently denies unknowns. Always provide an explicit callback.
- **Blocking in `can_use_tool` without timeout:** If the callback waits on a queue that never receives a message (e.g., waiting for human input that never arrives), the sub-agent hangs forever. Always wrap with `asyncio.wait_for`.
- **Using `break` inside `async for message in client.receive_response()`:** The SDK documentation explicitly warns this causes asyncio cleanup issues. Use state flags to stop processing early, but let iteration complete naturally.
- **Omitting the `PreToolUse` dummy hook:** In Python, `can_use_tool` requires a `PreToolUse` hook that returns `{"continue_": True}` to keep the stream open. Without it, the stream closes before the permission callback fires.
- **`bypassPermissions` mode in production:** Grants full system access. For sub-agents, use `default` mode with explicit `allowed_tools`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Subprocess management for Claude CLI | Custom subprocess + pipe reader | `ClaudeSDKClient` | SDK handles JSONL framing, stdin/stdout management, process lifecycle, error recovery |
| Message framing/parsing | Custom JSON line parser | SDK message types (`AssistantMessage`, `ToolUseBlock`, `ResultMessage`) | SDK provides typed message model with content blocks |
| Permission routing infrastructure | Custom event loop + callback registry | `can_use_tool` callback on `ClaudeAgentOptions` | Single callback handles ALL permission types uniformly |
| Session reconnect/restart logic | Custom retry wrapper | SDK context manager (`async with ClaudeSDKClient()`) | Context manager guarantees cleanup; SDK handles connection internally |
| Tool schema validation | Pydantic models for tool input | `input_data: dict` from `can_use_tool` — SDK has already parsed and validated | SDK delivers pre-parsed tool input; just access keys directly |

**Key insight:** The sub-process communication protocol (JSONL over stdin/stdout) is internal SDK infrastructure. Building it manually would require implementing the full ACP wire protocol, which the SDK already handles correctly across all edge cases.

---

## Common Pitfalls

### Pitfall 1: Missing `PreToolUse` Dummy Hook in Python

**What goes wrong:** `can_use_tool` callback is never invoked despite correct setup. The stream closes before Claude requests a tool.

**Why it happens:** Python SDK requires a `PreToolUse` hook to keep the stream alive when using `can_use_tool`. TypeScript SDK does not have this requirement.

**How to avoid:** Always register a no-op `PreToolUse` hook alongside any `can_use_tool` callback:
```python
async def _keepalive(input_data, tool_use_id, context):
    return {"continue_": True}

options = ClaudeAgentOptions(
    can_use_tool=my_handler,
    hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_keepalive])]},
)
```

**Warning signs:** `can_use_tool` logs never appear; sub-agent completes without triggering any permission events.

### Pitfall 2: Permission Callback Hanging on Unanswered Queue

**What goes wrong:** Sub-agent sends an `AskUserQuestion` or tool permission prompt; orchestrator waits for human confirmation that never arrives; entire session deadlocks.

**Why it happens:** `can_use_tool` is a coroutine — if it awaits something that never resolves (e.g., `asyncio.Queue.get()` with no producer), the sub-agent subprocess idles and eventually times out at the OS level (not gracefully).

**How to avoid:** Every `await` inside `can_use_tool` must be wrapped with `asyncio.wait_for(coro, timeout=N)`. Return `PermissionResultDeny` on timeout. This is the safe-default requirement (COMM-01 success criterion 3).

**Warning signs:** Tests pass but hang for 60+ seconds; orchestrator process consumes no CPU but holds an open subprocess.

### Pitfall 3: Using `claude-code-sdk` (Deprecated)

**What goes wrong:** Code builds and runs initially but receives deprecation warnings; future SDK features (session management, interrupt, `can_use_tool`) may diverge or be absent.

**Why it happens:** Old tutorials, examples, and Stack Overflow answers still reference `claude-code-sdk`. PyPI still hosts it.

**How to avoid:** Always install `claude-agent-sdk`. The import is `from claude_agent_sdk import ...`. If you see `from claude_code_sdk import ...` in any file, it's the old package.

**Warning signs:** `import claude_code_sdk` works; package is `claude-code-sdk` in pyproject.toml.

### Pitfall 4: `bypassPermissions` Subagent Inheritance

**What goes wrong:** Orchestrator uses `bypassPermissions` for speed; sub-agent inherits the mode and has full filesystem access without any permission prompts — including to destructive operations.

**Why it happens:** The SDK documentation notes: "When using `bypassPermissions`, all subagents inherit this mode and it cannot be overridden."

**How to avoid:** Use `permission_mode="default"` with explicit `allowed_tools` for sub-agents. Reserve `bypassPermissions` for controlled CI environments only.

**Warning signs:** No permission prompts observed even when the sub-agent attempts `rm -rf` style commands.

### Pitfall 5: `dontAsk` Mode Not Available in Python SDK

**What goes wrong:** Planner specifies `permission_mode="dontAsk"` in Python code; raises `ValueError` at runtime.

**Why it happens:** `dontAsk` is TypeScript-only as of SDK 0.1.48. Python docs explicitly note: "In Python, `dontAsk` is not yet available as a permission mode."

**How to avoid:** Implement Python equivalent manually: in `can_use_tool`, return `PermissionResultDeny` for any tool not in an allow-list. Use `disallowed_tools` to block tools before the callback fires.

**Warning signs:** `permission_mode="dontAsk"` causes a runtime exception in Python.

### Pitfall 6: `AskUserQuestion` Not Available in Sub-Agents

**What goes wrong:** Code assumes sub-agents spawned via the `Agent` tool can ask clarifying questions to the orchestrator; they cannot.

**Why it happens:** The SDK docs note: "AskUserQuestion is not currently available in subagents spawned via the Agent tool."

**How to avoid:** Sub-agents in this project are spawned via `ClaudeSDKClient` directly (not via the `Agent` tool), so `AskUserQuestion` IS available. This pitfall only applies if using `AgentDefinition` + `allowed_tools=["Agent"]` pattern.

**Warning signs:** Using `AgentDefinition` subagent feature instead of direct `ClaudeSDKClient` sessions.

---

## Code Examples

Verified patterns from official sources:

### Complete Session with Permission Handling

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
# Source: https://platform.claude.com/docs/en/agent-sdk/user-input
import asyncio
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import (
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

TIMEOUT = 30.0

async def _keepalive(input_data, tool_use_id, context):
    return {"continue_": True}

async def permission_handler(
    tool_name: str, input_data: dict, context: ToolPermissionContext
) -> PermissionResultAllow | PermissionResultDeny:
    try:
        return await asyncio.wait_for(_decide(tool_name, input_data), timeout=TIMEOUT)
    except asyncio.TimeoutError:
        return PermissionResultDeny(message="Timeout — denied by safe default")

async def _decide(tool_name: str, input_data: dict):
    if tool_name == "AskUserQuestion":
        answers = {q["question"]: "proceed" for q in input_data.get("questions", [])}
        return PermissionResultAllow(
            updated_input={"questions": input_data["questions"], "answers": answers}
        )
    return PermissionResultAllow(updated_input=input_data)

async def run_sub_agent(task_prompt: str, repo_path: str):
    options = ClaudeAgentOptions(
        cwd=repo_path,
        allowed_tools=["Read", "Edit", "Write", "Bash", "Glob", "Grep"],
        permission_mode="default",
        can_use_tool=permission_handler,
        setting_sources=["project"],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[_keepalive])]},
        max_turns=50,
    )
    async with ClaudeSDKClient(options=options) as client:
        await client.query(task_prompt)
        async for message in client.receive_response():
            yield message
```

### Interrupt a Running Sub-Agent

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
async with ClaudeSDKClient(options=options) as client:
    await client.query("Implement feature X")
    # Let it run; if orchestrator decides to cancel:
    await client.interrupt()
    # Send replacement instruction
    await client.query("Stop. Implement feature Y instead.")
    async for message in client.receive_response():
        pass  # drain
```

### Session Resume (for Phase 7 later)

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
session_id = None
async for message in query(
    prompt="Start task",
    options=ClaudeAgentOptions(allowed_tools=["Read"]),
):
    if hasattr(message, "subtype") and message.subtype == "init":
        session_id = message.session_id

# Later: resume with full context
async for message in query(
    prompt="Continue task",
    options=ClaudeAgentOptions(resume=session_id),
):
    pass
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `claude-code-sdk` | `claude-agent-sdk` | Late 2025 rename | Import paths changed; `ClaudeCodeOptions` → `ClaudeAgentOptions` |
| `ClaudeCodeOptions` | `ClaudeAgentOptions` | SDK rename | Drop-in rename; same fields |
| Manual `setting_sources` not required | `setting_sources=None` is now the default (no settings loaded) | SDK 0.1.x | Must explicitly set `setting_sources=["project"]` to load CLAUDE.md |
| `debug_stderr` parameter | `stderr: Callable[[str], None]` | SDK 0.1.x | Old parameter still works but deprecated; use callback form |
| `max_thinking_tokens` | `thinking: ThinkingConfig` | SDK 0.1.x | Old parameter deprecated |

**Deprecated/outdated:**
- `claude-code-sdk` package: deprecated, no longer maintained, use `claude-agent-sdk`
- `debug_stderr` parameter on `ClaudeAgentOptions`: deprecated, use `stderr` callback
- `max_thinking_tokens` on `ClaudeAgentOptions`: deprecated, use `thinking: ThinkingConfig`

---

## Open Questions

1. **Timeout value for permission prompts**
   - What we know: No timeout is built into the SDK. Application code must implement it.
   - What's unclear: What is the right default timeout? 30 seconds? Configurable?
   - Recommendation: Default to 30 seconds; make it a configurable constant in `conductor/acp/permission.py`. The planner should expose this as `PERMISSION_TIMEOUT_SECONDS` in a config/constants file.

2. **`can_use_tool` thread safety with state reads**
   - What we know: `can_use_tool` is an async coroutine. `StateManager.read_state()` is synchronous (blocking file I/O).
   - What's unclear: Does calling `StateManager.read_state()` inside `can_use_tool` block the asyncio event loop?
   - Recommendation: Wrap `StateManager.read_state()` calls inside `can_use_tool` with `asyncio.to_thread(manager.read_state)` to avoid blocking the event loop. Planner should include this pattern.

3. **`AskUserQuestion` message structure stability**
   - What we know: The `questions` array structure (with `question`, `header`, `options`, `multiSelect`) is documented in SDK 0.1.48.
   - What's unclear: Is this structure guaranteed stable across minor SDK versions?
   - Recommendation: Access fields via `.get()` with defaults rather than direct key access to survive schema additions.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio >=0.23 |
| Config file | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_acp_client.py tests/test_acp_permission.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMM-01 | Orchestrator receives streamed tool calls from sub-agent | unit (mock SDK) | `pytest tests/test_acp_client.py::TestComm01Streaming -x` | ❌ Wave 0 |
| COMM-01 | Permission prompt triggers `can_use_tool` callback | unit (mock SDK) | `pytest tests/test_acp_permission.py::TestComm01PermissionCallback -x` | ❌ Wave 0 |
| COMM-01 | Permission timeout resolves to deny (safe default) | unit | `pytest tests/test_acp_permission.py::TestComm01Timeout -x` | ❌ Wave 0 |
| COMM-02 | Orchestrator answers `AskUserQuestion` from state context | unit (mock state) | `pytest tests/test_acp_permission.py::TestComm02AnswerQuestion -x` | ❌ Wave 0 |
| COMM-01 | Session opens and closes without resource leaks | unit (mock SDK) | `pytest tests/test_acp_client.py::TestComm01SessionLifecycle -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_acp_client.py tests/test_acp_permission.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_acp_client.py` — covers COMM-01 streaming and session lifecycle
- [ ] `tests/test_acp_permission.py` — covers COMM-01 permission callback, timeout, and COMM-02 answer routing
- [ ] `pytest-asyncio` install: `uv add --dev pytest-asyncio` — required for async test functions
- [ ] `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` (or per-test `@pytest.mark.asyncio`) — needed for pytest-asyncio

---

## Sources

### Primary (HIGH confidence)

- `https://platform.claude.com/docs/en/agent-sdk/python` — Complete Python SDK API reference: `ClaudeSDKClient`, `ClaudeAgentOptions`, `can_use_tool`, permission types, all field definitions
- `https://platform.claude.com/docs/en/agent-sdk/overview` — SDK overview: subagents, sessions, permissions, hooks, MCP patterns
- `https://platform.claude.com/docs/en/agent-sdk/user-input` — Permission prompts, `AskUserQuestion` handling, `PermissionResultAllow`/`PermissionResultDeny`, dummy hook requirement
- `https://platform.claude.com/docs/en/agent-sdk/permissions` — Permission modes, `allowed_tools`, `disallowed_tools`, evaluation order, `dontAsk` TypeScript-only caveat
- `https://pypi.org/project/claude-agent-sdk/` — Current version (0.1.48, released 2026-03-07), Python 3.10+ requirement

### Secondary (MEDIUM confidence)

- PyPI `claude-code-sdk` page — Confirmed deprecated status with explicit migration notice to `claude-agent-sdk`

### Tertiary (LOW confidence)

- WebSearch results on `asyncio.wait_for` timeout pattern — Standard Python async pattern, verified against stdlib docs

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Verified against official PyPI and Anthropic docs; version confirmed 0.1.48
- Architecture: HIGH — Patterns taken directly from official SDK documentation with working code examples
- Pitfalls: HIGH — `PreToolUse` dummy hook requirement, `dontAsk` Python-only caveat, and `AskUserQuestion` subagent limitation all sourced from official docs

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (SDK is in active development; re-verify before Phase 4 if >30 days elapsed)
