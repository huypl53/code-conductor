# Phase 7: Agent Runtime - Research

**Researched:** 2026-03-11
**Domain:** Claude Agent SDK context inheritance, cross-agent memory, session persistence, orchestrator mode logic, dynamic agent sizing
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RUNT-01 | Sub-agents inherit repo context (`.claude/`, `CLAUDE.md`, project config) naturally | SDK `setting_sources=["project"]` + `cwd=repo_path` — already partially wired in `ACPClient`, needs `"project"` added to default sources |
| RUNT-02 | All agents share a `.memory/` folder for cross-agent knowledge persistence | File-based pattern: agents Read/Write `.memory/<agent-id>.md` via allowed tools; no SDK primitive needed |
| RUNT-03 | Full session persistence — agent identities, conversations, task progress, shared memory survive restarts | SDK `resume` field + `list_sessions()` / `get_session_messages()` for conversation history; `state.json` already persists task/agent data |
| RUNT-04 | `--auto` mode: orchestrator thinks critically on specs upfront, then runs fully autonomous | `EscalationRouter` mode="auto" already built; need upfront spec-review prompt before `orchestrator.run()` |
| RUNT-05 | Interactive mode: orchestrator can ask human questions during execution | `EscalationRouter` mode="interactive" already built; needs `human_out`/`human_in` queue wiring to CLI layer |
| RUNT-06 | Orchestrator dynamically decides how many sub-agents to spawn based on task decomposition | `TaskPlan.max_agents` field already exists; `Orchestrator` uses `min(plan.max_agents, self._max_agents)` — decomposer already drives this |
</phase_requirements>

---

## Summary

Phase 7 consolidates six runtime capabilities that transform the orchestrator from a functional prototype into a production-ready system. The good news: much of the foundation is already in place. The phase's work is primarily about wiring and surfacing existing primitives correctly, not building from scratch.

**RUNT-01 (context inheritance):** The `ACPClient` already accepts `setting_sources` and defaults to `["project"]`. The codebase currently passes `cwd=self._repo_path` to every sub-agent session. The critical fix: verify the default `_DEFAULT_SETTING_SOURCES = ["project"]` is correct and confirm that sub-agents spawned with `cwd=repo_path` automatically discover `CLAUDE.md` and `.claude/` from that directory tree. Per official SDK docs, `setting_sources=["project"]` causes the SDK to walk up from `cwd` to find `.claude/` and load `CLAUDE.md`, rules, and skills — this is the correct approach.

**RUNT-02 (shared memory):** No SDK primitive for cross-agent memory exists. The `.memory/` folder is a filesystem convention. Sub-agents already have Read/Write tools; they just need the `.memory/` path convention documented in their system prompt. The orchestrator writes the agent's memory file path into `build_system_prompt()`.

**RUNT-03 (session persistence):** The SDK provides `list_sessions(directory)`, `get_session_messages(session_id)`, and `resume` (session ID to restart from). Task/agent state already persists in `state.json` through `StateManager`. On restart, Conductor must: (a) read existing `state.json`, (b) find tasks still `IN_PROGRESS`, and (c) resume or re-spawn those agents. The `Orchestrator.run()` method currently does not handle restart — it always starts fresh.

**RUNT-04/RUNT-05 (auto + interactive modes):** The `EscalationRouter` with `mode="auto"` and `mode="interactive"` is complete. What's missing is the upfront spec-review step in `--auto` mode: before calling `orchestrator.run()`, the orchestrator should analyze the feature description and flag potential issues, but not start asking questions. This is an Orchestrator-level behavioral change — a new `pre_run_review()` phase.

**RUNT-06 (dynamic agent sizing):** Already effectively implemented. The `TaskDecomposer` returns `TaskPlan.max_agents` (bounded 1–10). The `Orchestrator` uses `min(plan.max_agents, self._max_agents)` as the semaphore cap. The only missing piece is that the planner removed the hardcoded `max_agents=5` default — the orchestrator should set `max_agents` high enough (e.g., 10) to let the decomposer drive team size.

**Primary recommendation:** This phase is primarily wiring, not building. The five sub-tasks are: (1) verify/test RUNT-01 context inheritance end-to-end, (2) add `.memory/` folder support to system prompt builder and state, (3) build `Orchestrator.resume()` using SDK session APIs, (4) add `pre_run_review()` to auto mode, (5) raise `max_agents` default to defer to decomposer.

---

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude-agent-sdk` | >=0.1.48 | SDK for spawning sub-agents with `setting_sources`, `cwd`, `resume` | Established in Phase 3; provides all session primitives needed for RUNT-01/03 |
| `filelock` | >=3.16 | Locking `.conductor/state.json` writes | Established in Phase 2; used for restart-safe state reads |
| `pydantic` | >=2.10 | Serialization of session checkpoint records | Established in Phase 2; used for all state models |

### New for Phase 7
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None required | — | — | All primitives already installed; phase work is in-code patterns, not new dependencies |

**No new dependencies are needed for Phase 7.**

### SDK Functions Used in Phase 7

| Function | Source | Purpose |
|----------|--------|---------|
| `list_sessions(directory, limit)` | `claude_agent_sdk` | Find existing sessions for a repo at restart |
| `get_session_messages(session_id)` | `claude_agent_sdk` | Inspect past session content |
| `ClaudeAgentOptions.resume` | `claude_agent_sdk` | Resume a prior conversation by session ID |
| `ClaudeAgentOptions.setting_sources` | `claude_agent_sdk` | Load `CLAUDE.md` + `.claude/` at sub-agent startup |

**Installation:** No new packages needed.
```bash
# All dependencies already in pyproject.toml
uv sync
```

---

## Architecture Patterns

### RUNT-01: Repository Context Inheritance

The SDK's `setting_sources=["project"]` combined with `cwd=repo_path` is the complete solution. The SDK walks from `cwd` upward through parent directories until it finds a `.claude/` folder and loads:
- `CLAUDE.md` from `cwd/CLAUDE.md` or `cwd/.claude/CLAUDE.md`
- `.claude/rules/*.md`
- `.claude/skills/` (on demand)
- `.claude/settings.json`

The current `ACPClient` default is `_DEFAULT_SETTING_SOURCES = ["project"]` — this is correct. No code change needed to the default. The `cwd` parameter is already passed through `self._repo_path`.

**Verification needed:** A repo with a `CLAUDE.md` at the root needs an integration test confirming that sub-agents spawned with `cwd=repo_path, setting_sources=["project"]` see the file's contents in context.

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/claude-code-features
# Current ACPClient already does this correctly:
ClaudeAgentOptions(
    cwd=repo_path,                      # repo root
    setting_sources=["project"],        # loads CLAUDE.md + .claude/
    system_prompt=system_prompt,        # agent-specific identity
)
```

**Warning:** The SDK docs state that auto memory (`~/.claude/projects/*/memory/`) is a CLI-only feature and is never loaded by the SDK. Do not rely on it for cross-session persistence. Use `.memory/` files explicitly instead (RUNT-02).

### RUNT-02: Shared Memory Folder

There is no SDK primitive for shared agent memory. The `.memory/` folder is a filesystem convention enforced through:
1. The orchestrator creates `.memory/` in the repo root at session start
2. Each agent's system prompt includes their designated memory file: `.memory/<agent-id>.md`
3. Agents write memory notes to their file using their Write tool
4. Orchestrator (and other agents) read memory files using the Read tool

**System prompt addition (extend `build_system_prompt()`):**
```python
# Add to identity model and system prompt builder
memory_section = (
    f"Your memory file: .memory/{identity.name}.md\n"
    "Write important decisions, context, and discoveries here.\n"
    "Read other agents' memory files at .memory/<agent-id>.md to share knowledge."
)
```

**Orchestrator startup (before spawning agents):**
```python
# Ensure .memory/ directory exists at session start
memory_dir = Path(self._repo_path) / ".memory"
memory_dir.mkdir(parents=True, exist_ok=True)
```

**State model addition:** The `AgentRecord` should store `memory_file: str` for observability. This is optional but useful for the CLI/dashboard.

### RUNT-03: Session Persistence and Restart Recovery

The persistence strategy has two independent layers:

**Layer 1: Task/Agent State** (already works)
`state.json` persists all task records, agent records, assignments, and status. This survives restarts now. No changes needed.

**Layer 2: Conversation State** (needs new code)
The SDK stores conversation history internally in Claude Code's session files. On restart, sessions can be resumed via `ClaudeAgentOptions.resume = session_id`.

**New class: `SessionRegistry`**
A lightweight registry stored in `state.json` (or a separate `.conductor/sessions.json`) maps `agent_id -> session_id`.

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
# list_sessions finds existing sessions for a directory
from claude_agent_sdk import list_sessions, ClaudeAgentOptions

# On restart: find sessions for this repo
sessions = list_sessions(directory=repo_path, limit=50)
# Map session_id to agent by matching cwd and creation time
```

**Orchestrator restart protocol:**
1. Read `state.json` — find tasks with `status=IN_PROGRESS` or `status=PENDING`
2. Look up `session_id` from session registry for each in-progress agent
3. For agents with valid sessions: resume via `ClaudeAgentOptions.resume = session_id`
4. For agents with no session: re-spawn with original `TaskSpec`
5. Continue normal `_run_agent_loop` from that point

```python
# Resume an existing session
async with ACPClient(
    cwd=self._repo_path,
    system_prompt=system_prompt,
    resume=session_id,         # NEW: resume existing conversation
) as client:
    # Continue from where left off
    await client.send("Continue your previous task.")
```

**ACPClient must expose `resume` parameter:**
```python
def __init__(self, *, cwd, system_prompt="", resume: str | None = None, ...):
    self._options = ClaudeAgentOptions(
        cwd=cwd,
        system_prompt=system_prompt,
        resume=resume,          # pass through to SDK
        ...
    )
```

**State model addition for session tracking:**
```python
class AgentRecord(BaseModel):
    ...
    session_id: str | None = None       # SDK session ID for resume
    memory_file: str | None = None      # .memory/<agent-id>.md path
    started_at: datetime | None = None  # for session lookup ordering
```

### RUNT-04: Auto Mode — Upfront Spec Review

Auto mode already runs fully autonomous once started (via `EscalationRouter(mode="auto")`). What's missing is the upfront spec review. This is a new `Orchestrator.pre_run_review()` method that runs before `run()`.

**Pattern:**
```python
async def pre_run_review(self, feature_description: str) -> str:
    """In --auto mode: analyze spec, surface ambiguities, commit to interpretation.

    Returns the (possibly amended) feature description or raises if spec is
    fundamentally unclear. This is the ONLY moment auto mode can surface
    issues — after this, execution is fully autonomous.
    """
    prompt = SPEC_REVIEW_PROMPT_TEMPLATE.format(
        feature_description=feature_description
    )
    # Uses query() (not ClaudeSDKClient) — single-exchange review
    result = await self._decomposer._run_review_query(prompt)
    # If review reveals critical gaps, raise SpecificationError
    # If review is OK, return confirmed/clarified description
    return result
```

**Caller (CLI/main):**
```python
async def run_auto(self, feature_description: str) -> None:
    confirmed_spec = await self.pre_run_review(feature_description)
    await self.run(confirmed_spec)  # fully autonomous from here
```

### RUNT-05: Interactive Mode — Human Question Wiring

The `EscalationRouter(mode="interactive", human_out=..., human_in=...)` is already built. The CLI layer (Phase 8) will wire the asyncio queues to actual terminal I/O. For Phase 7, the wiring should be:
1. Add `mode`, `human_out`, and `human_in` parameters to `Orchestrator.__init__()`
2. Pass an `EscalationRouter` instance to `PermissionHandler`
3. `PermissionHandler` delegates to `EscalationRouter.resolve()` for `AskUserQuestion` events

The `Orchestrator` must own the mode decision and pass it through:
```python
class Orchestrator:
    def __init__(
        self,
        state_manager: StateManager,
        repo_path: str,
        mode: str = "auto",             # NEW: "auto" | "interactive"
        human_out: asyncio.Queue | None = None,   # NEW
        human_in: asyncio.Queue | None = None,    # NEW
        max_agents: int = 10,           # CHANGED: raised from 5 to defer to decomposer
        max_revisions: int = 2,
    ):
        self._mode = mode
        self._escalation_router = EscalationRouter(
            mode=mode,
            human_out=human_out,
            human_in=human_in,
        )
```

### RUNT-06: Dynamic Agent Sizing

This is already effectively implemented. The only needed change is raising `max_agents` default from 5 to 10 (or removing the cap default to make it solely decomposer-driven).

Current flow:
1. `TaskDecomposer.decompose()` → `TaskPlan.max_agents` (1–10 per schema constraint)
2. `Orchestrator.run()` → `effective_max = min(plan.max_agents, self._max_agents)`
3. Semaphore set to `effective_max`

**No new code needed.** Just update `Orchestrator.__init__` default `max_agents=10` so the decomposer's `max_agents` is always the binding constraint (since it's capped at 10 by schema).

### Recommended Project Structure (additions to existing)

```
packages/conductor-core/src/conductor/
├── acp/
│   ├── client.py           # ADD: resume parameter to ACPClient
│   └── permission.py       # existing
├── orchestrator/
│   ├── identity.py         # MODIFY: add memory_file to AgentIdentity, build_system_prompt
│   ├── orchestrator.py     # MODIFY: mode/queues param, pre_run_review(), resume logic, max_agents default
│   ├── session_registry.py # NEW: SessionRegistry for session_id tracking
│   └── ...
├── state/
│   └── models.py           # MODIFY: add session_id, memory_file, started_at to AgentRecord
└── ...

# Runtime filesystem layout (in repo being worked on):
.conductor/
├── state.json              # existing
├── state.json.lock         # existing
└── sessions.json           # NEW: agent_id -> session_id map (optional, could go in state.json)
.memory/
├── agent-task1-abc123.md   # NEW: per-agent memory files
└── agent-task2-def456.md
```

### Anti-Patterns to Avoid

- **Do not use `~/.claude/projects/*/memory/`** for cross-agent memory: this is a CLI-only auto-memory feature. The SDK docs explicitly warn it is never loaded by SDK-spawned agents.
- **Do not store session IDs in memory only:** session IDs must be persisted to `state.json` or a sibling file before the session starts, so a restart can find them.
- **Do not start auto mode with interactive prompts:** after `pre_run_review()`, `--auto` mode must never ask the human anything. All routing goes to `EscalationRouter(mode="auto")`.
- **Do not raise `max_agents` schema cap beyond 10:** the `TaskPlan` schema constrains `max_agents` to 1–10. Raising `Orchestrator._max_agents` above 10 has no effect.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Conversation history persistence | Custom message log serialization | SDK `resume` + `list_sessions()` / `get_session_messages()` | SDK stores conversation history in Claude Code's session files; resume=session_id re-loads the full context |
| CLAUDE.md injection into sub-agent context | Manually reading and prepending CLAUDE.md content to system_prompt | `setting_sources=["project"]` + `cwd=repo_path` | SDK automatically loads CLAUDE.md at session start — more reliable, handles nested files, rules, child-dir discovery |
| Dynamic concurrency throttling | Custom queue/rate-limiter logic | `asyncio.Semaphore(effective_max)` already in Orchestrator | Already implemented correctly via semaphore pattern |
| Sub-agent file sandboxing | Custom read/write interceptors | `allowed_tools` list + system prompt file constraints | Simpler, already in place |

**Key insight:** The Claude Agent SDK's session management primitives (`resume`, `list_sessions`) are the correct abstraction for conversation persistence. Don't replicate conversation history in `state.json` — that's the wrong layer.

---

## Common Pitfalls

### Pitfall 1: Auto Memory vs. Explicit `.memory/`
**What goes wrong:** Developer assumes `setting_sources=["user"]` loads per-project memory files from `~/.claude/projects/*/memory/`. It does not — that's a CLI-only feature.
**Why it happens:** The SDK documentation warning is easy to miss.
**How to avoid:** Use explicit `.memory/<agent-id>.md` files written via the Write tool, not any auto-memory path.
**Warning signs:** System prompt says "check your memory file" but agents report no memory content.

### Pitfall 2: Session Resume Without State Reconciliation
**What goes wrong:** Orchestrator resumes a session but the task in `state.json` is already marked `COMPLETED` (from a previous partial run). The agent receives "continue your task" but has nothing to do.
**Why it happens:** State and session history get out of sync during mid-crash restarts.
**How to avoid:** Always reconcile `state.json` task status before sending the resume prompt. Only resume `IN_PROGRESS` tasks. Re-check task status after `stream_response()` completes.
**Warning signs:** Agent says "I've already completed this" repeatedly.

### Pitfall 3: `setting_sources` Isolation Mode
**What goes wrong:** Sub-agents spawned with `setting_sources=None` (the SDK default) don't pick up `CLAUDE.md` or project skills.
**Why it happens:** `setting_sources` defaults to `None` in the SDK — no settings loaded. The current `_DEFAULT_SETTING_SOURCES = ["project"]` in `ACPClient` is the fix, but it can accidentally be overridden.
**How to avoid:** Never pass `setting_sources=None` explicitly to `ACPClient`. Keep the default `["project"]`. Add a test asserting that `ClaudeAgentOptions` gets `setting_sources=["project"]`.
**Warning signs:** Sub-agent ignores CLAUDE.md coding conventions.

### Pitfall 4: session_id Not Persisted Before Session Crashes
**What goes wrong:** Orchestrator starts a session, gets a `session_id` from `get_server_info()`, then crashes before writing it to state. On restart, there's no way to find the old session.
**Why it happens:** Writing session_id to state is async and can be interrupted.
**How to avoid:** Write the session_id to `AgentRecord` immediately after `client.__aenter__()` succeeds, using the existing `mutate()` atomic pattern. Do this before sending the first task message.
**Warning signs:** After restart, sessions accumulate but can never be resumed.

### Pitfall 5: Upfront Spec Review Blocking Auto Mode
**What goes wrong:** `pre_run_review()` in auto mode asks the human for clarification. Auto mode must NEVER block on human input.
**Why it happens:** Reusing interactive mode's escalation path in pre-review.
**How to avoid:** `pre_run_review()` runs a single-exchange SDK query (no `ClaudeSDKClient`, no permission handler, no escalation router). It uses `query()` with structured output to get a review summary. The orchestrator decides unilaterally whether to proceed.
**Warning signs:** Auto mode hangs waiting for user input.

---

## Code Examples

### RUNT-01: Context Inheritance (Already Working, Verify End-to-End)

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/claude-code-features
# ACPClient already passes setting_sources=["project"] + cwd=repo_path.
# This is correct. CLAUDE.md at repo_path/CLAUDE.md will be loaded.

# What to verify in tests:
async with ACPClient(
    cwd="/path/to/repo",           # has CLAUDE.md at root
    system_prompt="You are Alice.",
    setting_sources=["project"],   # SDK loads CLAUDE.md from cwd
) as client:
    await client.send("What are the coding conventions for this project?")
    async for msg in client.stream_response():
        # Agent should reference CLAUDE.md content without being told explicitly
        pass
```

### RUNT-02: Memory File in System Prompt

```python
# Extend build_system_prompt() in identity.py:
def build_system_prompt(identity: AgentIdentity) -> str:
    memory_section = (
        f"Your memory file: .memory/{identity.name}.md\n"
        "Write decisions, discoveries, and context here using the Write tool.\n"
        "Read other agents' memory at .memory/<agent-name>.md using the Read tool."
    )
    return (
        f"You are {identity.name}, a {identity.role}.\n\n"
        f"Task ID: {identity.task_id}\n"
        f"Task: {identity.task_description}\n\n"
        f"Your assigned file:\n  {identity.target_file}\n\n"
        f"{material_section}\n\n"
        f"{memory_section}\n\n"
        "Do not modify files outside your assignment. "
        "Focus exclusively on your target file and task."
    )
```

### RUNT-03: Session Resume in ACPClient

```python
# Extend ACPClient.__init__() to accept resume parameter:
class ACPClient:
    def __init__(
        self,
        *,
        cwd: str,
        system_prompt: str = "",
        resume: str | None = None,    # NEW
        allowed_tools: list[str] | None = None,
        permission_handler: PermissionHandler | None = None,
        max_turns: int = _DEFAULT_MAX_TURNS,
        setting_sources: list[SettingSource] | None = None,
    ) -> None:
        ...
        self._options = ClaudeAgentOptions(
            cwd=cwd,
            system_prompt=system_prompt,
            resume=resume,             # NEW: SDK resumes session if set
            ...
        )
```

### RUNT-03: Session ID Retrieval and Storage

```python
# Source: https://platform.claude.com/docs/en/agent-sdk/python
# get_server_info() returns session metadata including session_id

async def _run_agent_loop(self, task_spec, sem, resume_session_id=None):
    async with sem:
        agent_id = f"agent-{task_spec.id}-{uuid.uuid4().hex[:8]}"
        ...
        async with ACPClient(
            cwd=self._repo_path,
            system_prompt=system_prompt,
            resume=resume_session_id,   # None for new sessions
        ) as client:
            # Persist session_id BEFORE sending first message
            server_info = await client._sdk_client.get_server_info()
            if server_info:
                session_id = server_info.get("session_id")
                await asyncio.to_thread(
                    self._state.mutate,
                    self._make_save_session_fn(agent_id, session_id),
                )
            ...
```

### RUNT-04: Pre-Run Spec Review (Auto Mode)

```python
SPEC_REVIEW_PROMPT_TEMPLATE = """\
You are a technical architect reviewing a feature specification before execution.
Analyze the following feature description for completeness and technical risks.

<feature_description>
{feature_description}
</feature_description>

Return a SpecReview JSON object with:
- is_clear: bool — whether the spec is clear enough to proceed
- issues: list[str] — any ambiguities or risks identified
- confirmed_description: str — the spec as you understand it (fill gaps with best judgment)
"""

async def pre_run_review(self, feature_description: str) -> str:
    """Auto mode only: analyze spec upfront, commit to interpretation."""
    # Single-exchange query — no escalation, no human interaction
    options = ClaudeAgentOptions(
        output_format={
            "type": "json_schema",
            "schema": SpecReview.model_json_schema(),
        },
        max_turns=2,
    )
    result = None
    async for msg in query(prompt=..., options=options):
        if isinstance(msg, ResultMessage):
            result = msg
            break
    review = SpecReview.model_validate(result.structured_output)
    if not review.is_clear and review.issues:
        logger.warning("Spec issues identified: %s", review.issues)
    return review.confirmed_description
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual CLAUDE.md injection into system_prompt | `setting_sources=["project"]` loads it automatically | SDK 0.1.48+ | Context inheritance requires no custom code |
| Session conversation lost on restart | `resume=session_id` restores conversation context | SDK 0.1.48+ | Sub-agent sessions are recoverable |
| SDK loaded all settings by default | SDK defaults to `setting_sources=None` (isolation mode) | Migration note in current SDK | Must explicitly set `setting_sources` — current default in `_DEFAULT_SETTING_SOURCES` is correct |

**SDK auto memory:** Never enabled for SDK-spawned agents — CLI-only feature. Use `.memory/` file convention instead.

---

## Open Questions

1. **`get_server_info()` availability in `ClaudeSDKClient`**
   - What we know: The Python SDK reference documents `get_server_info()` as a method on `ClaudeSDKClient` that returns session metadata including `session_id`
   - What's unclear: The SDK version in use (>=0.1.48) — need to verify `get_server_info()` is available in this version and returns a `session_id` key
   - Recommendation: Write a minimal test against the real SDK to confirm the session_id retrieval path before depending on it. If not available, fall back to `list_sessions(directory=repo_path)` filtered by creation timestamp.

2. **Resume semantics with a new system_prompt**
   - What we know: `ClaudeAgentOptions.resume=session_id` resumes a conversation
   - What's unclear: If the `system_prompt` on resume differs from the original, does the SDK use the original or the new one?
   - Recommendation: Pass the same system prompt on resume. If the agent identity has changed (e.g., task reassignment), spawn a fresh session instead.

3. **`.memory/` file access across agents with `allowed_tools`**
   - What we know: Agents have Read/Write in their `allowed_tools` list
   - What's unclear: Are there path restrictions that would prevent writing to `.memory/` which is outside the agent's `target_file` assignment?
   - Recommendation: The system prompt already says "do not modify files outside your assignment" — update the wording to explicitly permit writing to `.memory/<agent-name>.md` only.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio |
| Config file | `packages/conductor-core/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/ -x -q` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -v` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RUNT-01 | `ACPClient` passes `setting_sources=["project"]` and `cwd` to `ClaudeAgentOptions` | unit | `uv run pytest tests/test_acp_client.py -x -k "setting_sources"` | ✅ (extend existing) |
| RUNT-02 | `build_system_prompt()` includes `.memory/<agent-id>.md` reference | unit | `uv run pytest tests/test_identity.py -x -k "memory"` | ❌ Wave 0 |
| RUNT-02 | Orchestrator creates `.memory/` directory at session start | unit | `uv run pytest tests/test_orchestrator.py -x -k "memory_dir"` | ✅ (extend existing) |
| RUNT-03 | `ACPClient` passes `resume` to `ClaudeAgentOptions` when provided | unit | `uv run pytest tests/test_acp_client.py -x -k "resume"` | ✅ (extend existing) |
| RUNT-03 | `AgentRecord` stores `session_id` field | unit | `uv run pytest tests/test_models.py -x -k "session_id"` | ✅ (extend existing) |
| RUNT-03 | Orchestrator re-spawns `IN_PROGRESS` tasks on restart | unit | `uv run pytest tests/test_orchestrator.py -x -k "restart"` | ✅ (extend existing) |
| RUNT-04 | `pre_run_review()` returns confirmed spec description | unit | `uv run pytest tests/test_orchestrator.py -x -k "pre_run_review"` | ✅ (extend existing) |
| RUNT-05 | Orchestrator accepts `mode` + queue params; routes to EscalationRouter | unit | `uv run pytest tests/test_orchestrator.py -x -k "mode"` | ✅ (extend existing) |
| RUNT-06 | `Orchestrator.run()` uses `plan.max_agents` as effective cap when <= `max_agents` | unit | `uv run pytest tests/test_orchestrator.py -x -k "max_agents"` (exists) | ✅ (may exist) |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/ -x -q`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_identity.py` — new test file covering `build_system_prompt()` with memory section; currently identity tests may be embedded in orchestrator tests
- [ ] Extend `tests/test_models.py` — add `session_id` and `memory_file` field tests for `AgentRecord`
- [ ] Extend `tests/test_acp_client.py` — add `resume` parameter pass-through test

*(Remaining tests extend existing files — no new test files needed beyond `test_identity.py`)*

---

## Sources

### Primary (HIGH confidence)
- [platform.claude.com/docs/en/agent-sdk/claude-code-features](https://platform.claude.com/docs/en/agent-sdk/claude-code-features) — `setting_sources`, CLAUDE.md load table, SDK isolation mode, auto-memory warning
- [platform.claude.com/docs/en/agent-sdk/python](https://platform.claude.com/docs/en/agent-sdk/python) — Full `ClaudeAgentOptions` field reference including `resume`, `setting_sources`, `cwd`; `list_sessions()`, `get_session_messages()` signatures; `ClaudeSDKClient.get_server_info()`
- Project source code (`packages/conductor-core/src/conductor/`) — current ACPClient implementation, Orchestrator, EscalationRouter, StateManager, TaskDecomposer

### Secondary (MEDIUM confidence)
- STATE.md decisions log — confirmed that `setting_sources: list[SettingSource]` uses `list[SettingSource]` type (Phase 3 decision), `asyncio.wait_for` for all async decision logic (Phase 3 decision)

### Tertiary (LOW confidence)
- None — all claims verified against official SDK documentation or project source code

---

## Metadata

**Confidence breakdown:**
- RUNT-01 (context inheritance): HIGH — SDK docs confirm `setting_sources=["project"]` + `cwd` is the exact mechanism; current ACPClient already correct
- RUNT-02 (shared memory): HIGH — filesystem convention, no SDK dependency; straightforward implementation
- RUNT-03 (session persistence): MEDIUM-HIGH — `resume`, `list_sessions`, `get_server_info` documented in SDK reference; confirm `get_server_info` returns `session_id` in SDK >=0.1.48
- RUNT-04 (auto mode review): HIGH — pattern derived from existing `TaskDecomposer.decompose()` using `query()` with structured output
- RUNT-05 (interactive mode): HIGH — `EscalationRouter` is fully implemented; wiring is straightforward
- RUNT-06 (dynamic sizing): HIGH — already effectively implemented in `Orchestrator.run()`

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable SDK, 30-day estimate)
