# Phase 13: Wire Escalation Router + Pause Surface - Research

**Researched:** 2026-03-11
**Domain:** Python async wiring (orchestrator + ACP), CLI command extension, React/TypeScript dashboard intervention UI
**Confidence:** HIGH

## Summary

Phase 13 closes two distinct mechanical gaps in an otherwise complete system. The EscalationRouter
(in `conductor/orchestrator/escalation.py`) exists and is fully tested, but it is never wired as
the `permission_handler` for `ACPClient` sessions created inside `_run_agent_loop`. As a result,
sub-agent `AskUserQuestion` calls fall through to the PermissionHandler's no-state default
("proceed" for everything), and interactive-mode escalation to humans never fires at runtime.
Separately, `pause_for_human_decision` exists on the orchestrator but is reachable by no surface:
the CLI `_dispatch_command` has no `pause` branch, and the dashboard's `handle_intervention` has
no `pause` action, and `InterventionCommand` type has no `"pause"` action variant.

Each gap is a one-file change (plus a corresponding test fix/addition). No new logic needs to be
invented — all of it already exists. This phase is pure wiring and surface exposure.

**Primary recommendation:** Wire `EscalationRouter.resolve` as `answer_fn` when constructing
`PermissionHandler` inside `_run_agent_loop`, then add `pause` branches to the CLI dispatcher and
dashboard server+frontend.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMM-03 | In `--auto` mode, orchestrator uses best judgment to answer questions and logs decisions | EscalationRouter.resolve() already implements this via _auto_answer(). Fix: wire it as answer_fn in _run_agent_loop so it actually runs at runtime |
| COMM-04 | In interactive mode, orchestrator escalates questions it can't confidently answer to the human | EscalationRouter already supports interactive mode with human_out/human_in queues. Same wiring fix — the router needs to reach the PermissionHandler that the ACPClient uses |
| COMM-07 | Orchestrator can pause a sub-agent and escalate to human for a decision | pause_for_human_decision() exists on Orchestrator. Needs: CLI `pause` command, dashboard `pause` action in handle_intervention, `"pause"` in InterventionCommand TypeScript type |
</phase_requirements>

---

## Gap 1: EscalationRouter Unwired (ESCALATION-ROUTER-UNWIRED)

### What Exists

`Orchestrator.__init__` constructs a fully configured `EscalationRouter`:

```python
# orchestrator.py line 125-129
self._escalation_router = EscalationRouter(
    mode=mode,
    human_out=human_out,
    human_in=human_in,
)
```

`PermissionHandler` accepts an `answer_fn` parameter that routes `AskUserQuestion` calls:

```python
# permission.py line 20
_AnswerFn = Callable[[dict], Awaitable[PermissionResultAllow | PermissionResultDeny]]
```

`EscalationRouter.resolve` has exactly this signature: `async def resolve(self, input_data: dict) -> PermissionResultAllow | PermissionResultDeny`.

### What's Missing

`_run_agent_loop` creates `ACPClient` with no `permission_handler`:

```python
# orchestrator.py line 550-554 — the gap
async with ACPClient(
    cwd=self._repo_path,
    system_prompt=system_prompt,
    resume=resume_session_id,
    # permission_handler is absent — EscalationRouter never fires
) as client:
```

Without `permission_handler`, `can_use_tool` is `None` in `ClaudeAgentOptions`. Sub-agent
`AskUserQuestion` calls are unhandled — the SDK passes them through unanswered. The
`_escalation_router` stored on the orchestrator is never called at session time.

### The Fix

Construct a `PermissionHandler` that wraps `self._escalation_router.resolve` and pass it when
creating `ACPClient`:

```python
# In _run_agent_loop, before async with ACPClient:
from conductor.acp.permission import PermissionHandler

handler = PermissionHandler(answer_fn=self._escalation_router.resolve)

async with ACPClient(
    cwd=self._repo_path,
    system_prompt=system_prompt,
    resume=resume_session_id,
    permission_handler=handler,
) as client:
```

`PermissionHandler` already handles the `timeout` wrapping (default 30s) and correctly routes
`AskUserQuestion` → `answer_fn` while default-allowing all other tools. No changes to
`PermissionHandler`, `EscalationRouter`, or `ACPClient` are needed.

**Confidence:** HIGH — all code paths verified by reading the source.

---

## Gap 2: Pause Unreachable (PAUSE-UNREACHABLE)

### What Exists

`Orchestrator.pause_for_human_decision` is fully implemented (orchestrator.py line 448-498):
- Interrupts the agent via `client.interrupt()`
- Drains stream_response() to prevent stale message corruption
- Pushes `HumanQuery` to `human_out`
- Awaits answer from `human_in` with 120s timeout fallback
- Resumes agent with `client.send(f"Human decision: {decision}...")`

### What's Missing

**CLI gap:** `_dispatch_command` in `input_loop.py` handles: `cancel`, `feedback`, `redirect`,
`status`, `quit`/`exit`. There is no `pause` branch. Users cannot invoke
`pause_for_human_decision` from the terminal.

**Dashboard backend gap:** `handle_intervention` in `server.py` handles: `cancel`, `feedback`,
`redirect`. There is no `pause` branch. WebSocket `pause` messages from the frontend are silently
ignored.

**Dashboard frontend gap:**
- `InterventionCommand` TypeScript type in `conductor.ts` only allows `"cancel" | "redirect" | "feedback"`
- `InterventionPanel.tsx` has no Pause button

### The Fix — CLI

Add a `pause` branch to `_dispatch_command` in `input_loop.py`:

```python
elif cmd == "pause":
    if len(tokens) < 3:
        console.print("[red]Usage: pause <agent_id> <question...>[/]")
        return False
    agent_id = tokens[1]
    question = " ".join(tokens[2:])
    await orchestrator.pause_for_human_decision(
        agent_id,
        question,
        human_out,
        human_in,
    )
    console.print(f"[green]Paused agent {agent_id}, awaiting human decision...[/]")
```

The `_dispatch_command` function currently does NOT have `human_out`/`human_in` parameters — they
are only available in the outer `_input_loop`. Two implementation choices:

**Option A (preferred):** Pass `human_out` and `human_in` as parameters to `_dispatch_command`.
This is consistent with how `state_manager` and `console` are already passed. Low refactor cost.

**Option B:** Call `pause_for_human_decision` with new queue instances. This breaks the shared
queue contract — the human_in/human_out in the CLI loop must be the same queues.

Use Option A: add `human_out: asyncio.Queue | None = None, human_in: asyncio.Queue | None = None`
parameters to `_dispatch_command`. The `_input_loop` already has both queues — pass them through.

### The Fix — Dashboard Backend

Add a `pause` branch to `handle_intervention` in `server.py`:

```python
elif action == "pause":
    question = command.get("message", "pause requested from dashboard")
    # pause_for_human_decision needs the shared human_out/human_in queues
    # These must be passed through create_app -> handle_intervention
    await orchestrator.pause_for_human_decision(
        agent_id,
        question,
        orchestrator._human_out,
        orchestrator._human_in,
    )
```

`pause_for_human_decision` requires `human_out` and `human_in` queues. The orchestrator already
holds `self._human_out` and `self._human_in`. The dashboard server can access these via
`orchestrator._human_out` / `orchestrator._human_in` directly (they are already private
attributes, accessing via underscore is acceptable for wiring in the dashboard).

Alternatively, add a public property to `Orchestrator` exposing these queues. This avoids private
access and is cleaner. Recommended: add `@property human_queues(self) -> tuple[Queue, Queue] | None`.

Actually, simplest option consistent with the codebase pattern: `pause_for_human_decision` already
takes `human_out` and `human_in` as explicit parameters. The server can pass
`orchestrator._human_out` and `orchestrator._human_in` directly — no new API needed. Follow the
existing `cancel_agent`/`inject_guidance` pattern of try/except in `handle_intervention`.

### The Fix — Dashboard Frontend

Add `"pause"` to the `InterventionCommand` action union in `types/conductor.ts`:

```typescript
export interface InterventionCommand {
  action: "cancel" | "redirect" | "feedback" | "pause";
  agent_id: string;
  message?: string;
}
```

Add a Pause button to `InterventionPanel.tsx`. It should fire immediately (like Cancel, not like
Feedback/Redirect which open inline inputs), but it needs a question. Design decision: show an
inline input (like Feedback/Redirect) where the user types their pause question, then sends.

The `activeInput` state type needs a `"pause"` variant:

```typescript
type ActiveInput = "feedback" | "redirect" | "pause" | null;
```

The Pause button renders with its own color class (e.g., amber-600 or purple-100/700 to
distinguish from Redirect's amber) and a placeholder "Question for the agent..." in the input.

---

## Standard Stack

### Core (no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `conductor.acp.permission.PermissionHandler` | (local) | Routes AskUserQuestion → answer_fn | Already exists, already tested |
| `conductor.orchestrator.escalation.EscalationRouter` | (local) | Answers sub-agent questions by mode | Already exists, all tests green |
| `asyncio.Queue` | stdlib | human_out/human_in communication channel | Already in use throughout the system |
| React `useState` | 18.x | UI state for activeInput in InterventionPanel | Already in use |

No new pip or npm dependencies are required for this phase.

---

## Architecture Patterns

### Pattern 1: PermissionHandler Wrapping an AnswerFn

The `PermissionHandler` acts as an adapter between the SDK's `can_use_tool` callback API and the
orchestrator's `EscalationRouter.resolve` method. The wiring point is `_run_agent_loop`, which is
the only place where `ACPClient` sessions are created:

```python
# Source: packages/conductor-core/src/conductor/acp/permission.py
# Source: packages/conductor-core/src/conductor/orchestrator/orchestrator.py

handler = PermissionHandler(answer_fn=self._escalation_router.resolve)
async with ACPClient(..., permission_handler=handler) as client:
```

`PermissionHandler` wraps the answer_fn call in `asyncio.wait_for(timeout=30.0)`. The
`EscalationRouter` internally uses `asyncio.wait_for(timeout=120.0)` for human escalation. The
outer 30s timeout must NOT conflict with the inner 120s timeout. Resolution: increase
`PermissionHandler`'s default timeout when constructing it here, or accept that the human
escalation path will timeout at 30s (safe, falls back to "proceed"). Since the current default is
30s and human escalation can wait 120s, the PermissionHandler timeout should be set to a value
greater than `EscalationRouter.human_timeout` when in interactive mode.

**Recommendation:** Pass `timeout=self._escalation_router._human_timeout + 30.0` to
`PermissionHandler` when constructing it inside `_run_agent_loop`, or expose a public
`human_timeout` attribute on `EscalationRouter`. This prevents the outer handler from cutting off
a pending human answer.

### Pattern 2: CLI Command Dispatch via Token Splitting

`_dispatch_command` uses `tokens = line.strip().split()` and branches on `cmd = tokens[0].lower()`.
The `pause` command follows the same signature as `feedback`:

```
pause <agent_id> <question...>
```

The question text is the remainder after token[1]: `" ".join(tokens[2:])`.

### Pattern 3: Dashboard WebSocket Intervention Routing

`handle_intervention` parses JSON, extracts `action` and `agent_id`, dispatches to orchestrator
methods, wrapped in `try/except Exception` so connection errors don't crash the server. The `pause`
action follows the same pattern as `feedback`:

```python
elif action == "pause":
    question = command.get("message", "pause requested from dashboard")
    await orchestrator.pause_for_human_decision(
        agent_id, question, orchestrator._human_out, orchestrator._human_in
    )
```

### Pattern 4: InterventionPanel Inline Input for Pause

The `pause` action requires a question string from the user before firing. It should follow the
same "toggle → type → send" UX as `feedback` and `redirect`. Extend `activeInput` to include
`"pause"`:

- Button color suggestion: `bg-purple-100 text-purple-700 hover:bg-purple-200` (distinguishable
  from Redirect's amber and Feedback's blue)
- Placeholder: `"Question to ask the human..."`
- On send: `onIntervene({ action: "pause", agent_id: agentId, message })`

### Anti-Patterns to Avoid

- **Creating a new PermissionHandler per question:** The handler should be constructed once per
  agent session (inside `_run_agent_loop`), not per permission request.
- **Using orchestrator._human_out/_human_in from tests without mock:** Tests for the CLI `pause`
  command must pass mock queues explicitly; don't assume the orchestrator always has queues set.
- **Adding "pause" to InterventionCommand without the backend handler:** Frontend and backend must
  both be updated atomically — a `pause` command sent to a backend that doesn't handle it will
  result in a silent no-op.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timeout wrapping for async answer_fn | Custom timeout logic | `PermissionHandler` with `timeout` param | Already wraps in `asyncio.wait_for`; handles denial on timeout |
| Queue communication between CLI and orchestrator | New queue type | Existing `asyncio.Queue[HumanQuery]` / `asyncio.Queue[str]` pair | Already wired in `_run_async` and `_input_loop` |
| Agent interruption | Manual stream draining | `client.interrupt()` + `stream_response()` drain | Already implemented in `pause_for_human_decision` |

---

## Common Pitfalls

### Pitfall 1: PermissionHandler Timeout Cuts Off Human Escalation

**What goes wrong:** `PermissionHandler` default timeout is 30s. `EscalationRouter` human timeout
is 120s. If a sub-agent asks a question that routes to the human, the outer 30s timer fires first,
returning `PermissionResultDeny` before the human can answer.

**Why it happens:** Two nested `asyncio.wait_for` calls with the outer timeout shorter than the
inner.

**How to avoid:** Set `PermissionHandler(timeout=self._escalation_router._human_timeout + 30.0)`
so the outer deadline is always beyond the inner escalation deadline. In auto mode, this doesn't
matter (no human wait), so it's safe to always apply.

**Warning signs:** Tests pass individually but human escalation always "falls back to proceed"
even when an answer is provided.

### Pitfall 2: pause_for_human_decision Called on Inactive Agent

**What goes wrong:** `pause_for_human_decision` raises `EscalationError` if `agent_id` is not in
`self._active_clients`. The CLI and dashboard must handle this gracefully.

**How to avoid:** Wrap the `pause` dispatch in `try/except EscalationError` in both the CLI
dispatcher and `handle_intervention`, printing a helpful message ("Agent not active or already
finished").

### Pitfall 3: Stale Queue Messages After Pause

**What goes wrong:** If `pause_for_human_decision` is called while a human question is already in
`human_out` from `EscalationRouter`, the CLI input loop may consume the pause question as if it
were a router question, causing `human_in` to get the wrong answer.

**Why it happens:** Both `EscalationRouter` and `pause_for_human_decision` use the same
`human_out`/`human_in` queue pair. A queued router question and a manual pause question are
indistinguishable.

**How to avoid:** This is an existing design constraint, not a new problem introduced by Phase 13.
Document it but don't change the queue architecture in this phase. A `HumanQuery.source` field
could disambiguate in a future phase.

### Pitfall 4: InterventionCommand "pause" Action Not in Backend

**What goes wrong:** Frontend sends `{action: "pause", ...}` but backend `handle_intervention` has
no matching branch — silent no-op.

**How to avoid:** Update both `conductor.ts` TypeScript type and `server.py` `handle_intervention`
in the same plan/task. Update `test_server_interventions.py` to verify the pause branch.

---

## Code Examples

### Wiring EscalationRouter in _run_agent_loop

```python
# Source: packages/conductor-core/src/conductor/orchestrator/orchestrator.py
# In _run_agent_loop, before: async with ACPClient(...)

from conductor.acp.permission import PermissionHandler

handler = PermissionHandler(
    answer_fn=self._escalation_router.resolve,
    timeout=self._escalation_router._human_timeout + 30.0,
)

async with ACPClient(
    cwd=self._repo_path,
    system_prompt=system_prompt,
    resume=resume_session_id,
    permission_handler=handler,
) as client:
```

### CLI pause Command in _dispatch_command

```python
# Source: packages/conductor-core/src/conductor/cli/input_loop.py
elif cmd == "pause":
    if len(tokens) < 3:
        console.print("[red]Usage: pause <agent_id> <question...>[/]")
        return False
    agent_id = tokens[1]
    question = " ".join(tokens[2:])
    if human_out is None or human_in is None:
        console.print("[red]pause requires interactive mode[/]")
        return False
    try:
        await orchestrator.pause_for_human_decision(
            agent_id, question, human_out, human_in
        )
        console.print(f"[green]Paused agent {agent_id}[/]")
    except Exception as e:
        console.print(f"[red]pause failed: {e}[/]")
```

### Dashboard pause in handle_intervention

```python
# Source: packages/conductor-core/src/conductor/dashboard/server.py
elif action == "pause":
    question = command.get("message", "pause requested from dashboard")
    if orchestrator._human_out is not None and orchestrator._human_in is not None:
        await orchestrator.pause_for_human_decision(
            agent_id,
            question,
            orchestrator._human_out,
            orchestrator._human_in,
        )
```

### InterventionPanel.tsx with Pause

```typescript
// Source: packages/conductor-dashboard/src/components/InterventionPanel.tsx
type ActiveInput = "feedback" | "redirect" | "pause" | null;

// In the button row:
<button
  type="button"
  onClick={() => handleToggle("pause")}
  className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
    activeInput === "pause"
      ? "bg-purple-600 text-white"
      : "bg-purple-100 text-purple-700 hover:bg-purple-200"
  }`}
>
  Pause
</button>

// Placeholder in the shared input:
placeholder={
  activeInput === "feedback"
    ? "Send feedback to agent..."
    : activeInput === "redirect"
    ? "New instructions for agent..."
    : "Question for the human..."
}
```

### InterventionCommand Type Update

```typescript
// Source: packages/conductor-dashboard/src/types/conductor.ts
export interface InterventionCommand {
  action: "cancel" | "redirect" | "feedback" | "pause";
  agent_id: string;
  message?: string;
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No wiring (EscalationRouter silently unused) | Wire as answer_fn in _run_agent_loop | Phase 13 | COMM-03/04 actually fire at runtime |
| No pause CLI command | `pause <agent_id> <question>` dispatch branch | Phase 13 | COMM-07 reachable from CLI |
| No pause in dashboard | `pause` action in handle_intervention + Pause button | Phase 13 | COMM-07 reachable from dashboard |

---

## Open Questions

1. **PermissionHandler timeout for interactive mode**
   - What we know: PermissionHandler default is 30s, EscalationRouter human_timeout is 120s
   - What's unclear: Should `human_timeout` be a public attribute on EscalationRouter to avoid
     `._human_timeout` private access?
   - Recommendation: Expose it as a public property `human_timeout: float` or just use 150.0 as
     a hardcoded constant in _run_agent_loop (simple, no new API surface)

2. **Dashboard pause: orchestrator queue availability**
   - What we know: `orchestrator._human_out` is None in `--auto` mode
   - What's unclear: Should the pause endpoint return an error when called in auto mode?
   - Recommendation: Check for None and silently ignore (same pattern as orchestrator=None for
     the whole server), or log a warning. Do not raise.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (Python) + vitest 4.x (TypeScript) |
| Config file | `packages/conductor-core/pyproject.toml` (pytest) / `packages/conductor-dashboard/vitest.config.ts` |
| Quick run command (Python) | `uv run pytest packages/conductor-core/tests/test_orchestrator.py packages/conductor-core/tests/test_escalation.py -q` |
| Quick run command (TS) | `pnpm --filter conductor-dashboard test --reporter=verbose` |
| Full suite command | `uv run pytest packages/conductor-core/tests/ -q && pnpm --filter conductor-dashboard test` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMM-03 | EscalationRouter.resolve called as answer_fn in auto mode | unit | `uv run pytest packages/conductor-core/tests/test_orchestrator.py -k "permission_handler or escalation" -x` | ❌ Wave 0 |
| COMM-04 | EscalationRouter.resolve called as answer_fn in interactive mode | unit | `uv run pytest packages/conductor-core/tests/test_orchestrator.py -k "permission_handler or interactive" -x` | ❌ Wave 0 |
| COMM-07 CLI | CLI `pause` command dispatches to pause_for_human_decision | unit | `uv run pytest packages/conductor-core/tests/test_cli.py -k "pause" -x` | ❌ Wave 0 |
| COMM-07 Dashboard | Dashboard `pause` action calls orchestrator.pause_for_human_decision | unit | `uv run pytest packages/conductor-core/tests/dashboard/test_server_interventions.py -k "pause" -x` | ❌ Wave 0 |
| COMM-07 Frontend | InterventionPanel renders Pause button and sends pause command | unit | `pnpm --filter conductor-dashboard test -- --reporter=verbose InterventionPanel` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest packages/conductor-core/tests/ -q`
- **Per wave merge:** `uv run pytest packages/conductor-core/tests/ -q && pnpm --filter conductor-dashboard test`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

All test files already exist. New test cases need to be added to:
- [ ] `packages/conductor-core/tests/test_orchestrator.py` — add test that `_run_agent_loop` creates `PermissionHandler` with `answer_fn=escalation_router.resolve`
- [ ] `packages/conductor-core/tests/test_cli.py` — add test for `pause <agent_id> <question>` dispatch
- [ ] `packages/conductor-core/tests/dashboard/test_server_interventions.py` — add test for `pause` action
- [ ] `packages/conductor-dashboard/src/components/InterventionPanel.test.tsx` — add tests for Pause button

No new test files needed. No framework install needed (both test stacks are already installed and green: 290 Python tests, 77 TypeScript tests).

---

## Sources

### Primary (HIGH confidence)

- Direct source reading: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — confirmed EscalationRouter constructed but not wired to ACPClient
- Direct source reading: `packages/conductor-core/src/conductor/acp/client.py` — confirmed `permission_handler` parameter exists and wires `can_use_tool`
- Direct source reading: `packages/conductor-core/src/conductor/acp/permission.py` — confirmed `answer_fn` parameter and `_AnswerFn` type compatibility
- Direct source reading: `packages/conductor-core/src/conductor/cli/input_loop.py` — confirmed no `pause` branch exists
- Direct source reading: `packages/conductor-core/src/conductor/dashboard/server.py` — confirmed no `pause` branch in `handle_intervention`
- Direct source reading: `packages/conductor-dashboard/src/components/InterventionPanel.tsx` — confirmed no Pause button
- Direct source reading: `packages/conductor-dashboard/src/types/conductor.ts` — confirmed `InterventionCommand` missing `"pause"`
- Test runs: 290 Python tests pass, 77 TypeScript tests pass (baseline green)

### Secondary (MEDIUM confidence)

- STATE.md decision log — confirms all relevant design decisions for EscalationRouter, ACPClient, PermissionHandler from Phases 3, 6, 8, 10

---

## Metadata

**Confidence breakdown:**
- Gap identification: HIGH — confirmed by direct code inspection, no ambiguity
- Fix approach: HIGH — all wiring points are mechanical one-file changes using existing APIs
- Timeout conflict (Pitfall 1): HIGH — confirmed by reading both timeout values
- Queue contention (Pitfall 3): MEDIUM — theoretical race, not observed in tests, design constraint acknowledged

**Research date:** 2026-03-11
**Valid until:** 2026-06-01 (code is stable; no external dependencies changing)
