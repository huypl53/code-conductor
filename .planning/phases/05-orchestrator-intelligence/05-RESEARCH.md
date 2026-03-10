# Phase 5: Orchestrator Intelligence - Research

**Researched:** 2026-03-10
**Domain:** ACP streaming message processing, LLM-based output review, structured revision feedback, multi-turn agent sessions
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ORCH-03 | Orchestrator monitors sub-agent progress in real-time via ACP streaming (tool calls, file edits) | `stream_response()` already yields `AssistantMessage` (with `ToolUseBlock`) and `SystemMessage` (with task progress subtypes) mid-session; the orchestrator currently ignores all yielded messages (`async for _ in ...`). Phase 5 replaces the `_` with typed message dispatch. |
| ORCH-04 | Orchestrator reviews sub-agent output for quality and coherence before marking work complete | After `stream_response()` exhausts (yields `ResultMessage`), orchestrator captures `ResultMessage.result` (the final text summary) + file content from `Task.target_file`, then calls a separate `query()` with a review prompt + structured output to get `ReviewVerdict`. Only a passing verdict triggers the state COMPLETED write. |
| ORCH-05 | Orchestrator can give feedback to sub-agents and request revisions | `ClaudeSDKClient.query()` sends additional user turns to an active session mid-stream. After a failing review verdict, orchestrator calls `client.query(feedback_message)` and resumes `receive_response()`. The session remains open because `ClaudeSDKClient` is a stateful multi-turn client, unlike one-shot `query()`. |
</phase_requirements>

---

## Summary

Phase 5 extends the existing `Orchestrator._spawn_agent()` method to transform the current fire-and-forget pattern into an observe-review-revise loop. Three distinct responsibilities are added: (1) real-time streaming monitoring via typed message dispatch on each item from `stream_response()`; (2) post-completion output review via a one-shot structured `query()` returning a `ReviewVerdict`; and (3) feedback injection via `ClaudeSDKClient.query()` to send revision instructions back to the still-open session.

The Claude Agent SDK already exposes all three capabilities. `AssistantMessage` objects yielded during streaming contain `ToolUseBlock` entries identifying every tool call a sub-agent makes. `TaskProgressMessage` and `TaskNotificationMessage` (subtypes of `SystemMessage`) provide summary telemetry. After the sub-agent's first `ResultMessage` is received, the session remains open if `ClaudeSDKClient` was used (not the one-shot `query()`) — `client.query(feedback)` followed by another `receive_response()` loop sends a revision request. This multi-turn capability is the exact `ClaudeSDKClient` vs `query()` distinction documented in the SDK.

The current `ACPClient.send()` + `stream_response()` wrappers already use `ClaudeSDKClient` internally. The key architectural decision for Phase 5 is **not** to replace this wrapper but to extend `_spawn_agent()` to (a) collect messages during streaming rather than discarding them, and (b) call `client.send()` again after receiving the first `ResultMessage` if the review fails.

**Primary recommendation:** Extend `_spawn_agent()` into a `_run_agent_loop()` that processes the streaming response, triggers a review, and re-enters the streaming loop on failure, up to a `max_revisions` cap. Do not implement a separate review agent process — use a lightweight one-shot `query()` call from within the orchestrator process for the review step.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude_agent_sdk` | 0.1.48 (installed) | Streaming message types (`AssistantMessage`, `ToolUseBlock`, `SystemMessage`, `TaskProgressMessage`, `TaskNotificationMessage`, `ResultMessage`), multi-turn `ClaudeSDKClient.query()`, one-shot `query()` for review | Already installed; all required types are in `types.py` and publicly exported |
| `pydantic` | >=2.10 (installed) | `ReviewVerdict` model for structured review output; `model_json_schema()` for `output_format` | Already installed; same pattern as `TaskPlan` decomposition |
| `asyncio` | stdlib | Existing semaphore pattern; `asyncio.to_thread()` for state writes | No change required |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-asyncio` | >=8.0 / >=0.23 | Test async streaming with mock generators | Already in dev deps |
| `unittest.mock` | stdlib | `AsyncMock` for `stream_response()` that yields typed messages; `MagicMock` for review `query()` | Built-in; existing test pattern from `test_orchestrator.py` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Lightweight `query()` for review | Spawn a full sub-agent Claude Code session for review | Full session is ~10x more expensive, slower startup, unnecessary tool access. One-shot `query()` with structured output is correct for a pure LLM reasoning task. |
| Review after `ResultMessage` | Review during streaming via hook | Hooks fire on tool events, not on output completeness. Review needs the final output, not incremental tool calls. Post-completion review is correct timing. |
| `client.query()` for revision | Restart a new session with revision instructions | New session loses conversation history and context. `client.query()` on the existing `ClaudeSDKClient` sends a follow-up turn in the same session, preserving all prior context. |
| Hard `max_revisions=1` limit | Unlimited revision loop | Unlimited loops risk cost explosion. A configurable cap (default 2) prevents runaway loops while still allowing one retry. |

**Installation:**
```bash
# No new dependencies required — all needed libraries are already installed
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/conductor/
├── orchestrator/
│   ├── orchestrator.py      # EXTEND: _spawn_agent() -> _run_agent_loop(); add review step
│   ├── reviewer.py          # NEW: ReviewVerdict model, review_output() function
│   ├── monitor.py           # NEW: StreamMonitor class — processes streaming messages, logs events
│   └── errors.py            # EXTEND: add ReviewError for review query failures
└── state/
    └── models.py            # EXTEND: Task gets review_status, revision_count fields (all-default)

tests/
├── test_orchestrator.py     # EXTEND: test review/revision loop, max_revisions cap
├── test_reviewer.py         # NEW: ORCH-04 — ReviewVerdict schema, review pass/fail, review error
└── test_monitor.py          # NEW: ORCH-03 — StreamMonitor processes ToolUseBlock, TaskProgress events
```

### Pattern 1: Real-Time Streaming Monitoring (ORCH-03)

**What:** Replace `async for _ in client.stream_response()` with a typed dispatch loop. Each message is passed to `StreamMonitor.process(message)` which logs tool use events, writes progress to state, and accumulates the final result text.

**When to use:** Immediately — replace the existing `pass` body in `_spawn_agent()`.

**Example:**
```python
# Source: claude_agent_sdk types.py — AssistantMessage, ToolUseBlock, ResultMessage
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage
from claude_agent_sdk.types import TaskProgressMessage, TaskNotificationMessage, ToolUseBlock

class StreamMonitor:
    """Processes streaming messages from a sub-agent session."""

    def __init__(self, task_id: str, state_manager: StateManager) -> None:
        self._task_id = task_id
        self._state = state_manager
        self._result_text: str | None = None

    def process(self, message: object) -> None:
        """Dispatch a single streamed message."""
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    self._on_tool_use(block)
        elif isinstance(message, TaskProgressMessage):
            self._on_progress(message)
        elif isinstance(message, TaskNotificationMessage):
            self._on_notification(message)
        elif isinstance(message, ResultMessage):
            self._result_text = message.result

    def _on_tool_use(self, block: ToolUseBlock) -> None:
        """Log tool call event to state."""
        # Example: record tool name in task outputs for dashboard visibility
        pass  # Phase 5: minimal logging; Phase 9/10 will use this for dashboard

    def _on_progress(self, message: TaskProgressMessage) -> None:
        """TaskProgressMessage: tool_uses count, duration_ms, last_tool_name."""
        pass

    def _on_notification(self, message: TaskNotificationMessage) -> None:
        """TaskNotificationMessage: status (completed/failed/stopped), summary."""
        pass

    @property
    def result_text(self) -> str | None:
        return self._result_text
```

### Pattern 2: Post-Completion Review (ORCH-04)

**What:** After the streaming loop exits (sub-agent sent `ResultMessage`), orchestrator reads the sub-agent's `target_file` content and calls a lightweight `query()` with a `ReviewVerdict` output schema. The verdict is either `approved` or `needs_revision` with structured feedback.

**When to use:** Once per agent task completion, before writing `TaskStatus.COMPLETED` to state.

**Example:**
```python
# Source: claude_agent_sdk query() — same pattern as TaskDecomposer
from pydantic import BaseModel, Field
from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions, ResultMessage

class ReviewVerdict(BaseModel):
    """Structured review result from orchestrator quality check."""
    approved: bool
    quality_issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""

REVIEW_PROMPT_TEMPLATE = """
You are a senior code reviewer and project orchestrator.

Sub-agent task: {task_description}
Target file: {target_file}

File content:
<file_content>
{file_content}
</file_content>

Agent's completion summary:
<agent_summary>
{agent_summary}
</agent_summary>

Review the file and determine:
1. Does the implementation address the task description?
2. Are there obvious defects (syntax errors, missing logic, wrong file structure)?
3. Is the output coherent and complete?

If approved, set approved=true and leave revision_instructions empty.
If not, set approved=false and provide clear revision_instructions the agent can act on.
"""

async def review_output(
    task_spec: "TaskSpec",
    agent_summary: str,
    repo_path: str,
) -> ReviewVerdict:
    """One-shot structured review of a sub-agent's completed work."""
    target_path = Path(repo_path) / task_spec.target_file
    try:
        file_content = target_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ReviewVerdict(
            approved=False,
            quality_issues=["Target file was not created"],
            revision_instructions=f"Create the file at {task_spec.target_file}",
        )

    schema = ReviewVerdict.model_json_schema()
    async for message in sdk_query(
        prompt=REVIEW_PROMPT_TEMPLATE.format(
            task_description=task_spec.description,
            target_file=task_spec.target_file,
            file_content=file_content[:8000],  # cap to avoid context overflow
            agent_summary=agent_summary or "(no summary provided)",
        ),
        options=ClaudeAgentOptions(
            output_format={"type": "json_schema", "schema": schema},
            max_turns=2,
        ),
    ):
        if isinstance(message, ResultMessage):
            if message.structured_output:
                return ReviewVerdict.model_validate(message.structured_output)
    raise ReviewError("Review query returned no structured output")
```

### Pattern 3: Feedback Injection for Revision (ORCH-05)

**What:** When review returns `approved=False`, orchestrator calls `client.send(revision_instructions)` on the still-open `ClaudeSDKClient` session and re-enters `stream_response()`. The session retains full conversation context. After the revision completes, orchestrator re-runs the review step. This loop continues up to `max_revisions`.

**Key SDK fact:** `ClaudeSDKClient.query()` sends a new user message to an existing session — the session stays open after `receive_response()` exhausts (after the first `ResultMessage`). This is the documented difference between `ClaudeSDKClient` (multi-turn) and `query()` (one-shot). The current `ACPClient.send()` already wraps `ClaudeSDKClient.query()`.

**When to use:** Only when `ReviewVerdict.approved == False` and `revision_count < max_revisions`.

**Example:**
```python
# Source: claude_agent_sdk client.py — ClaudeSDKClient.query() for multi-turn
async def _run_agent_loop(
    self,
    task_spec: TaskSpec,
    sem: asyncio.Semaphore,
    max_revisions: int = 2,
) -> None:
    """Spawn agent, monitor streaming, review output, revise if needed."""
    async with sem:
        agent_id = f"agent-{task_spec.id}-{uuid.uuid4().hex[:8]}"
        identity = AgentIdentity(...)
        system_prompt = build_system_prompt(identity)

        await asyncio.to_thread(
            self._state.mutate, self._make_add_agent_fn(agent_id, task_spec)
        )

        async with ACPClient(
            cwd=self._repo_path,
            system_prompt=system_prompt,
        ) as client:
            await client.send(f"Task {task_spec.id}: {task_spec.description}")

            for revision_num in range(max_revisions + 1):
                monitor = StreamMonitor(task_spec.id, self._state)

                async for message in client.stream_response():
                    monitor.process(message)

                # Review completed output
                verdict = await review_output(
                    task_spec,
                    agent_summary=monitor.result_text or "",
                    repo_path=self._repo_path,
                )

                if verdict.approved:
                    break

                if revision_num < max_revisions:
                    # Send revision instructions back to the same session
                    await client.send(
                        f"Revision needed:\n{verdict.revision_instructions}\n\n"
                        "Please revise your implementation and ensure the task is complete."
                    )
                # If we've exhausted revisions, break and mark as completed
                # (best-effort; task completion is still recorded)

        await asyncio.to_thread(
            self._state.mutate, self._make_complete_task_fn(task_spec.id)
        )
```

### Pattern 4: State Model Extension (Task.review_status)

**What:** Extend `Task` with review-tracking fields. All fields must have all-default values to preserve backward compatibility with existing serialized `state.json` files.

**Example:**
```python
# Extend Task in conductor/state/models.py
class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"

class Task(BaseModel):
    ...existing fields...
    # New in Phase 5 — all-default for backward compat:
    review_status: ReviewStatus = ReviewStatus.PENDING
    revision_count: int = 0
```

### Anti-Patterns to Avoid

- **Spawning a full Claude Code sub-agent for review:** Review is a pure reasoning task requiring no tool access. Using `query()` (one-shot, no Claude Code CLI overhead) is ~10x cheaper and faster than a full agent session.
- **Closing the session before revision:** Once `ClaudeSDKClient.__aexit__` is called, the session is closed and cannot receive new messages. The revision `client.send()` MUST happen inside the same `async with ACPClient(...) as client:` block.
- **Ignoring `ResultMessage` before restarting the stream:** After calling `client.send(revision_instructions)`, you must call `client.stream_response()` again. Attempting to re-iterate an already-exhausted `stream_response()` will return immediately without new messages — always call `stream_response()` fresh after each `send()`.
- **Blocking event loop on file read for review:** `target_path.read_text()` is synchronous file I/O. Inside the async orchestrator, wrap with `await asyncio.to_thread(target_path.read_text, encoding="utf-8")`.
- **Accumulating all streamed messages in memory:** With 50-turn agents, an `AssistantMessage` list can grow large. `StreamMonitor` should process-and-discard, keeping only state change events and the final `result_text`.
- **Treating `TaskNotificationMessage` as session completion:** `TaskNotificationMessage` signals a sub-task (Claude Code `Task` tool invocation) completing, not the entire agent session completing. The session ends when `ResultMessage` is yielded.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Streaming message type detection | String subtype matching or regex on raw JSON | `isinstance(message, AssistantMessage)` / `isinstance(block, ToolUseBlock)` | SDK provides typed dataclasses; Python `isinstance()` is O(1) and correct |
| Review LLM call | Custom HTTP call to Anthropic API | `query()` with `output_format` + `ReviewVerdict.model_json_schema()` | Same pattern as `TaskDecomposer`; SDK handles retries, auth, structured output validation |
| Revision message protocol | Custom JSON message format piped to sub-agent | `client.send(text)` on the open `ClaudeSDKClient` | Already implemented in `ACPClient.send()`; this sends a standard user message to the existing Claude Code session |
| Output quality heuristics | Regex checks for file existence, line counts | LLM review via `query()` | Code quality is inherently semantic; heuristics produce false positives/negatives; LLM review is appropriate here |

**Key insight:** The SDK already provides both the streaming message types and the multi-turn messaging needed for all three requirements. The orchestrator only needs to (a) not discard streamed messages and (b) call `client.send()` a second time before closing the session.

---

## Common Pitfalls

### Pitfall 1: Closing ACPClient Before Revision Send

**What goes wrong:** Review fails, orchestrator exits the `async with ACPClient(...) as client:` block, then tries to send revision feedback. `SessionError("Session is closed")` is raised.

**Why it happens:** `ACPClient.__aexit__` sets `_closed = True` and calls `ClaudeSDKClient.__aexit__`. Any subsequent `send()` checks `self._closed` and raises immediately.

**How to avoid:** The entire observe-review-revise loop (including all revision iterations) must be inside the same `async with ACPClient(...) as client:` block. Only call `await asyncio.to_thread(state.mutate, complete_fn)` after exiting the `async with` block.

**Warning signs:** `SessionError: Session is closed` raised during revision iteration.

### Pitfall 2: Re-Iterating an Exhausted stream_response()

**What goes wrong:** After the first `receive_response()` exhausts on `ResultMessage`, calling `stream_response()` again without a new `client.send()` returns immediately (no new messages). The orchestrator thinks the agent completed immediately.

**Why it happens:** `receive_response()` terminates after `ResultMessage`. The SDK does not buffer pending messages — a new user turn is required to get new responses.

**How to avoid:** Always call `client.send(revision_instructions)` before re-entering the `stream_response()` loop. In the `_run_agent_loop()` loop body: `send()` at the start of each iteration (except the first) then `stream_response()`.

**Warning signs:** Second `stream_response()` iteration completes instantly; `monitor.result_text` is `None` after revision loop.

### Pitfall 3: Blocking Event Loop on File Read During Review

**What goes wrong:** `Path.read_text()` is called directly inside the async `_run_agent_loop()`. With multiple agents completing simultaneously, several threads block the event loop trying to read files, causing `asyncio.to_thread()` queue backpressure and permission timeout cascades.

**Why it happens:** File I/O is synchronous. This is the same class of problem documented for `StateManager.mutate()` in Phase 2/3.

**How to avoid:** `file_content = await asyncio.to_thread(target_path.read_text, encoding="utf-8")` inside async code.

**Warning signs:** Permission callbacks timing out during high-parallelism phases.

### Pitfall 4: Review Prompt Context Overflow

**What goes wrong:** Large files (>100KB) are passed verbatim to the review `query()`, exceeding context limits. The review call fails or produces hallucinated results based on truncated content.

**Why it happens:** Review prompt includes full file content. Large codebases routinely produce files that exceed LLM context windows.

**How to avoid:** Cap file content at ~8000 characters (approximately 2000 tokens). If the file is larger, provide the first 4000 chars + last 4000 chars with a truncation notice in the middle: `[... {n} characters truncated ...]`. This preserves module-level declarations and the end-of-file implementations, which are the most review-relevant sections.

**Warning signs:** Review `query()` raising API errors on context length; `ReviewVerdict` citing code that is not in the file.

### Pitfall 5: Infinite Cost via Revision Loop Without Cap

**What goes wrong:** Review consistently fails. Orchestrator sends revision after revision. Token cost grows linearly; model may oscillate between implementations without converging.

**Why it happens:** No `max_revisions` guard. LLM review may flag quality issues that are subjective or require information the sub-agent doesn't have.

**How to avoid:** `max_revisions: int = 2` (configurable). After exhausting revisions, log a warning, mark the task with `review_status=NEEDS_REVISION` but still set `task.status=COMPLETED` (best-effort). Do not block the dependency graph on a permanently-failing review — that would halt all downstream tasks.

**Warning signs:** Agent session turn count approaching `max_turns` (default 50); token costs spiking per task.

### Pitfall 6: TaskNotificationMessage Confused with Session Completion

**What goes wrong:** Orchestrator receives `TaskNotificationMessage` and assumes the sub-agent session is complete. It exits the streaming loop and proceeds to review. But the sub-agent's top-level session has not yet yielded `ResultMessage` — more messages will follow.

**Why it happens:** Claude Code internally uses a `Task` tool for sub-tasks within a session. `TaskNotificationMessage` signals a sub-task (not the main session) completing. `ResultMessage` is the definitive session end marker.

**How to avoid:** Only use `isinstance(message, ResultMessage)` as the session completion signal. `receive_response()` already does this correctly — let the SDK handle the streaming termination, do not implement custom `ResultMessage` detection outside the iterator.

**Warning signs:** Review running before the sub-agent finishes writing its target file.

---

## Code Examples

Verified patterns from official sources:

### Streaming Message Type Dispatch

```python
# Source: claude_agent_sdk types.py — AssistantMessage, ToolUseBlock, ResultMessage
from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage
from claude_agent_sdk.types import TaskProgressMessage, TaskNotificationMessage, ToolUseBlock

async for message in client.stream_response():
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                print(f"[{task_id}] tool: {block.name}({block.input})")
    elif isinstance(message, TaskProgressMessage):
        print(f"[{task_id}] progress: {message.usage['tool_uses']} tool calls")
    elif isinstance(message, TaskNotificationMessage):
        print(f"[{task_id}] sub-task: {message.status} — {message.summary}")
    elif isinstance(message, ResultMessage):
        result_text = message.result
        # receive_response() will terminate after this
```

### ReviewVerdict Structured Output

```python
# Source: same output_format pattern as TaskDecomposer (Phase 4)
from pydantic import BaseModel, Field
from claude_agent_sdk import query as sdk_query, ClaudeAgentOptions, ResultMessage

class ReviewVerdict(BaseModel):
    approved: bool
    quality_issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""

async def review_output(task_spec, agent_summary: str, repo_path: str) -> ReviewVerdict:
    schema = ReviewVerdict.model_json_schema()
    async for message in sdk_query(
        prompt=REVIEW_PROMPT_TEMPLATE.format(...),
        options=ClaudeAgentOptions(
            output_format={"type": "json_schema", "schema": schema},
            max_turns=2,
        ),
    ):
        if isinstance(message, ResultMessage) and message.structured_output:
            return ReviewVerdict.model_validate(message.structured_output)
    raise ReviewError("No structured output from review query")
```

### Multi-Turn Revision Send

```python
# Source: claude_agent_sdk client.py — ClaudeSDKClient.query() is multi-turn
# ACPClient.send() wraps ClaudeSDKClient.query() — already implemented in Phase 3
async with ACPClient(cwd=repo_path, system_prompt=system_prompt) as client:
    await client.send(initial_task_prompt)

    for i in range(max_revisions + 1):
        monitor = StreamMonitor(task_id, state_manager)
        async for message in client.stream_response():
            monitor.process(message)

        verdict = await review_output(task_spec, monitor.result_text or "", repo_path)
        if verdict.approved or i == max_revisions:
            break

        await client.send(
            f"Revision {i + 1} requested:\n{verdict.revision_instructions}"
        )
    # client closes here — session ends
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fire-and-forget agent spawning (Phase 4) | Observe-review-revise loop (Phase 5) | This phase | Tasks only marked COMPLETED after orchestrator review passes |
| `async for _ in stream_response(): pass` | `StreamMonitor.process(message)` dispatches typed events | This phase | Tool calls, progress, and notifications visible to orchestrator in real time |
| `query()` one-shot for all agent interaction | `ClaudeSDKClient` multi-turn for sub-agents, `query()` one-shot for review | This phase | Sub-agent sessions stay open for revision; review is lightweight one-shot |
| `ResultMessage.result` ignored | `ResultMessage.result` captured as `agent_summary` for review prompt | This phase | Review has agent's own summary as additional signal |

**Deprecated/outdated:**
- `async for _ in client.stream_response(): pass` — this pattern from Phase 4 is replaced entirely in Phase 5. The `_` discard is explicitly noted as "Phase 5 will process" in Phase 4 code comments.

---

## Open Questions

1. **Review prompt quality — false positive rate**
   - What we know: LLM review using a structured prompt + `output_format` will produce `ReviewVerdict.approved=True/False`. The prompt quality determines false positive (rejecting good work) and false negative (approving bad work) rates.
   - What's unclear: Specific prompt patterns that minimize false positives while catching genuine failures (missing file, wrong signature, syntax error).
   - Recommendation: Start with a conservative review prompt focused on objective checks (file exists, task description addressed, no obvious syntax errors). Avoid subjective style checks — those cause false positives. Refine in Phase 7+ based on empirical results.

2. **`max_revisions` default value**
   - What we know: 0 revisions = no retry (task marked complete on first attempt); 1 revision = one retry; 2 revisions = two retries. Token cost scales linearly with revision count.
   - What's unclear: What default balances quality gate effectiveness vs. cost?
   - Recommendation: `max_revisions=2` as default. One retry handles transient LLM oversights; the second handles situations where the first revision misunderstood feedback. Beyond 2, the sub-agent is likely missing required context that revision alone cannot provide.

3. **Review of tasks that produce no file (pure refactoring tasks)**
   - What we know: `TaskSpec.target_file` is required and must be non-empty. A task that modifies many files but "primarily" targets one file will have one `target_file`.
   - What's unclear: How to review tasks where the meaningful output is spread across multiple files (e.g., test suites).
   - Recommendation: Review the `target_file` as primary signal. Add `produces` list to the review prompt context — if `produces` lists exported interfaces, verify they appear in the file. Do not try to review every `material_files` that the agent may have modified.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio >=0.23 |
| Config file | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` (asyncio_mode = "auto" already configured) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_monitor.py tests/test_reviewer.py tests/test_orchestrator.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORCH-03 | `StreamMonitor.process()` dispatches `AssistantMessage` with `ToolUseBlock` | unit (mock messages) | `pytest tests/test_monitor.py::TestOrch03ToolUse -x` | ❌ Wave 0 |
| ORCH-03 | `StreamMonitor.process()` handles `TaskProgressMessage` without error | unit (mock messages) | `pytest tests/test_monitor.py::TestOrch03Progress -x` | ❌ Wave 0 |
| ORCH-03 | `StreamMonitor.process()` captures `ResultMessage.result` as `result_text` | unit (mock messages) | `pytest tests/test_monitor.py::TestOrch03ResultCapture -x` | ❌ Wave 0 |
| ORCH-04 | `review_output()` returns `ReviewVerdict(approved=True)` on passing output | unit (mock `query()`) | `pytest tests/test_reviewer.py::TestOrch04Approved -x` | ❌ Wave 0 |
| ORCH-04 | `review_output()` returns `ReviewVerdict(approved=False)` with `revision_instructions` when file missing | unit (tmp file not created) | `pytest tests/test_reviewer.py::TestOrch04FileMissing -x` | ❌ Wave 0 |
| ORCH-04 | `review_output()` raises `ReviewError` when `query()` returns no structured output | unit (mock `query()` with no output) | `pytest tests/test_reviewer.py::TestOrch04ReviewError -x` | ❌ Wave 0 |
| ORCH-04 | Orchestrator does NOT write `TaskStatus.COMPLETED` until review passes | unit (mock `review_output`) | `pytest tests/test_orchestrator.py::TestOrch04CompleteGate -x` | ❌ Wave 0 |
| ORCH-05 | `client.send(feedback)` called when review returns `approved=False` | unit (mock `ACPClient`, mock `review_output`) | `pytest tests/test_orchestrator.py::TestOrch05RevisionSend -x` | ❌ Wave 0 |
| ORCH-05 | Revision loop terminates at `max_revisions` and marks task complete | unit (mock always-failing review) | `pytest tests/test_orchestrator.py::TestOrch05MaxRevisions -x` | ❌ Wave 0 |
| ORCH-05 | Sub-agent session remains open (not closed) between review and revision send | unit (mock ACPClient) | `pytest tests/test_orchestrator.py::TestOrch05SessionOpenForRevision -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_monitor.py tests/test_reviewer.py tests/test_orchestrator.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_monitor.py` — covers ORCH-03: StreamMonitor message dispatch
- [ ] `tests/test_reviewer.py` — covers ORCH-04: ReviewVerdict schema, review pass/fail, file-missing handling
- [ ] `src/conductor/orchestrator/monitor.py` — `StreamMonitor` class
- [ ] `src/conductor/orchestrator/reviewer.py` — `ReviewVerdict` model, `review_output()`, `REVIEW_PROMPT_TEMPLATE`
- [ ] Extend `src/conductor/orchestrator/errors.py` — add `ReviewError`
- [ ] Extend `src/conductor/orchestrator/orchestrator.py` — replace `_spawn_agent()` with `_run_agent_loop()`
- [ ] Extend `src/conductor/state/models.py` — add `ReviewStatus` enum, `review_status`/`revision_count` to `Task`

*(Existing `tests/test_orchestrator.py` will be extended with new test classes for ORCH-04 and ORCH-05 scenarios.)*

---

## Sources

### Primary (HIGH confidence)

- `/home/huypham/code/digest/claude-auto/.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py` — Verified: `AssistantMessage`, `ToolUseBlock`, `TaskProgressMessage`, `TaskNotificationMessage`, `ResultMessage`, `SystemMessage` types; `ClaudeAgentOptions.output_format` field; hook type definitions
- `/home/huypham/code/digest/claude-auto/.venv/lib/python3.13/site-packages/claude_agent_sdk/client.py` — Verified: `ClaudeSDKClient.query()` sends user turn to existing session; `receive_response()` terminates after `ResultMessage`; `__aexit__` disconnects session
- Phase 4 research `.planning/phases/04-orchestrator-core/04-RESEARCH.md` — Structured output pattern (`output_format` + `model_json_schema()`) verified and used directly for `ReviewVerdict`
- Phase 4 code `src/conductor/orchestrator/orchestrator.py` — Confirmed: `async for _ in client.stream_response(): pass` is the exact line Phase 5 replaces; session uses `ACPClient` which wraps `ClaudeSDKClient`; `ACPClient.send()` wraps `ClaudeSDKClient.query()`
- Phase 3 code `src/conductor/acp/client.py` — Confirmed: `ACPClient.send()` calls `self._sdk_client.query(prompt)`; `stream_response()` calls `self._sdk_client.receive_response()`; `_closed` flag guards re-use after `__aexit__`

### Secondary (MEDIUM confidence)

- Anthropic multi-agent patterns documentation (observed in Phase 3/4 research) — orchestrator review loop matches "supervisor-critic" pattern in agent system design; review via `query()` (not full agent) is the documented lightweight approach

### Tertiary (LOW confidence)

- None — all key findings verified against installed SDK source code

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all types and APIs verified directly against installed `claude_agent_sdk` source
- Architecture: HIGH — `stream_response()` message types verified; `ClaudeSDKClient.query()` multi-turn capability verified in client.py; `ACPClient.send()` wraps it correctly
- Pitfalls: HIGH — "session closed before revision" derived from `ACPClient._closed` flag in client.py; "exhausted stream_response" derived from `receive_response()` termination logic in client.py

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (SDK 0.1.48 stable; re-verify `receive_response()` termination semantics if SDK minor version changes)
