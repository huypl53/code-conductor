# Phase 15: Fix Dashboard Server Cancel Type Mismatch - Research

**Researched:** 2026-03-11
**Domain:** Python type contract — dashboard server.py intervention dispatch vs. Orchestrator.cancel_agent API
**Confidence:** HIGH

## Summary

Phase 12 fixed `Orchestrator.cancel_agent` to accept `(agent_id: str, new_instructions: str | None = None)`, eliminating the requirement that callers construct a `TaskSpec`. However, `packages/conductor-core/src/conductor/dashboard/server.py` was not updated in Phase 12. The `handle_intervention` function in `server.py` still calls `cancel_agent` with a manually constructed `TaskSpec` object as the second argument — the pre-Phase-12 calling convention.

**The cancel branch** (lines 83-95 in `server.py`):
```python
await orchestrator.cancel_agent(
    agent_id,
    TaskSpec(id=agent_id, title="Cancelled from dashboard", description="", role="", target_file=""),
)
```

**The redirect branch** (lines 99-112 in `server.py`):
```python
await orchestrator.cancel_agent(
    agent_id,
    TaskSpec(id=agent_id, title="Redirected from dashboard", description=message, role="", target_file=""),
)
```

Both calls pass a `TaskSpec` object to the `new_instructions: str | None` parameter. The orchestrator receives a truthy non-string object and treats it as `new_instructions`, then tries to use `new_instructions if new_instructions else task.description` — selecting the `TaskSpec` object as the description for the corrected spec. This builds a `TaskSpec(description=<TaskSpec object>)` which fails Pydantic validation with a type error.

Additionally, the existing test `test_ws_redirect_action_calls_cancel_agent_with_new_spec` in `tests/dashboard/test_server_interventions.py` was written against the old (broken) server.py behavior. It asserts `call_args[0][1].description` contains the redirect message — this test validates the wrong contract and must be updated to validate the correct `new_instructions` string API.

**Primary recommendation:** Fix `handle_intervention` in `server.py` to call `cancel_agent(agent_id)` for cancel and `cancel_agent(agent_id, new_instructions=message)` for redirect. Remove all `TaskSpec` imports from `server.py`. Update the masking test to assert `new_instructions=message` keyword arg instead of a TaskSpec positional arg.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib | stdlib | No new imports needed | Fix removes imports (TaskSpec), adds none |
| conductor.orchestrator.orchestrator (Orchestrator) | local | Target of fix | Already imported via TYPE_CHECKING guard |
| pytest + pytest-asyncio | 9.0.2 + 1.3.0 | Test validation | Already in pyproject.toml dev deps |
| starlette.testclient (TestClient) | bundled with FastAPI | Sync WebSocket test client | Already used in all intervention tests |

No new dependencies required. This is a pure bug fix and test correction within existing modules.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct string args to cancel_agent | Keep TaskSpec but accept str too | Keeping TaskSpec in server.py would re-couple server to orchestrator internals. The Phase 12 fix was specifically designed to remove this coupling. |

## Architecture Patterns

### Recommended Project Structure

No new files are required. Changes are confined to:

```
packages/conductor-core/src/conductor/
└── dashboard/
    └── server.py              # Fix handle_intervention cancel + redirect branches
packages/conductor-core/tests/
└── dashboard/
    └── test_server_interventions.py  # Fix test 3 (masking wrong contract)
```

### Pattern 1: Pass-Through Dispatch (Correct)

**What:** The dashboard server is a thin dispatch layer. It extracts the relevant string fields from the WebSocket JSON payload and passes them directly to the orchestrator methods. It does NOT construct domain model objects.

**When to use:** Always for intervention dispatch from server.py. The orchestrator owns the complexity of reconstructing specs from state.

**Target code for cancel branch:**
```python
# Source: server.py handle_intervention — target after fix
if action == "cancel":
    await orchestrator.cancel_agent(agent_id)
```

**Target code for redirect branch:**
```python
# Source: server.py handle_intervention — target after fix
elif action == "redirect":
    message = command.get("message", "")
    await orchestrator.cancel_agent(agent_id, new_instructions=message)
```

**What to remove:** Both `from conductor.orchestrator.models import TaskSpec` import lines inside the `if action == "cancel":` and `elif action == "redirect":` branches.

### Pattern 2: Keyword-Arg Test Assertions (Correct)

**What:** When testing that `cancel_agent` is called with optional keyword args, assert using `assert_awaited_once_with` or inspect `call_args.kwargs`.

**Target test 3 assertion:**
```python
# Replaces the old TaskSpec positional arg check
mock_orch.cancel_agent.assert_awaited_once_with("a1", new_instructions="new instructions here")
```

### Anti-Patterns to Avoid

- **Constructing TaskSpec in server.py:** The server layer has no knowledge of agent roles, target files, or existing task specs. Constructing a minimal/empty TaskSpec here creates a spec with empty `role=""` and `target_file=""`, overwriting the agent's real role when the orchestrator re-spawns them.
- **Leaving the import inside the if-branch:** Even though Python allows inline imports, the `from conductor.orchestrator.models import TaskSpec` lines should be removed entirely — they indicate the wrong abstraction boundary.
- **Only fixing server.py but not the test:** Leaving `test_ws_redirect_action_calls_cancel_agent_with_new_spec` in its current state would assert `call_args[0][1].description` (expecting a TaskSpec positional arg), which would FAIL after the server.py fix. The test must be updated alongside.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TaskSpec reconstruction in server.py | Building a partial TaskSpec with empty fields | `cancel_agent(agent_id, new_instructions=str)` | Phase 12 decision: orchestrator owns spec reconstruction from state; callers only supply agent_id + string |
| New test infrastructure | New test file or framework | Update existing `test_server_interventions.py` test 3 | Test infrastructure already exists; only the assertion shape needs updating |

## Common Pitfalls

### Pitfall 1: TaskSpec used as new_instructions without immediate TypeError

**What goes wrong:** `cancel_agent(agent_id, TaskSpec(...))` does NOT raise TypeError at the call site because `new_instructions: str | None = None` is typed but Python does not enforce types at runtime. The crash happens later when `TaskSpec(description=new_instructions_which_is_a_TaskSpec)` triggers Pydantic validation inside `cancel_agent`.

**Why it happens:** The wrong type passes the parameter assignment silently. The error surfaces only when the orchestrator tries to build `corrected_spec` and passes a `TaskSpec` object where `description: str` is required.

**How to avoid:** Fix the call site (server.py), not just the type annotation. Runtime type errors in Python always require fixing the actual value passed, not just the annotation.

**Warning signs:** No TypeError at the `await orchestrator.cancel_agent(...)` call, but a Pydantic `ValidationError` appears in the `logger.exception` handler inside `handle_intervention`'s outer try/except block — errors are silently swallowed.

### Pitfall 2: Test 3 passes with either wrong or right server.py code

**What goes wrong:** After fixing server.py, test 3 would fail because it currently asserts `call_args[0][1].description` — a positional TaskSpec arg. The fix changes the call to `cancel_agent(agent_id, new_instructions=message)`, where `message` is a keyword arg. The test assertion must be updated.

**Why it happens:** The test was written to validate the old broken behavior. It passes all 298 current tests with the broken server.py because mock calls accept any args.

**How to avoid:** Update test 3 to `mock_orch.cancel_agent.assert_awaited_once_with("a1", new_instructions="new instructions here")`.

**Warning signs:** If test 3 still passes after the server.py fix but you didn't update it — check whether it's testing the wrong thing.

### Pitfall 3: Leaving empty TaskSpec role="" silently corrupts agent re-spawn

**What goes wrong:** If the TaskSpec approach is kept but "fixed" to build a valid TaskSpec (filling required fields), the re-spawned agent would have `role=""` — an empty string. The orchestrator uses `task_spec.role` to build the agent identity and system prompt. An empty role produces a degraded system prompt.

**Why it happens:** The server has no access to the agent's actual role — only the orchestrator knows it from state.

**How to avoid:** Pass only `agent_id` and `new_instructions` (or nothing). Let the orchestrator look up the real role from state, as Phase 12 designed.

### Pitfall 4: Cancel test 1 assertion does not catch the second-arg regression

**What goes wrong:** Test 1 (`test_ws_cancel_action_calls_cancel_agent`) only asserts `call_args[0][0] == "a1"`. It would pass whether server.py passes a `TaskSpec` as second arg or nothing. This means test 1 currently provides no regression protection for the cancel branch.

**How to avoid:** Update test 1 to `mock_orch.cancel_agent.assert_awaited_once_with("a1")` (no second arg) to lock in the correct contract.

## Code Examples

### Verified current state — broken cancel branch in server.py

```python
# Source: packages/conductor-core/src/conductor/dashboard/server.py lines 83-95
# BROKEN — passes TaskSpec where new_instructions: str | None is expected
if action == "cancel":
    from conductor.orchestrator.models import TaskSpec

    await orchestrator.cancel_agent(
        agent_id,
        TaskSpec(
            id=agent_id,
            title="Cancelled from dashboard",
            description="",
            role="",
            target_file="",
        ),
    )
```

### Verified current state — broken redirect branch in server.py

```python
# Source: packages/conductor-core/src/conductor/dashboard/server.py lines 99-112
# BROKEN — passes TaskSpec where new_instructions: str | None is expected
elif action == "redirect":
    from conductor.orchestrator.models import TaskSpec

    message = command.get("message", "")
    await orchestrator.cancel_agent(
        agent_id,
        TaskSpec(
            id=agent_id,
            title="Redirected from dashboard",
            description=message,
            role="",
            target_file="",
        ),
    )
```

### Target state — fixed cancel branch

```python
# server.py handle_intervention — after fix
if action == "cancel":
    await orchestrator.cancel_agent(agent_id)
```

### Target state — fixed redirect branch

```python
# server.py handle_intervention — after fix
elif action == "redirect":
    message = command.get("message", "")
    await orchestrator.cancel_agent(agent_id, new_instructions=message)
```

### Orchestrator cancel_agent signature (verified correct since Phase 12)

```python
# Source: packages/conductor-core/src/conductor/orchestrator/orchestrator.py lines 376-427
# inspect.signature(Orchestrator.cancel_agent) == (self, agent_id: 'str', new_instructions: 'str | None' = None) -> 'None'
async def cancel_agent(
    self, agent_id: str, new_instructions: str | None = None
) -> None:
    ...
    corrected_spec = TaskSpec(
        ...
        description=new_instructions if new_instructions else task.description,
        ...
    )
```

### Target test 1 — assert correct cancel contract

```python
# tests/dashboard/test_server_interventions.py test 1 — after fix
mock_orch.cancel_agent.assert_awaited_once_with("a1")
```

### Target test 3 — assert correct redirect contract

```python
# tests/dashboard/test_server_interventions.py test 3 — after fix
mock_orch.cancel_agent.assert_awaited_once_with("a1", new_instructions="new instructions here")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| cancel_agent(agent_id, corrected_spec: TaskSpec) | cancel_agent(agent_id, new_instructions: str \| None = None) | Phase 12 | CLI callers no longer need to construct TaskSpec |
| server.py builds partial TaskSpec for cancel/redirect | server.py passes agent_id + str \| None | Phase 15 (this phase) | Dashboard callers align with Phase 12 contract; agent re-spawn preserves original role/target_file from state |

**Deprecated/outdated:**
- `from conductor.orchestrator.models import TaskSpec` inside `handle_intervention`: remove entirely after Phase 15 fix. The server layer no longer needs this import.
- Asserting `call_args[0][1].description` in test 3: replace with `assert_awaited_once_with("a1", new_instructions=...)`.

## Open Questions

1. **Should test 2 (feedback) be changed?**
   - What we know: The feedback branch correctly calls `inject_guidance(agent_id, message)` with string args. Test 2 correctly asserts `inject_guidance.assert_called_once_with("a1", "looks good")`. No change needed.
   - Recommendation: Leave test 2 unchanged.

2. **Are there other callers of cancel_agent that still pass TaskSpec?**
   - What we know: Searched all Python source files. Only two callers exist: `input_loop.py` (correct, fixed in Phase 12) and `server.py` (broken, this phase's target).
   - Recommendation: No other call sites to fix.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | packages/conductor-core/pyproject.toml |
| Quick run command | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/dashboard/test_server_interventions.py -v` |
| Full suite command | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMM-05 | Orchestrator can cancel a sub-agent's work and reassign with corrected instructions | integration | `pytest tests/dashboard/test_server_interventions.py -k "cancel or redirect" -v` | Yes (tests 1+3 need assertion update) |
| DASH-06 | User can intervene from dashboard (cancel, redirect, provide feedback to agents) | integration | `pytest tests/dashboard/test_server_interventions.py -v` | Yes (all 8 tests exist; tests 1+3 need correction) |

### Sampling Rate
- **Per task commit:** `uv run --project packages/conductor-core pytest packages/conductor-core/tests/dashboard/test_server_interventions.py -v`
- **Per wave merge:** `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q`
- **Phase gate:** Full suite green (currently 298 passed; must remain 298+ after fix)

### Wave 0 Gaps
None — existing test infrastructure covers all requirements. The two tests that need updating (test 1 assertion tightening, test 3 assertion correction) exist already. No new test files or framework installs are needed.

## Sources

### Primary (HIGH confidence)
- Direct source read: `packages/conductor-core/src/conductor/dashboard/server.py` lines 83-112 — confirmed both cancel and redirect branches pass TaskSpec to cancel_agent
- Direct source read: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` lines 376-427 — confirmed Phase 12 fixed signature `cancel_agent(agent_id, new_instructions: str | None = None)`
- Runtime inspection: `inspect.signature(Orchestrator.cancel_agent)` returns `(self, agent_id: 'str', new_instructions: 'str | None' = None) -> 'None'`
- Direct source read: `packages/conductor-core/tests/dashboard/test_server_interventions.py` lines 94-120 — confirmed test 3 asserts wrong contract (TaskSpec positional arg)
- Runtime test run: `uv run pytest tests/dashboard/test_server_interventions.py -v` → 8 passed (all pass because mock accepts any args regardless of correctness)
- Runtime test run: `uv run pytest tests/ -q` → 298 passed (full baseline)

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` Phase 12 decision: "cancel_agent reconstructs TaskSpec from state internally — CLI only needs to pass agent_id and optional new_instructions string" — confirms intended API
- `.planning/phases/12-fix-cli-cancel-redirect/12-01-SUMMARY.md` — confirms Phase 12 changed signature, only modified orchestrator.py and test_orchestrator.py, did NOT touch server.py

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Bug identification: HIGH — confirmed by direct code inspection; server.py still imports and passes TaskSpec after Phase 12 fixed the orchestrator
- Fix approach: HIGH — one-line fix per branch; mirrors the exact API the CLI already uses correctly
- Test gaps: HIGH — test 3 confirmed to assert wrong contract; identified by direct code inspection
- Side effects: HIGH — no other callers of cancel_agent with TaskSpec arg exist; removing import from server.py has no downstream effect

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable domain — internal Python refactor, no external library churn)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMM-05 | Orchestrator can cancel a sub-agent's work and reassign with corrected instructions | server.py cancel branch must call `cancel_agent(agent_id)` — no TaskSpec; orchestrator then looks up task from state and re-spawns with original spec |
| DASH-06 | User can intervene from dashboard (cancel, redirect, provide feedback to agents) | All three intervention types (cancel, redirect, feedback) must call correct orchestrator methods with correct arg types; redirect must call `cancel_agent(agent_id, new_instructions=message)` |
</phase_requirements>
