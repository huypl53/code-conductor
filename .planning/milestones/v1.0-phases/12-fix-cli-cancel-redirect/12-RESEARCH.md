# Phase 12: Fix CLI Cancel/Redirect Signatures - Research

**Researched:** 2026-03-11
**Domain:** Python function signature mismatch — CLI dispatch layer vs. Orchestrator intervention API
**Confidence:** HIGH

## Summary

Phase 12 closes a runtime signature mismatch introduced between Phase 6 (Orchestrator `cancel_agent`) and Phase 8 (CLI `_dispatch_command`). The CLI calls `cancel_agent` in two incompatible ways:

1. `cancel agent-1` from CLI dispatches `await orchestrator.cancel_agent(agent_id)` — omitting the required `corrected_spec: TaskSpec` positional argument entirely, causing `TypeError: cancel_agent() missing 1 required positional argument: 'corrected_spec'`.
2. `redirect agent-1 "new instructions"` dispatches `await orchestrator.cancel_agent(agent_id, new_instructions=new_instructions)` — passing an unknown keyword argument instead of a `TaskSpec` object, causing `TypeError: cancel_agent() got an unexpected keyword argument 'new_instructions'`.

The root cause is that `cancel_agent` was designed around the orchestrator's internal data model (`TaskSpec`), but the CLI only has a string `agent_id` and optionally new instruction text. The fix must bridge this gap without requiring the CLI to construct a `TaskSpec`.

The cleanest fix is to change `cancel_agent`'s public signature to `(agent_id: str, new_instructions: str | None = None)` and have the method look up the existing task spec from state internally. This keeps the CLI simple, preserves the orchestrator's ability to re-spawn with original spec fields (role, target_file, etc.) updated with new instructions, and satisfies COMM-05.

**Primary recommendation:** Change `Orchestrator.cancel_agent` to accept `(agent_id: str, new_instructions: str | None = None)`. Look up the running task spec from `_active_tasks` / state, update `description` with `new_instructions` if provided, and re-spawn. Update the three existing test assertions in `test_cli.py` that already express the desired call contract (they use `cancel_agent("agent-1")` and `cancel_agent("agent-1", new_instructions="...")`, which is the target API).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python asyncio | stdlib | Async task management, cancellation | Already used throughout; no new dep |
| conductor.state.models (TaskSpec, Task) | local | Task data model used by orchestrator | Already imported in orchestrator.py |
| conductor.state.manager (StateManager) | local | State read for task lookup | Already available as `self._state` |
| pytest + pytest-asyncio | project | Test validation | Already in pyproject.toml dev deps |

No new dependencies required. This is a pure refactor within existing modules.

## Architecture Patterns

### Recommended Project Structure

No new files are required. Changes are confined to:

```
packages/conductor-core/src/conductor/
├── orchestrator/
│   └── orchestrator.py          # cancel_agent signature + body fix
└── cli/
    └── input_loop.py            # No changes needed (already uses target API)
packages/conductor-core/tests/
└── test_cli.py                  # Tests already express target API; update integration test
```

### Pattern 1: State-Aware Cancellation

**What:** `cancel_agent` reads the current task assignment from `self._state` to reconstruct spec fields (role, target_file, material_files, etc.), then overrides `description` with `new_instructions` if provided.

**When to use:** When the caller only has `agent_id` + optional new instruction text. The method owns the complexity of constructing the corrected spec.

**Example — target signature:**
```python
# orchestrator.py — target after fix
async def cancel_agent(
    self, agent_id: str, new_instructions: str | None = None
) -> None:
    """Cancel a running agent and optionally reassign with new instructions.

    COMM-05: Cancels the asyncio.Task for *agent_id* (if running), then
    spawns a new _run_agent_loop. If *new_instructions* is provided, the
    task description is replaced; all other spec fields (role, target_file,
    material_files) are preserved from the current task record.

    If *agent_id* is not in _active_tasks, cancel is a no-op; a new session
    is still spawned (idempotent).
    """
    existing_task = self._active_tasks.pop(agent_id, None)
    if existing_task is not None:
        existing_task.cancel()
        try:
            await existing_task
        except (asyncio.CancelledError, Exception):
            pass

    # Look up current task record to build corrected spec
    state = await asyncio.to_thread(self._state.read_state)
    agent_rec = next((a for a in state.agents if a.id == agent_id), None)
    task_id = agent_rec.current_task_id if agent_rec else None
    task = next((t for t in state.tasks if t.id == task_id), None)

    if task is None:
        # Agent not found in state — nothing to re-spawn
        return

    corrected_spec = TaskSpec(
        id=task.id,
        title=task.title,
        description=new_instructions if new_instructions else task.description,
        role=agent_rec.role if agent_rec else "developer",
        target_file=task.target_file or "",
        material_files=task.material_files,
        requires=task.requires,
        produces=task.produces,
    )

    sem = self._semaphore or asyncio.Semaphore(self._max_agents)
    new_asyncio_task = asyncio.create_task(
        self._run_agent_loop(corrected_spec, sem)
    )
    self._active_tasks[corrected_spec.id] = new_asyncio_task
```

### Pattern 2: Existing CLI dispatch is already correct

The CLI `input_loop.py` already calls the target API:
- `cancel`: `await orchestrator.cancel_agent(agent_id)` — maps to `cancel_agent(agent_id, new_instructions=None)`
- `redirect`: `await orchestrator.cancel_agent(agent_id, new_instructions=new_instructions)` — maps to `cancel_agent(agent_id, new_instructions="...")`

**No changes to `input_loop.py` are required.** The CLI was written against the intended API; the orchestrator was written against an internal API. The orchestrator must be fixed.

### Anti-Patterns to Avoid

- **Building TaskSpec in the CLI:** The CLI has no knowledge of agent roles, target files, or material files. Forcing the CLI to construct a `TaskSpec` would couple it to internal orchestrator data models and require reading state from the CLI layer — wrong ownership.
- **Adding a separate `redirect_agent` method:** Unnecessary duplication. `cancel_agent` with optional `new_instructions` cleanly handles both cancel (no new instructions) and redirect (with new instructions).
- **Changing `input_loop.py` to pass a full TaskSpec:** Requires the CLI to import and construct `TaskSpec`, state reads in CLI, breaking the layer boundary.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Task lookup by agent_id | Custom dict or scan loop | `next((a for a in state.agents if a.id == agent_id), None)` | Already used in `resume()` — same pattern |
| Async state read | Blocking call inside async def | `await asyncio.to_thread(self._state.read_state)` | Already used everywhere in orchestrator — avoids event loop block |

## Common Pitfalls

### Pitfall 1: cancel_agent with no active task in state

**What goes wrong:** If the agent_id is not found in `state.agents` (already cleaned up, or never started), the lookup returns `None` and trying to build a `TaskSpec` fails.

**Why it happens:** State cleanup may have already removed the agent record by the time cancel is called.

**How to avoid:** Guard with early return if `task is None`. The cancel itself (stopping the asyncio.Task) should still succeed — only the re-spawn should be skipped when no spec can be reconstructed.

**Warning signs:** `StopIteration` or `NoneType` attribute errors in logs after cancel.

### Pitfall 2: Tests only mock cancel_agent — no integration coverage

**What goes wrong:** Existing tests in `test_cli.py` use `MagicMock()` for the orchestrator. They validate the call shape but never exercise the actual `cancel_agent` body. The TypeError only appears at runtime.

**Why it happens:** Phase 8 CLI tests were written against the intended API (which is correct), but the orchestrator implementation drifted to use `TaskSpec` instead.

**How to avoid:** Add an integration-style test that calls `cancel_agent` on a real `Orchestrator` instance (with mocked state and mocked `_run_agent_loop`/`_active_tasks`). This validates the actual implementation, not just the call shape.

**Warning signs:** All tests pass but runtime raises TypeError immediately on cancel or redirect.

### Pitfall 3: asyncio.Task naming collision

**What goes wrong:** `cancel_agent` creates a new asyncio.Task stored in `self._active_tasks[corrected_spec.id]`. If `task.id` == the original task ID (which it should be), this overwrites the old entry correctly. But if `task.id` changes (it shouldn't), old tasks leak in `_active_tasks`.

**How to avoid:** Keep `corrected_spec.id = task.id` — preserve the original task ID, only override `description`.

### Pitfall 4: Missing `target_file` on Task

**What goes wrong:** `Task.target_file` defaults to `None` (from state models). `TaskSpec.target_file` is a required `str` with no default. Building a `TaskSpec` from a `Task` that has `target_file=None` raises Pydantic validation error.

**How to avoid:** Use `task.target_file or ""` when constructing the corrected spec. An empty string is valid for agents whose task description doesn't require a specific target file.

## Code Examples

### Existing call sites in `input_loop.py` (correct, no changes needed)

```python
# Source: packages/conductor-core/src/conductor/cli/input_loop.py lines 50, 68
# cancel command
await orchestrator.cancel_agent(agent_id)

# redirect command
await orchestrator.cancel_agent(agent_id, new_instructions=new_instructions)
```

### Existing tests that already express the target API

```python
# Source: packages/conductor-core/tests/test_cli.py lines 150, 178
# These already assert the correct call shape — no test changes needed for dispatch tests
mock_orch.cancel_agent.assert_awaited_once_with("agent-1")
mock_orch.cancel_agent.assert_awaited_once_with("agent-1", new_instructions="work on auth instead")
```

### Integration test pattern (to be added)

```python
# New test: validates actual cancel_agent body executes without TypeError
async def test_cancel_agent_no_new_instructions(tmp_path):
    """cancel_agent(agent_id) executes without TypeError."""
    from conductor.orchestrator.orchestrator import Orchestrator
    from conductor.state.models import AgentRecord, AgentStatus, Task, TaskStatus, ConductorState

    state = ConductorState(
        agents=[AgentRecord(id="agent-1", name="agent-1", role="developer",
                            status=AgentStatus.WORKING, current_task_id="task-1")],
        tasks=[Task(id="task-1", title="T", description="Do X",
                    status=TaskStatus.IN_PROGRESS, target_file="src/foo.py",
                    assigned_agent="agent-1")],
    )
    mock_sm = MagicMock()
    mock_sm.read_state.return_value = state

    orch = Orchestrator(state_manager=mock_sm, repo_path=str(tmp_path))
    # No active asyncio task for agent-1 — cancel should be a no-op for task cancellation
    # but should re-spawn via _run_agent_loop
    with patch.object(orch, "_run_agent_loop", new=AsyncMock(return_value=None)):
        await orch.cancel_agent("agent-1")
    # No TypeError means success
```

### State model field reference

```python
# Source: packages/conductor-core/src/conductor/orchestrator/models.py
class TaskSpec(BaseModel):
    id: str
    title: str
    description: str
    role: str
    target_file: str           # required str — use task.target_file or ""
    material_files: list[str]  # default_factory=list
    requires: list[str]        # default_factory=list
    produces: list[str]        # default_factory=list

# Source: packages/conductor-core/src/conductor/state/models.py (inferred from usage)
class Task(BaseModel):
    id: str
    title: str
    description: str
    status: TaskStatus
    target_file: str | None     # can be None — guard with `or ""`
    material_files: list[str]
    requires: list[str]
    produces: list[str]
    assigned_agent: str | None

class AgentRecord(BaseModel):
    id: str
    name: str
    role: str
    current_task_id: str | None
    status: AgentStatus
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| cancel_agent(agent_id, corrected_spec: TaskSpec) | cancel_agent(agent_id, new_instructions: str \| None) | Phase 12 | CLI can call cancel/redirect without knowing internal data models |

**Deprecated/outdated:**
- `cancel_agent(corrected_spec: TaskSpec)` second param: replace with `new_instructions: str | None = None`; spec reconstruction happens inside the method using state.

## Open Questions

1. **What if agent_id is unknown in state but IS in `_active_tasks`?**
   - What we know: `_active_tasks` stores asyncio.Task objects keyed by agent_id (UUID-based like `agent-task-id-abc123`), not the human-readable `agent-1` CLI users would type
   - What's unclear: The CLI receives agent IDs from the display table. The display table shows `AgentRecord.name` which IS the `agent_id` string used as the key
   - Recommendation: Treat this as the normal path — agent_id from CLI matches `AgentRecord.id` and `_active_tasks` keys

2. **Fire-and-forget vs. await for new task**
   - What we know: STATE.md decision log says "cancel_agent uses asyncio.create_task fire-and-forget for new session — caller does not wait for reassigned agent"
   - What's unclear: Whether to change this behavior
   - Recommendation: Preserve fire-and-forget. The CLI returns immediately after cancel/redirect prints confirmation. This matches existing behavior.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | packages/conductor-core/pyproject.toml |
| Quick run command | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_cli.py -x -q` |
| Full suite command | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLI-01 | User can chat with orchestrator via CLI terminal | unit | `pytest tests/test_cli.py -x -q` | Yes |
| CLI-03 | User can cancel/redirect agents via CLI commands | unit+integration | `pytest tests/test_cli.py -x -q` | Yes (dispatch tests pass; integration test missing) |
| COMM-05 | Orchestrator can cancel sub-agent and reassign | integration | `pytest tests/test_orchestrator.py -k cancel -x -q` | Needs new test |

### Sampling Rate
- **Per task commit:** `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_cli.py -x -q`
- **Per wave merge:** `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Integration test for `cancel_agent(agent_id)` — validates actual body, not just mock call shape (add to `tests/test_orchestrator.py` or new `tests/test_cancel_redirect.py`)
- [ ] Integration test for `cancel_agent(agent_id, new_instructions="...")` — validates redirect path

*(All existing test infrastructure is in place; only new test cases are needed, not new files or framework installs)*

## Sources

### Primary (HIGH confidence)
- Direct source code read: `packages/conductor-core/src/conductor/cli/input_loop.py` — CLI dispatch layer, lines 45-69
- Direct source code read: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — `cancel_agent` signature, lines 375-401
- Direct source code read: `packages/conductor-core/tests/test_cli.py` — existing test assertions, lines 150 and 178
- Direct source code read: `packages/conductor-core/src/conductor/orchestrator/models.py` — TaskSpec model fields
- Runtime inspection: `uv run python3 -c "inspect.signature(Orchestrator.cancel_agent)"` — confirmed `(self, agent_id: str, corrected_spec: TaskSpec) -> None`
- Runtime test run: All 11 tests in test_cli.py pass (mocked) — confirmed tests express target API but don't exercise implementation

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` Phase 06 decision: "cancel_agent uses asyncio.create_task fire-and-forget for new session" — informs re-spawn design
- `.planning/STATE.md` Phase 08 decisions — Typer/asyncio patterns for CLI are stable

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Bug identification: HIGH — confirmed by direct code inspection and signature comparison
- Fix approach: HIGH — cancel_agent signature change is the minimal invasive fix; task lookup pattern already used in `resume()` method
- Test gaps: HIGH — confirmed by running tests (all pass via mocks, no integration coverage of actual implementation)
- Side effects: MEDIUM — possible edge cases when agent_id not in state (handled by early return guard)

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable domain, no external library churn)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLI-01 | User can chat with the orchestrator via CLI terminal | CLI input_loop dispatches cancel/redirect; fixing cancel_agent signature ensures these commands execute without TypeError |
| CLI-03 | User can intervene (cancel, redirect, provide feedback) via CLI commands | Direct fix: cancel and redirect dispatch already call correct API shape; orchestrator must accept those calls |
| COMM-05 | Orchestrator can cancel a sub-agent's work and reassign with corrected instructions | cancel_agent body must be fixed to accept simple string args, look up existing spec from state, and re-spawn with new instructions |
</phase_requirements>
