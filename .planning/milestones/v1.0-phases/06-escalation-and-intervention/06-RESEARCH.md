# Phase 6: Escalation and Intervention - Research

**Researched:** 2026-03-11
**Domain:** Orchestrator decision routing, `--auto` vs interactive mode, `ACPClient.interrupt()`, mid-stream guidance injection, human-in-the-loop CLI escalation
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COMM-03 | In `--auto` mode, orchestrator uses best judgment to answer questions and logs decisions | `PermissionHandler` already answers all `AskUserQuestion` calls; Phase 6 adds a mode flag that controls whether the orchestrator consults the human (interactive) or decides autonomously and logs its reasoning (auto). The log destination is `ConductorState` or a structured log on disk. |
| COMM-04 | In interactive mode, orchestrator escalates questions it can't confidently answer to the human | `PermissionHandler.answer_fn` is a replaceable callback. Phase 6 introduces an `EscalationRouter` that detects low-confidence questions and, in interactive mode, blocks on a `asyncio.Queue` fed by CLI input — with `asyncio.wait_for` guarding against deadlock. |
| COMM-05 | Orchestrator can cancel a sub-agent's work and reassign with corrected instructions | `ACPClient.interrupt()` already wraps `ClaudeSDKClient.interrupt()`, which sends `{"subtype": "interrupt"}` via the control protocol. After interrupt, the orchestrator closes the session (`__aexit__`), writes `TaskStatus.FAILED` to state, then spawns a new `_run_agent_loop()` with updated instructions. The reassignment does NOT reuse the old session — it creates a new `ACPClient`. |
| COMM-06 | Orchestrator can inject guidance to a sub-agent mid-stream without stopping their work | `ACPClient.send()` wraps `ClaudeSDKClient.query()` which writes a user-turn message to the live session via `transport.write()`. This can be called while `stream_response()` is running in a concurrent `asyncio.Task` — no interrupt needed. The sub-agent receives the new user message and incorporates it in its next reply. |
| COMM-07 | Orchestrator can pause a sub-agent and escalate to human for a decision before resuming | Pause = `ACPClient.interrupt()` (stops current turn), then orchestrator writes the question to a CLI output queue and blocks on an answer queue. On answer, orchestrator calls `ACPClient.send(decision)` + re-enters `stream_response()`. This requires the session to remain open (inside `async with ACPClient`) across the pause. |
</phase_requirements>

---

## Summary

Phase 6 adds three interlocking concerns to the orchestrator: (1) a **mode switch** between `--auto` (fully autonomous) and interactive (human-in-the-loop), (2) **intervention commands** the orchestrator can apply to running sub-agents (cancel/redirect, inject guidance, pause/resume), and (3) a **human escalation channel** over which interactive questions flow to the CLI and answers flow back.

The SDK primitives for all three concerns already exist and are verified in the installed `claude_agent_sdk` 0.1.48. `ACPClient.interrupt()` triggers a session-level interrupt via the control protocol. `ACPClient.send()` delivers a user-turn message to an open session whether or not the session is currently streaming — this is the injection primitive. The session stays open across an interrupt if the `async with ACPClient` block remains active. After an interrupt, the sub-agent's current turn is aborted; calling `send()` + re-entering `stream_response()` starts a new turn in the same session.

The human escalation channel does not exist yet. Phase 6 must design a minimal in-process queue: the orchestrator pushes a `HumanQuery` object to an output queue that the CLI (Phase 8) will eventually drain; a corresponding answer queue delivers the response back. In this phase, the CLI is not built yet — the planner must provide a stub that reads from `stdin` or a simple `asyncio.Queue` driven by tests. The production wiring to the real CLI happens in Phase 8.

**Primary recommendation:** Implement `EscalationRouter` as the single decision point that inspects mode (`auto` vs `interactive`) and question confidence, and routes accordingly. Keep `PermissionHandler` unchanged — it calls the router's `resolve()` method as its `answer_fn`. The orchestrator passes the router at construction time so tests can inject a fake router without patching globals.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude_agent_sdk` | 0.1.48 (installed) | `ACPClient.interrupt()`, `ACPClient.send()` for all intervention commands | All primitives verified in SDK source; `interrupt()` sends `{"subtype": "interrupt"}` control request; `send()` sends a user-turn message via `transport.write()` |
| `asyncio` | stdlib | `asyncio.Queue` for human I/O channel; `asyncio.wait_for` to guard escalation blocking; `asyncio.Event` for pause/resume synchronization | Same pattern already in use in Phase 3 permission timeout handling |
| `pydantic` | >=2.10 (installed) | `DecisionLog` model for structured auto-mode decision logging; `HumanQuery` model for escalation channel type safety | Already established in Phases 2-5 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-asyncio` | >=8.0 / >=0.23 | Test async escalation queue, interrupt semantics, mode switching | Already in dev deps; `asyncio_mode = "auto"` already configured |
| `unittest.mock` | stdlib | `AsyncMock` for `ACPClient` to test interrupt + send sequences; mock `asyncio.Queue` for escalation channel | Existing pattern from test_orchestrator.py |
| `logging` | stdlib | Structured log output for auto-mode decision audit trail | No new dependency; use `logging.getLogger("conductor.orchestrator")` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.Queue` for human I/O channel | Shared file / socket / pipe | Queue is in-process, zero-latency, testable without I/O setup. The CLI (Phase 8) will drain the same queue — it runs in the same process. File/socket adds complexity with no benefit in-process. |
| `EscalationRouter` as a separate class | Logic embedded in `PermissionHandler` | Router is tested independently of permission handling. Mixing them makes unit testing hard and violates single-responsibility. |
| `interrupt()` then close session for cancel/redirect | `interrupt()` then `send(new_instructions)` in same session | Sending new instructions in an interrupted session can produce unexpected continuation of the prior task. Clean cancel = interrupt + close + new session. Guidance injection = `send()` without interrupt, in the same session. These are distinct operations that must not be conflated. |
| Confidence-score via LLM call | Rule-based keyword matching | LLM call adds latency and cost to every permission callback, which runs in the critical path. Rule-based matching (e.g., question contains "delete", "rm", "drop", "irreversible") with conservative thresholds is fast and sufficient for v1. |

**Installation:**
```bash
# No new runtime dependencies — all needed libraries are already installed
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/conductor/
├── orchestrator/
│   ├── orchestrator.py      # EXTEND: accept EscalationRouter; add cancel_agent(), inject_guidance(), pause_agent() methods
│   ├── escalation.py        # NEW: EscalationRouter, HumanQuery, DecisionLog, confidence heuristic
│   └── errors.py            # EXTEND: add EscalationError, InterruptError
└── acp/
    └── client.py            # NO CHANGE: interrupt() already implemented in Phase 3

tests/
├── test_escalation.py       # NEW: COMM-03/04 — EscalationRouter auto vs interactive mode, confidence routing
└── test_orchestrator.py     # EXTEND: COMM-05/06/07 — cancel+reassign, mid-stream inject, pause+resume
```

### Pattern 1: Mode-Aware Escalation Router (COMM-03, COMM-04)

**What:** `EscalationRouter` is the single decision point. It receives a `question: str` (from `AskUserQuestion.input_data`) and returns an `answer: str`. In `--auto` mode it uses rule-based heuristics to pick an answer and logs to `DecisionLog`. In interactive mode it first checks heuristics — if high-confidence, answers autonomously; if low-confidence, pushes to the human channel and awaits the response via `asyncio.wait_for`.

**When to use:** Replace the `answer_fn` in `PermissionHandler` with `EscalationRouter.resolve`.

**Example:**
```python
# Source: verified against existing PermissionHandler pattern (conductor/acp/permission.py)
import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger("conductor.orchestrator")

@dataclass
class HumanQuery:
    """A question the orchestrator cannot confidently answer autonomously."""
    question: str
    context: dict
    timestamp: str

@dataclass
class DecisionLog:
    """Structured record of an auto-mode decision."""
    question: str
    answer: str
    confidence: str  # "high" | "low"
    rationale: str
    timestamp: str

_LOW_CONFIDENCE_KEYWORDS = frozenset({
    "delete", "drop", "remove", "irreversible", "cannot be undone",
    "production", "deploy", "billing", "secret", "credentials",
})

def _is_low_confidence(question: str) -> bool:
    """Return True if the question contains keywords suggesting high risk."""
    q = question.lower()
    return any(kw in q for kw in _LOW_CONFIDENCE_KEYWORDS)


class EscalationRouter:
    """Routes sub-agent questions to auto-answer or human escalation.

    Args:
        mode: "auto" (never block on human) or "interactive" (escalate low-confidence).
        human_out: Queue the CLI drains for questions to display to the human.
        human_in: Queue the CLI writes answers into.
        human_timeout: Max seconds to wait for a human answer before using auto fallback.
    """

    def __init__(
        self,
        mode: str = "auto",
        human_out: asyncio.Queue | None = None,
        human_in: asyncio.Queue | None = None,
        human_timeout: float = 120.0,
    ) -> None:
        self._mode = mode
        self._human_out = human_out
        self._human_in = human_in
        self._human_timeout = human_timeout

    async def resolve(self, input_data: dict) -> str:
        """Return an answer for an AskUserQuestion input_data dict."""
        questions: list[dict] = input_data.get("questions", [])
        if not questions:
            return "proceed"

        question_text = questions[0].get("question", "")
        low_confidence = _is_low_confidence(question_text)

        if self._mode == "interactive" and low_confidence and self._human_out and self._human_in:
            return await self._escalate_to_human(question_text)

        # Auto-mode (or high-confidence interactive): answer autonomously
        answer = "proceed"
        entry = DecisionLog(
            question=question_text,
            answer=answer,
            confidence="low" if low_confidence else "high",
            rationale="Auto-mode: proceeding with default answer",
            timestamp=datetime.now(UTC).isoformat(),
        )
        logger.info("auto_decision: %s", entry)
        return answer

    async def _escalate_to_human(self, question: str) -> str:
        query = HumanQuery(
            question=question,
            context={},
            timestamp=datetime.now(UTC).isoformat(),
        )
        await self._human_out.put(query)
        try:
            answer = await asyncio.wait_for(
                self._human_in.get(),
                timeout=self._human_timeout,
            )
            return str(answer)
        except asyncio.TimeoutError:
            logger.warning("Human escalation timed out — using auto fallback: proceed")
            return "proceed"
```

### Pattern 2: Cancel and Reassign (COMM-05)

**What:** To cancel a running sub-agent and reassign it with corrected instructions:
1. Call `client.interrupt()` — sends `{"subtype": "interrupt"}` control request; the sub-agent aborts its current turn
2. Exit the `async with ACPClient` block — closes the session completely
3. Write `TaskStatus.FAILED` to state (or mark for reassignment)
4. Spawn a new `_run_agent_loop()` for the same task with updated instructions in the `TaskSpec.description`

**Key SDK fact:** `interrupt()` is a control-protocol request (`_send_control_request({"subtype": "interrupt"})`), not a subprocess kill. The sub-agent process stays alive after interrupt — it can receive a new `send()` in the same session. However, for **cancel and reassign** (COMM-05), the clean pattern is interrupt + close the session + start a new session. This prevents contamination of the old context.

**When to use:** When the orchestrator determines (via review, human instruction, or error detection) that a sub-agent is on the wrong track and needs a fresh start with corrected instructions.

**Example:**
```python
# Source: ACPClient.interrupt() verified in conductor/acp/client.py (Phase 3)
# ClaudeSDKClient.interrupt() verified in claude_agent_sdk/client.py
async def cancel_agent(self, agent_id: str, corrected_spec: TaskSpec) -> None:
    """Cancel a running sub-agent and schedule reassignment with corrected instructions."""
    # 1. Find the active asyncio.Task for agent_id and cancel it
    # The task is already inside `async with ACPClient`, so cancellation propagates
    # to __aexit__ which calls disconnect()
    if agent_id in self._active_tasks:
        task = self._active_tasks[agent_id]
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        del self._active_tasks[agent_id]

    # 2. Write FAILED status to state
    await asyncio.to_thread(
        self._state.mutate,
        self._make_fail_task_fn(corrected_spec.id, reason="cancelled_for_reassignment"),
    )

    # 3. Spawn new loop with corrected spec
    sem = self._semaphore  # reuse existing semaphore
    new_task = asyncio.create_task(self._run_agent_loop(corrected_spec, sem))
    self._active_tasks[corrected_spec.id] = new_task
```

**IMPORTANT:** `asyncio.Task.cancel()` propagates `CancelledError` into the coroutine. Since `_run_agent_loop` uses `async with ACPClient`, the `__aexit__` is called even on cancellation, which calls `disconnect()`. The SDK session is cleaned up correctly.

### Pattern 3: Mid-Stream Guidance Injection (COMM-06)

**What:** Send a guidance message to a running sub-agent without stopping it. The sub-agent is currently in the `stream_response()` loop. The orchestrator calls `client.send(guidance)` on the same `ACPClient` instance from outside the streaming loop — this writes a user-turn message to the transport. The sub-agent will see it on its next response cycle.

**When to use:** When the orchestrator detects a sub-agent is going in the right direction but needs a nudge (e.g., "remember to add error handling to the function you're writing").

**How it works (verified in SDK source):**
- `ACPClient.send()` → `self._sdk_client.query(prompt)` → `transport.write(json_message + "\n")`
- This is a fire-and-send — it writes to the transport immediately, regardless of whether `receive_response()` is currently consuming messages
- The sub-agent process reads from stdin which is the transport write side — it will see the message when it next reads

**Concurrency note:** The `stream_response()` loop runs inside an `asyncio.Task`. The `send()` call runs in a different async context (e.g., the orchestrator's main coroutine or an intervention handler coroutine). Both are in the same event loop, so there is no true parallelism — the `send()` writes to the transport buffer; the streaming task processes responses. This is safe: `asyncio.Queue`/transport writes are not concurrent in Python's cooperative multitasking model.

**Example:**
```python
# Source: ACPClient.send() -> ClaudeSDKClient.query() verified in claude_agent_sdk/client.py
# transport.write() is the underlying primitive — safe to call while receive_response() runs
async def inject_guidance(self, agent_id: str, guidance: str) -> None:
    """Send a guidance message to a running sub-agent without stopping it."""
    if agent_id not in self._active_clients:
        raise EscalationError(f"No active client for agent {agent_id!r}")
    client = self._active_clients[agent_id]
    await client.send(guidance)
    # The sub-agent will incorporate this on its next response cycle
    # No need to restart stream_response() — it's still running
```

**Required orchestrator change:** `self._active_clients: dict[str, ACPClient]` must be populated when a session opens and cleared when it closes. Currently the orchestrator creates `ACPClient` as a local variable inside `_run_agent_loop` — it must be registered on `self` for external access.

### Pattern 4: Pause and Human Decision (COMM-07)

**What:** Pause a sub-agent mid-execution, present a decision to the human, then resume based on the answer.

**Pause mechanism:**
1. `await client.interrupt()` — aborts the sub-agent's current turn
2. Write the decision question to `human_out` queue and block on `human_in` queue
3. When the human answers, call `await client.send(answer)` to deliver the decision
4. Re-enter `stream_response()` to resume

**Key constraint:** The `async with ACPClient` block must NOT be exited during pause. The session stays open. After interrupt, the sub-agent process waits for the next user message.

**Verified SDK behavior:** After `interrupt()` sends the control request, the sub-agent receives an abort signal for its current tool chain. `receive_response()` may yield a `ResultMessage` with `stop_reason="interrupted"` or may yield additional messages before terminating. The orchestrator must drain `stream_response()` until it stops (when it yields a `ResultMessage` or the stream ends) before re-entering it.

**Example:**
```python
# Source: ClaudeSDKClient.interrupt() -> Query.interrupt() -> _send_control_request({"subtype": "interrupt"})
# Verified in claude_agent_sdk/_internal/query.py
async def pause_and_decide(
    self,
    agent_id: str,
    question: str,
    human_out: asyncio.Queue,
    human_in: asyncio.Queue,
    timeout: float = 120.0,
) -> None:
    """Pause a sub-agent, get human decision, resume with decision context."""
    if agent_id not in self._active_clients:
        raise EscalationError(f"No active client for agent {agent_id!r}")
    client = self._active_clients[agent_id]

    # 1. Interrupt the current turn
    await client.interrupt()

    # 2. Drain the response stream until it terminates post-interrupt
    # The stream will end with a ResultMessage (stop_reason="interrupted") or error
    async for _msg in client.stream_response():
        pass  # drain until stream ends

    # 3. Escalate to human
    await human_out.put(HumanQuery(
        question=question,
        context={"agent_id": agent_id},
        timestamp=datetime.now(UTC).isoformat(),
    ))
    try:
        decision = await asyncio.wait_for(human_in.get(), timeout=timeout)
    except asyncio.TimeoutError:
        decision = "proceed with best judgment"

    # 4. Deliver decision and resume
    await client.send(f"Human decision: {decision}. Continue your work with this guidance.")
    # The orchestrator's existing stream_response() loop needs to re-enter
    # This is done by setting an event/flag that the _run_agent_loop() task checks
```

**Implementation note for pause/resume:** `_run_agent_loop()` must be structured so that after `stream_response()` exhausts, it checks a `pause_event: asyncio.Event` before proceeding to the review step. If the event is set, it waits for a resume signal. `pause_and_decide()` sets the pause event, delivers the decision via `send()`, then sets a resume event.

### Pattern 5: Orchestrator State for Active Sessions (Required by COMM-05, COMM-06, COMM-07)

**What:** The current `_run_agent_loop()` holds `ACPClient` as a local variable — it is invisible from outside. Intervention requires the orchestrator to reach into a running agent's session. This requires registering active sessions in a shared dict on `self`.

**Design:**
```python
class Orchestrator:
    def __init__(self, ...) -> None:
        ...
        self._active_clients: dict[str, ACPClient] = {}   # agent_id -> client
        self._active_tasks: dict[str, asyncio.Task] = {}  # agent_id -> asyncio.Task
        self._semaphore: asyncio.Semaphore | None = None  # set in run()
```

**Thread safety:** All access is within the same asyncio event loop — no thread safety needed. Mutations happen when `_run_agent_loop()` starts/ends, which is in a coroutine scheduled by the event loop.

### Anti-Patterns to Avoid

- **Using `task.cancel()` for guidance injection:** Cancelling the task stops the agent session. For mid-stream guidance (COMM-06), use `client.send()` — no cancellation needed.
- **Exiting `async with ACPClient` before resume (COMM-07):** Once `__aexit__` is called, the SDK client disconnects. Pause must keep the `async with` block alive.
- **Calling `stream_response()` without prior `interrupt()` for pause:** Calling `stream_response()` on an already-streaming session without draining the previous stream first will cause the iterator to hang waiting for messages that the prior `stream_response()` already consumed. Always drain post-interrupt before re-entering.
- **Blocking `asyncio.Queue.get()` without `asyncio.wait_for`:** If the human never answers, the sub-agent session hangs. Always wrap with `asyncio.wait_for` and provide a fallback answer on `asyncio.TimeoutError`.
- **Registering `ACPClient` on `self` without cleanup on error:** If `_run_agent_loop` raises, the `active_clients` entry must still be deleted. Use `try/finally`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sub-agent interrupt | Custom subprocess signal (SIGINT, SIGTERM) | `ACPClient.interrupt()` → SDK control protocol `{"subtype": "interrupt"}` | SDK interrupt is a clean protocol-level signal; SIGTERM kills the process and loses state. Already implemented in Phase 3. |
| User-turn injection | Custom JSONL framing + transport write | `ACPClient.send(text)` → `ClaudeSDKClient.query(text)` → `transport.write(...)` | Already implemented and tested. Building raw JSONL framing risks protocol errors. |
| Escalation queue | File-based polling or socket | `asyncio.Queue` (in-process) | Zero latency, no I/O setup, trivially testable with `AsyncMock`. CLI (Phase 8) drains the same queue — same process. |
| Confidence scoring | LLM call per question | Keyword set lookup (`_LOW_CONFIDENCE_KEYWORDS`) | Questions arrive in the permission callback hot path — LLM calls add 500-2000ms latency per permission event. Conservative keyword matching is fast and sufficient for v1. |
| Mode flag storage | Config file re-read per decision | Constructor argument (`mode: str`) on `EscalationRouter` | Mode is set at startup from CLI args, doesn't change at runtime. No need for dynamic config. |

**Key insight:** All intervention primitives (interrupt, send, inject) are already in `ACPClient` from Phase 3. Phase 6 is primarily about **orchestrating** those primitives in the right sequence with the right state management — not adding new SDK capabilities.

---

## Common Pitfalls

### Pitfall 1: Calling `stream_response()` Concurrently from Two Coroutines

**What goes wrong:** `inject_guidance()` (COMM-06) is implemented by creating a second `stream_response()` iterator on the same client while the agent loop is already iterating. Two concurrent `receive_messages()` calls on the same `_message_receive` memory object stream will cause messages to be split between the two iterators — the agent loop misses events.

**Why it happens:** `inject_guidance()` is confused with receiving new messages. Guidance injection is only a `send()` — no new `stream_response()` needed.

**How to avoid:** `inject_guidance()` calls `client.send(text)` only. The existing `stream_response()` in `_run_agent_loop()` will deliver the sub-agent's response to the guidance naturally — no second iterator.

**Warning signs:** Missing `ResultMessage` in agent loop; `monitor.result_text` remaining `None`; stream ending prematurely.

### Pitfall 2: Post-Interrupt `stream_response()` Hanging Indefinitely

**What goes wrong:** After `interrupt()`, the orchestrator calls `stream_response()` again to drain the stream before sending the pause decision. But the interrupted stream has already ended (the SDK yielded `ResultMessage` with `stop_reason="interrupted"`), and the second `stream_response()` call returns immediately (empty). The orchestrator then calls `send(decision)` but no third `stream_response()` call follows — the agent never processes the decision.

**Why it happens:** Each `stream_response()` call terminates after one `ResultMessage`. The sequence is: (1) interrupted stream ends → `ResultMessage` yielded → stream terminates; (2) `send(decision)` delivers the decision; (3) new `stream_response()` must be called to get the agent's response.

**How to avoid:** After pause/interrupt, the flow is always: `interrupt()` → drain `stream_response()` → `send(decision)` → new `stream_response()` call (re-enter review loop).

**Warning signs:** Sub-agent doesn't process the decision; orchestrator exits the revision loop prematurely; task marked COMPLETED without processing the pause decision.

### Pitfall 3: `asyncio.Task.cancel()` Inside the `async with ACPClient` Block Skips `__aexit__`

**What goes wrong:** The orchestrator calls `asyncio.Task.cancel()` on `_run_agent_loop()`. Python's asyncio scheduler delivers a `CancelledError` at the next `await` inside the task. If the task is currently inside `async with ACPClient`, the `__aexit__` IS called (Python's context managers handle cancellation). However, if the task is at a bare `await asyncio.to_thread(...)` that cannot be cancelled (blocking thread), the cancellation is deferred until the thread returns. This is not a data loss issue but can cause delays.

**How to avoid:** Ensure `asyncio.to_thread()` calls inside `_run_agent_loop` are short (millisecond-scale state reads/writes). Do not use `asyncio.to_thread()` for long-running I/O inside the loop. State manager mutations are fast — this is not a practical concern.

**Warning signs:** `cancel()` called but task doesn't stop for several seconds; orchestrator appears to hang after cancel command.

### Pitfall 4: Active Client Registry Not Cleaned Up on Exception

**What goes wrong:** `_run_agent_loop()` raises an unexpected exception (e.g., `ReviewError`, `SessionError`). The entry in `self._active_clients[agent_id]` is never deleted. A subsequent `inject_guidance()` call finds the stale entry and attempts `client.send()` on a closed session → `SessionError("Session is closed")`.

**Why it happens:** Dictionary cleanup only in the happy path.

**How to avoid:** Wrap the `async with ACPClient` block in `try/finally`:
```python
async with ACPClient(...) as client:
    self._active_clients[agent_id] = client
    try:
        ...  # revision loop
    finally:
        del self._active_clients[agent_id]
```

**Warning signs:** `SessionError: Session is closed` raised on `inject_guidance()` after a prior agent failure.

### Pitfall 5: Human Escalation Queue Deadlock in `--auto` Mode

**What goes wrong:** Router is configured for `--auto` but `human_out`/`human_in` queues are provided. A bug accidentally causes `_escalate_to_human()` to be called. No process is draining `human_out`, so `human_in.get()` blocks. `asyncio.wait_for` fires after `human_timeout` and falls back to "proceed" — but the test assertion expected no escalation, causing a flaky test.

**How to avoid:** In `--auto` mode, `EscalationRouter.resolve()` must NEVER write to `human_out`, regardless of confidence. The mode check is the outer guard, not the confidence check. Only interactive mode escalates.

**Warning signs:** Flaky tests that occasionally time out in `--auto` mode tests; `asyncio.TimeoutError` raised in `resolve()` during `--auto` mode tests.

### Pitfall 6: `interrupt()` Without Draining May Corrupt Next `stream_response()`

**What goes wrong:** Orchestrator calls `interrupt()` and immediately calls `send(new_instructions)` without draining the remaining messages from the interrupted stream. The `_message_receive` queue still has the interrupted session's messages in the buffer. The new `stream_response()` will yield these stale messages before the new response arrives.

**Why it happens:** SDK `_message_receive` is a buffered `anyio.create_memory_object_stream` with `max_buffer_size=100`. Interrupt does not flush this buffer.

**How to avoid:** Always drain `stream_response()` after `interrupt()`:
```python
await client.interrupt()
async for _ in client.stream_response():  # drain stale messages
    pass
# Now safe to send and re-stream
await client.send(new_instructions)
async for message in client.stream_response():  # fresh response
    monitor.process(message)
```

**Warning signs:** `StreamMonitor.result_text` set to the wrong value (the interrupted session's partial result); review failing on stale content.

---

## Code Examples

Verified patterns from official sources:

### EscalationRouter Wiring into PermissionHandler

```python
# Source: existing PermissionHandler pattern (conductor/acp/permission.py) — Phase 3
from conductor.acp.permission import PermissionHandler
from conductor.orchestrator.escalation import EscalationRouter
import asyncio

human_out: asyncio.Queue = asyncio.Queue()
human_in: asyncio.Queue = asyncio.Queue()

router = EscalationRouter(
    mode="interactive",        # or "auto"
    human_out=human_out,
    human_in=human_in,
    human_timeout=120.0,
)

# Wire the router's resolve method as the PermissionHandler's answer_fn
handler = PermissionHandler(
    timeout=30.0,
    answer_fn=router.resolve,  # resolver returns str; PermissionHandler wraps in PermissionResultAllow
)
```

**Note:** `PermissionHandler.answer_fn` currently returns `PermissionResultAllow | PermissionResultDeny`. The router returns `str`. The handler's `_answer_fn` type signature must be updated, OR `EscalationRouter.resolve()` returns `PermissionResultAllow` directly. The latter keeps `PermissionHandler` unmodified — preferred.

```python
# Revised signature: resolve() returns PermissionResultAllow directly
async def resolve(self, input_data: dict) -> PermissionResultAllow:
    answer = await self._get_answer(input_data)
    questions: list[dict] = input_data.get("questions", [])
    # Build answers dict matching PermissionHandler._default_answer_with_state pattern
    answers = {str(i): answer for i in range(len(questions))}
    return PermissionResultAllow(updated_input={**input_data, "answers": answers})
```

### Cancel + Reassign Sequence

```python
# Source: ACPClient.interrupt() from conductor/acp/client.py (Phase 3)
# asyncio.Task.cancel() from stdlib asyncio docs
async def cancel_and_reassign(self, agent_id: str, updated_spec: TaskSpec) -> None:
    """Cancel a running agent and spawn fresh session with corrected instructions."""
    if agent_id in self._active_tasks:
        task = self._active_tasks.pop(agent_id)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass  # Expected — task was cancelled

    # Write CANCELLED status to state
    await asyncio.to_thread(
        self._state.mutate,
        lambda state: next(
            (setattr(t, "status", "failed") for t in state.tasks if t.id == updated_spec.id),
            None,
        ),
    )

    # Spawn new loop with corrected spec
    assert self._semaphore is not None
    new_task = asyncio.create_task(
        self._run_agent_loop(updated_spec, self._semaphore)
    )
    self._active_tasks[updated_spec.id] = new_task
```

### Mid-Stream Guidance Injection

```python
# Source: ACPClient.send() -> ClaudeSDKClient.query() -> transport.write()
# Verified in claude_agent_sdk/client.py and _internal/query.py
async def inject_guidance(self, agent_id: str, guidance: str) -> None:
    """Inject a guidance message to a running sub-agent without stopping it."""
    client = self._active_clients.get(agent_id)
    if client is None:
        raise EscalationError(f"No active session for agent {agent_id!r}")
    # send() writes a user-turn message to the transport buffer
    # The agent will receive it on its next response cycle
    await client.send(guidance)
    # No need to re-enter stream_response() — the existing loop handles it
```

### Pause + Resume Flow

```python
# Source: interrupt() control protocol from claude_agent_sdk/_internal/query.py
# asyncio.wait_for from stdlib — same pattern as PermissionHandler (Phase 3)
async def pause_for_human_decision(
    self,
    agent_id: str,
    question: str,
    human_out: asyncio.Queue,
    human_in: asyncio.Queue,
    timeout: float = 120.0,
) -> None:
    """Pause agent, get human decision, resume with decision."""
    client = self._active_clients.get(agent_id)
    if client is None:
        raise EscalationError(f"No active session for agent {agent_id!r}")

    # 1. Signal pause to _run_agent_loop so it waits before review step
    self._pause_events[agent_id] = asyncio.Event()
    resume_event = asyncio.Event()
    self._resume_events[agent_id] = resume_event

    # 2. Interrupt the current turn
    await client.interrupt()
    # _run_agent_loop's stream_response() will terminate after interrupt
    # The loop detects the pause event and waits

    # 3. Escalate to human
    await human_out.put({"agent_id": agent_id, "question": question})
    try:
        decision = await asyncio.wait_for(human_in.get(), timeout=timeout)
    except asyncio.TimeoutError:
        decision = "proceed with best judgment"

    # 4. Resume — send decision to the session and signal the loop to continue
    await client.send(f"Guidance: {decision}")
    resume_event.set()
    del self._pause_events[agent_id]
    del self._resume_events[agent_id]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single `answer_fn` (always auto) | `EscalationRouter` with mode switch (auto vs interactive) | Phase 6 | Human questions in interactive mode reach the CLI; auto mode logs decisions |
| No intervention API on `Orchestrator` | `cancel_agent()`, `inject_guidance()`, `pause_and_decide()` methods | Phase 6 | Orchestrator becomes externally controllable (CLI Phase 8 will call these) |
| `ACPClient` as local variable in `_run_agent_loop` | Registered in `self._active_clients` dict | Phase 6 | Enables external intervention without exposing SDK internals |
| No human escalation channel | `asyncio.Queue` in/out pair | Phase 6 | Provides the in-process IPC mechanism that CLI (Phase 8) will plug into |

**Deprecated/outdated patterns:**
- `PermissionHandler` with a fixed `_default_answer_with_state` for all questions — Phase 6 replaces the `answer_fn` with `EscalationRouter.resolve` for context-aware routing.

---

## Open Questions

1. **`stream_response()` behavior after `interrupt()` — does it always yield a `ResultMessage`?**
   - What we know: `interrupt()` sends `{"subtype": "interrupt"}` via the control protocol. The SDK's `receive_response()` iterates until a `ResultMessage` is yielded. From `query.py`, the `_read_messages` loop sends `{"type": "end"}` when the transport closes; the SDK's stream ends on `end`.
   - What's unclear: Does the CLI always emit a `ResultMessage` when interrupted, or does the transport close silently? If the transport closes without `ResultMessage`, `stream_response()` terminates (because `_read_messages` sends `end` in its `finally` block), but `monitor.result_text` will be `None`.
   - Recommendation: Drain `stream_response()` post-interrupt by iterating to exhaustion (not looking for `ResultMessage` specifically). The iterator terminates naturally regardless — either via `ResultMessage` or via the `end` sentinel. This is safe.

2. **Concurrent `send()` and `stream_response()` — is there a race?**
   - What we know: Python asyncio is cooperative. `send()` calls `transport.write()` which is `async def`. It awaits the write. The `stream_response()` loop in `_run_agent_loop` is a concurrent `asyncio.Task`. Both run in the same event loop — they cannot truly run simultaneously.
   - What's unclear: If `transport.write()` inside `send()` and the read loop in `stream_response()` execute interleaved, is the protocol framing preserved?
   - Recommendation: This is safe. `transport.write()` writes a complete JSON line atomically (no partial writes between the two coroutines). JSONL framing is per-line, not per-byte. The SDK was designed for this bidirectional use case — `ClaudeSDKClient.query()` is documented as callable "at any time" during a session.

3. **`asyncio.Task.cancel()` vs `client.interrupt()` for cancel/reassign**
   - What we know: `client.interrupt()` is a protocol-level interrupt; `task.cancel()` is Python's asyncio cancellation. For cancel+reassign (COMM-05), we want to stop the agent and close the session. Both mechanisms achieve this.
   - What's unclear: If we call `task.cancel()` on `_run_agent_loop`, the `CancelledError` propagates through the `async with ACPClient` block — `__aexit__` calls `disconnect()`. But we never called `interrupt()` first. Does the sub-agent process hang waiting for a new message?
   - Recommendation: Call `client.interrupt()` then `task.cancel()` for cancel+reassign. The interrupt signal tells the sub-agent process to abort its current work cleanly, then `task.cancel()` tears down the Python coroutine. Interrupt without task cancel works too, but the task would continue to the review step — undesirable for cancel+reassign.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio >=0.23 |
| Config file | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` (asyncio_mode = "auto" already configured) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_escalation.py tests/test_orchestrator.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COMM-03 | `EscalationRouter` in auto mode answers all questions autonomously without touching human queues | unit | `pytest tests/test_escalation.py::TestComm03AutoMode -x` | ❌ Wave 0 |
| COMM-03 | Auto-mode decisions are logged via `logging` with question, answer, confidence, rationale | unit (caplog) | `pytest tests/test_escalation.py::TestComm03DecisionLog -x` | ❌ Wave 0 |
| COMM-03 | Auto-mode with low-confidence keyword still answers without escalating | unit | `pytest tests/test_escalation.py::TestComm03LowConfidenceNoEscalate -x` | ❌ Wave 0 |
| COMM-04 | Interactive mode with high-confidence question answers autonomously (no human queue write) | unit | `pytest tests/test_escalation.py::TestComm04HighConfidenceAuto -x` | ❌ Wave 0 |
| COMM-04 | Interactive mode with low-confidence question writes to `human_out` and awaits `human_in` | unit (asyncio.Queue) | `pytest tests/test_escalation.py::TestComm04LowConfidenceEscalate -x` | ❌ Wave 0 |
| COMM-04 | Interactive mode escalation timeout falls back to "proceed" without raising | unit | `pytest tests/test_escalation.py::TestComm04EscalationTimeout -x` | ❌ Wave 0 |
| COMM-05 | `cancel_and_reassign()` cancels the active asyncio.Task for agent_id | unit (mock task) | `pytest tests/test_orchestrator.py::TestComm05CancelTask -x` | ❌ Wave 0 |
| COMM-05 | After cancel, `_active_clients` no longer contains the cancelled agent_id | unit | `pytest tests/test_orchestrator.py::TestComm05ClientCleanup -x` | ❌ Wave 0 |
| COMM-05 | After cancel, a new `_run_agent_loop` is spawned for the corrected spec | unit (mock loop) | `pytest tests/test_orchestrator.py::TestComm05ReassignSpawns -x` | ❌ Wave 0 |
| COMM-06 | `inject_guidance()` calls `client.send()` on the active client without interrupting | unit (mock ACPClient) | `pytest tests/test_orchestrator.py::TestComm06InjectSend -x` | ❌ Wave 0 |
| COMM-06 | `inject_guidance()` raises `EscalationError` if agent_id not in `_active_clients` | unit | `pytest tests/test_orchestrator.py::TestComm06UnknownAgent -x` | ❌ Wave 0 |
| COMM-07 | `pause_for_human_decision()` calls `interrupt()` then drains stream before sending decision | unit (mock client + queue) | `pytest tests/test_orchestrator.py::TestComm07PauseInterrupt -x` | ❌ Wave 0 |
| COMM-07 | Pause delivers human decision to agent via `send()` and signals resume | unit | `pytest tests/test_orchestrator.py::TestComm07ResumeAfterDecision -x` | ❌ Wave 0 |
| COMM-07 | Pause timeout falls back to default decision without raising | unit | `pytest tests/test_orchestrator.py::TestComm07PauseTimeout -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_escalation.py tests/test_orchestrator.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_escalation.py` — covers COMM-03 and COMM-04: EscalationRouter auto/interactive mode, confidence routing, timeout fallback
- [ ] `src/conductor/orchestrator/escalation.py` — `HumanQuery` dataclass, `DecisionLog` dataclass, `_LOW_CONFIDENCE_KEYWORDS`, `_is_low_confidence()`, `EscalationRouter` class
- [ ] Extend `src/conductor/orchestrator/errors.py` — add `EscalationError`, `InterruptError`
- [ ] Extend `src/conductor/orchestrator/orchestrator.py` — add `self._active_clients`, `self._active_tasks`, `self._semaphore`, `self._pause_events`, `self._resume_events`; add `cancel_and_reassign()`, `inject_guidance()`, `pause_for_human_decision()` methods; register/deregister client in `_run_agent_loop` via `try/finally`

*(Existing `tests/test_orchestrator.py` will be extended with new test classes for COMM-05, COMM-06, COMM-07. No new test infrastructure needed — existing mock patterns apply.)*

---

## Sources

### Primary (HIGH confidence)

- `/home/huypham/code/digest/claude-auto/.venv/lib/python3.13/site-packages/claude_agent_sdk/client.py` — Verified: `interrupt()` calls `self._query.interrupt()`; `query(prompt)` (the `send()` primitive) writes a JSON user-turn message via `transport.write()`; `receive_response()` yields until `ResultMessage`; `disconnect()` called on `__aexit__`
- `/home/huypham/code/digest/claude-auto/.venv/lib/python3.13/site-packages/claude_agent_sdk/_internal/query.py` — Verified: `interrupt()` sends `{"subtype": "interrupt"}` control request; `stream_input()` + `_read_messages()` run as concurrent anyio tasks; `_message_receive` is a buffered `anyio.create_memory_object_stream`; `_read_messages` sends `{"type": "end"}` in `finally` ensuring stream always terminates
- `/home/huypham/code/digest/claude-auto/.venv/lib/python3.13/site-packages/claude_agent_sdk/types.py` — Verified: `ResultMessage.stop_reason` field exists (can be `"interrupted"`); `PermissionResultAllow.updated_input` pattern; `HumanQuery` design based on `AskUserQuestion` structure in `SDKControlPermissionRequest`
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/acp/client.py` — Verified: `interrupt()` already implemented and delegates to `self._sdk_client.interrupt()`; `send()` already implemented; `_closed` flag guards post-exit operations
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/acp/permission.py` — Verified: `answer_fn` callback pattern; `asyncio.wait_for` timeout guard; `PermissionResultAllow` construction pattern
- `/home/huypham/code/digest/claude-auto/packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — Verified: `_run_agent_loop()` structure; `self._active_clients` is NOT yet present (Phase 6 adds it); `async with ACPClient` pattern; `asyncio.Task` management via `asyncio.wait(FIRST_COMPLETED)`

### Secondary (MEDIUM confidence)

- Phase 3 RESEARCH.md (`.planning/phases/03-acp-communication-layer/03-RESEARCH.md`) — Pre-verified SDK patterns for `can_use_tool`, timeout handling, `AskUserQuestion` routing; all directly applicable to COMM-03/04

### Tertiary (LOW confidence)

- None — all critical claims verified against installed SDK source code and existing project code

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all primitives verified in installed `claude_agent_sdk` 0.1.48 source
- Architecture: HIGH — `interrupt()`, `send()`, `stream_response()` semantics verified; `asyncio.Task.cancel()` behavior is stdlib-documented; `asyncio.Queue` pattern identical to Phase 3's permission timeout
- Pitfalls: HIGH — concurrent stream corruption derived from `anyio.create_memory_object_stream` behavior in `query.py`; drain-after-interrupt requirement derived from `receive_response()` termination logic in `client.py`; cleanup-in-finally requirement derived from existing `ACPClient._closed` guard pattern

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (SDK 0.1.48 stable; re-verify `interrupt()` control request semantics if SDK minor version changes)
