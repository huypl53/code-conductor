# Phase 16 Research: Fix Agent Status Lifecycle

**Question:** What do I need to know to PLAN this phase well?

## Problem Statement

The milestone audit identified two missing status mutations in the orchestrator:

1. **AgentRecord.status never transitions to DONE** — after `_run_agent_loop` completes, `_make_complete_task_fn` sets `task.status = COMPLETED` but never touches `agent.status`. Agents permanently show WORKING in the dashboard.

2. **AgentRecord.status never transitions to WAITING** — `pause_for_human_decision` interrupts the agent and waits for human input, but never sets `agent.status = AgentStatus.WAITING` in state. The dashboard's `classify_delta` correctly emits `INTERVENTION_NEEDED` when it sees a WAITING agent, but the status is never written.

## Affected Requirements

- **DASH-01** (partial): Dashboard shows agent status summary, but status is always WORKING
- **DASH-04** (partial): intervention_needed notification never fires because WAITING is never set in state

## Codebase Analysis

### Status Enum (already exists)

File: `packages/conductor-core/src/conductor/state/models.py` (lines 25-29)

```python
class AgentStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    DONE = "done"
```

The enum values already exist. The problem is purely that no code writes WAITING or DONE to state.

### Missing Mutation 1: DONE on task completion

File: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py`

The `_make_complete_task_fn` static method (lines 701-718) only sets `task.status = COMPLETED`. It does NOT set `agent.status = DONE`. The fix is to add an agent status mutation in the same state mutate call.

Current code:
```python
@staticmethod
def _make_complete_task_fn(
    task_id: str,
    review_status: ReviewStatus = ReviewStatus.APPROVED,
    revision_count: int = 0,
) -> Callable[[ConductorState], None]:
    def _complete(state: ConductorState) -> None:
        for task in state.tasks:
            if task.id == task_id:
                task.status = TaskStatus.COMPLETED
                task.review_status = review_status
                task.revision_count = revision_count
                task.updated_at = datetime.now(UTC)
                break
    return _complete
```

**Issue:** This function doesn't know the agent_id. The caller (`_run_agent_loop`) has `agent_id` in scope. Two options:
- **Option A:** Add `agent_id` parameter to `_make_complete_task_fn` and set agent status inside
- **Option B:** Create a separate `_make_set_agent_status_fn` and call it after `_make_complete_task_fn`

**Recommendation: Option A** — single atomic state mutation is better than two sequential mutations. The function already takes task_id; adding agent_id is consistent.

### Missing Mutation 2: WAITING on pause

File: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py`

The `pause_for_human_decision` method (lines 449-499) interrupts the agent, pushes question to human_out, waits for response, then resumes — but never touches AgentRecord.status.

**Fix:** Set `AgentStatus.WAITING` before pushing to human_out, and restore to `AgentStatus.WORKING` after receiving the response and resuming.

### Event Pipeline (already wired)

File: `packages/conductor-core/src/conductor/dashboard/events.py`

`classify_delta` already handles WAITING -> INTERVENTION_NEEDED (lines 115-122):
```python
if agent.status == "waiting":
    events.append(DeltaEvent(
        type=EventType.INTERVENTION_NEEDED,
        agent_id=agent.id,
        is_smart_notification=True,
    ))
```

And WORKING -> DONE produces AGENT_STATUS_CHANGED (tested in `test_dashboard_events.py` line 158-165).

**No changes needed in events.py or the dashboard frontend.** The pipeline is fully wired — it just needs the orchestrator to write the status values to state.

### Dashboard Frontend (already wired)

File: `packages/conductor-dashboard/src/components/NotificationProvider.tsx`

The `useSmartNotifications` hook already handles `intervention_needed` events (lines 52-54):
```tsx
} else if (event.type === "intervention_needed") {
    toast.warning(`Agent ${event.agent_id} needs intervention`, { duration: Infinity });
}
```

File: `packages/conductor-dashboard/src/components/AgentCard.tsx`

StatusBadge already renders all four AgentStatus values (idle, working, waiting, done).

**No frontend changes needed.**

### TypeScript Types (already correct)

File: `packages/conductor-dashboard/src/types/conductor.ts`

`AgentStatus` type already includes "waiting" and "done".

## Implementation Strategy

### Change 1: Add agent DONE mutation to _make_complete_task_fn

- Add `agent_id: str` parameter
- Inside the mutate function, find the agent and set `status = AgentStatus.DONE`
- Update the single caller in `_run_agent_loop` (line 623-630) to pass `agent_id`

### Change 2: Add WAITING/WORKING mutations to pause_for_human_decision

- Before `await human_out.put(query)`: mutate state to set agent status = WAITING
- After `await client.send(...)` (resume): mutate state to set agent status = WORKING
- Both mutations use `self._state.mutate` via `asyncio.to_thread`

### Change 3: Tests

- Update existing `test_make_complete_task_fn` tests to verify agent status = DONE
- Add test for `pause_for_human_decision` setting WAITING then WORKING
- Existing `test_dashboard_events.py` tests already validate the event pipeline

## Files to Modify

| File | Change |
|------|--------|
| `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` | Add agent_id to _make_complete_task_fn, add WAITING/WORKING mutations to pause_for_human_decision |
| `packages/conductor-core/tests/test_orchestrator.py` | Add tests for DONE and WAITING status mutations |

## Risk Assessment

- **Low risk:** All changes are in the orchestrator — no model changes, no event changes, no frontend changes
- **The enum values already exist** — this is purely about writing them to state at the right time
- **Existing event pipeline tests pass** — `test_dashboard_events.py` already validates WAITING -> INTERVENTION_NEEDED and WORKING -> DONE -> AGENT_STATUS_CHANGED
- **Backward compatible:** No new fields, no schema changes

## Validation Architecture

### Test Strategy

1. **Unit test: _make_complete_task_fn sets agent DONE** — create state with agent WORKING, call mutate fn, assert agent.status == "done"
2. **Unit test: pause_for_human_decision sets WAITING** — mock StateManager.mutate, verify WAITING mutation called before human_out.put
3. **Unit test: pause_for_human_decision restores WORKING** — verify WORKING mutation called after client.send
4. **Integration: full _run_agent_loop sets DONE on completion** — existing orchestrator integration tests can be extended

### Existing Test Coverage

- `test_dashboard_events.py::test_classify_delta_agent_waiting_is_smart_notification` — validates event pipeline for WAITING
- `test_dashboard_events.py::test_classify_delta_agent_done_is_not_smart_notification` — validates event pipeline for DONE
- `test_orchestrator.py` — existing orchestrator tests provide patterns for mocking

### Commands

- Quick: `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_orchestrator.py -v -k "status"`
- Full: `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q`
