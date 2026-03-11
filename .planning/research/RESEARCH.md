# Phase 23: Resume Robustness - Research

**Researched:** 2026-03-11
**Domain:** Python asyncio orchestration, pytest async testing
**Confidence:** HIGH (code examined directly, tests run locally)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| RESM-01 | When `review_only` review fails with an exception, the orchestrator falls back to best-effort approval instead of crashing | Code already has the `except Exception` handler in `_run_agent_loop`; tests for this path already exist (`test_review_only_approves_on_review_error`). Need additional edge-case tests for non-`ReviewError` exceptions, log message verification, and state mutation confirming APPROVED status. |
| RESM-02 | The resume spawn loop correctly handles completed tasks from `get_ready()`, retrieves task exceptions, and uses `marked_done` flag to avoid premature loop exit | Spawn loop is fully implemented with `marked_done` flag and `fut.exception()` retrieval. Existing tests (`TestResumeScheduler`) cover the happy-path. Missing: tests for exception retrieval on failed tasks, the `marked_done` continuation guard, and all-completed-first-round exit path. |
</phase_requirements>

## Summary

Phase 23 is a **test-and-harden** phase for two already-partially-implemented robustness features in `orchestrator.py`. Both RESM-01 and RESM-02 have working production code; the gap is in test coverage for edge cases.

**RESM-01** (`review_only` exception fallback): The `else` branch of `_run_agent_loop` at line 700-714 wraps `review_output` in `except Exception` and falls back to `ReviewVerdict(approved=True)` on any exception. One test exists (`test_review_only_approves_on_review_error`) that covers `ReviewError`, but additional exception types (`ConnectionError`, `TimeoutError`, `RuntimeError`) are not tested. The warning log message is not asserted in tests. The resulting state mutation (APPROVED + COMPLETED) after the fallback is not explicitly verified.

**RESM-02** (spawn loop `marked_done` + exception retrieval): The `resume()` spawn loop at lines 382-431 already has both mechanisms: `marked_done = False` / `if not pending and marked_done: continue` and `fut.exception()` retrieval inside the done-future processing loop. The `TestResumeScheduler` tests cover the basic workflows but miss: (a) the `marked_done` short-circuit behavior when all `get_ready()` IDs are completed, (b) proper exception retrieval/logging without re-raising, (c) the loop guard that prevents premature `break` when `pending` is empty only because completed tasks just got marked done.

**Primary recommendation:** Write targeted pytest tests for the specific edge cases described above. No production code changes are needed for either requirement — only test coverage.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | `>=7` (project uses) | Test runner | Project standard |
| pytest-asyncio | current | async test support | Required for all orchestrator tests |
| `unittest.mock` | stdlib | Patching, AsyncMock, MagicMock | Project uses throughout test file |

**Installation:** Already present. No new dependencies needed.

## Architecture Patterns

### Existing Test Structure
```
tests/
└── test_orchestrator.py   # ~2138 lines, 61 tests
    ├── helpers            # _make_task_spec, _make_plan, _make_state_manager, mock ACP clients
    ├── TestOrchestrator   # ORCH-02 loop tests
    ├── TestOrch04CompleteGate
    ├── TestOrch05RevisionSend / MaxRevisions / SessionOpen
    ├── TestComm05/06/07   # cancel_agent, inject_guidance, pause
    ├── TestOrchestratorModeWiring / MemoryDir / SessionPersistence
    ├── TestOrchestratorResume
    ├── TestPreRunReview / TestRunAuto
    ├── TestActiveClientCleanup
    ├── TestCancelAgentIntegration
    ├── TestPermissionHandlerWiring
    ├── TestAgentStatusLifecycle
    ├── TestSemaphoreScope     ← RESM-01 is partly here
    └── TestResumeScheduler    ← RESM-02 is partly here
```

### Pattern: AsyncMock + patch.object
All orchestrator tests use this pattern for isolating `_run_agent_loop`:

```python
with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
    await orch.resume()
```

When testing `_run_agent_loop` directly, the pattern is:
```python
with patch(f"{_ORCH}.review_output", AsyncMock(side_effect=SomeError)):
    await orch._run_agent_loop(spec, sem, review_only=True)
```

### Pattern: State verification via mutate tracking
```python
def _track_mutate(fn):
    from conductor.state.models import ConductorState, Task
    dummy = ConductorState(tasks=[Task(id="t1", title="T1", description="D1")])
    fn(dummy)
    for task in dummy.tasks:
        if task.review_status == "approved":
            approved_ids.append(task.id)
```

### Anti-Patterns to Avoid
- **Patching `asyncio.wait` directly:** Fragile and unnecessary; patching `_run_agent_loop` side_effect is sufficient to test loop behavior.
- **Using `asyncio.sleep(0)` in resume tests:** Not needed when `await orch.resume()` completes synchronously via mocked `_run_agent_loop`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async exception capture | Manual asyncio task wrappers | `AsyncMock(side_effect=...)` | Built-in exception simulation |
| Concurrent task ordering | Thread locks, Events | `asyncio.wait` already used; test by tracking call order list | Simpler, already proven |

## Common Pitfalls

### Pitfall 1: `fut.exception()` raises `CancelledError` if task was cancelled
**What goes wrong:** Calling `fut.exception()` on a cancelled asyncio.Future raises `CancelledError` instead of returning None.
**Why it happens:** Python asyncio specification: `future.exception()` raises `CancelledError` for cancelled futures.
**How to avoid:** Current code only calls `fut.exception()` inside the `done_futures` loop which runs for naturally-completed futures (from `asyncio.wait`). However, tests should verify this is not a problem by including futures that complete with exceptions, not just those that succeed.
**Warning signs:** `CancelledError` propagating out of the resume loop.

### Pitfall 2: `marked_done` and `pending` both empty in the same iteration
**What goes wrong:** If all tasks in `get_ready()` are completed IDs AND no tasks were previously pending, the `if not pending and marked_done: continue` guard allows the loop to continue correctly. Without this guard, the `if not pending: break` fires and the loop terminates before newly unblocked tasks can run.
**Why it happens:** `get_ready()` returns completed tasks that were never processed by `scheduler.done()`.
**How to avoid:** The guard already exists. Test that the loop does NOT break prematurely when completed tasks are the only items in the current `get_ready()` batch.

### Pitfall 3: `except Exception` swallows non-review errors in `review_only` path
**What goes wrong:** The `except Exception` handler in `_run_agent_loop` is intentionally broad. If the mock setup in tests raises unexpectedly in the wrong place (e.g., `asyncio.to_thread` fails), the best-effort path silently accepts failure.
**Why it happens:** Overly broad exception catch.
**How to avoid:** Tests should verify the warning is logged (use `caplog`) and that `final_verdict.approved is True` even for non-`ReviewError` exception types.

## Code Examples

### RESM-01: The exact review_only exception handler
```python
# Source: orchestrator.py lines 700-714
else:
    # --- Review only (no semaphore needed) ---
    try:
        final_verdict = await review_output(
            task_description=task_spec.description,
            target_file=task_spec.target_file,
            agent_summary="(resumed — file already exists on disk)",
            repo_path=self._repo_path,
        )
    except Exception:  # noqa: BLE001
        # Best-effort: file exists on disk, approve even if review fails
        logger.warning(
            "Review failed for resumed task %s — approving best-effort",
            task_spec.id,
        )
        final_verdict = ReviewVerdict(approved=True)
```

Key test observation: `task_spec.id` is used in the log message. Tests should verify the log message contains the task ID.

### RESM-02: The spawn loop marked_done guard and exception retrieval
```python
# Source: orchestrator.py lines 382-431
while scheduler.is_active():
    ready_ids = scheduler.get_ready()

    marked_done = False
    for task_id in ready_ids:
        if task_id in completed_ids:
            scheduler.done(task_id)
            marked_done = True
            continue
        if task_id not in pending and task_id in task_specs:
            review_only = task_mode.get(task_id, False)
            t = asyncio.create_task(
                self._run_agent_loop(task_specs[task_id], sem, review_only=review_only)
            )
            pending[task_id] = t
            self._active_tasks[task_id] = t

    # If we only marked completed tasks done, loop again to get
    # newly-unblocked tasks before waiting on pending futures
    if not pending and marked_done:
        continue
    if not pending:
        break

    done_futures, _ = await asyncio.wait(
        pending.values(), return_when=asyncio.FIRST_COMPLETED
    )

    for fut in done_futures:
        completed_id = next(
            tid for tid, t in pending.items() if t is fut
        )
        del pending[completed_id]
        self._active_tasks.pop(completed_id, None)
        # Retrieve exception to suppress warning — the error was already logged
        if fut.exception() is not None:
            logger.error(
                "Task %s failed during resume: %s",
                completed_id,
                fut.exception(),
            )
        scheduler.done(completed_id)
```

### Test pattern for exception retrieval verification
```python
@pytest.mark.asyncio
async def test_resume_logs_error_for_failed_task(self, tmp_path, caplog):
    import logging
    # Make _run_agent_loop raise for one task
    async def _failing_loop(spec, sem, **kwargs):
        raise RuntimeError("agent exploded")

    with patch.object(orch, '_run_agent_loop', side_effect=_failing_loop):
        with caplog.at_level(logging.ERROR, logger="conductor.orchestrator"):
            await orch.resume()

    assert any("failed during resume" in msg for msg in caplog.messages)
```

### Test pattern for marked_done continuation
```python
@pytest.mark.asyncio
async def test_resume_marked_done_unblocks_dependent(self, tmp_path):
    # t1: COMPLETED (ready immediately, just needs scheduler.done())
    # t2: PENDING, requires t1
    # Expected: t2 still runs even though pending was empty after t1's done() call
    ...
    assert mock_loop.call_count == 1  # only t2 ran (t1 was pre-completed)
    assert mock_loop.call_args_list[0][0][0].id == "t2"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| resume() re-ran all in-progress tasks from scratch | review_only mode for tasks with existing files | Phase 20/21 | Faster resume, less redundant work |
| No exception retrieval from done futures | `fut.exception()` called explicitly | Phase 23 partial impl | Suppresses Python warning "Task exception was never retrieved" |

## Open Questions

1. **Should `fut.exception()` be called before or guard against `CancelledError`?**
   - What we know: `asyncio.wait` with `FIRST_COMPLETED` returns naturally completed tasks. Cancelled futures would have been awaited/handled before being put in `pending`.
   - What's unclear: Whether cancelled futures can appear in `done_futures` in edge cases.
   - Recommendation: Add a try/except around `fut.exception()` in tests that simulate cancellation, or document as out-of-scope since `resume()` does not cancel tasks internally.

2. **Test for `marked_done` + non-empty pending in same iteration?**
   - What we know: The guard `if not pending and marked_done: continue` only fires when pending is empty.
   - What's unclear: Whether we need a test for the case where `marked_done=True` AND `pending` is non-empty (i.e., no guard fires, normal wait proceeds).
   - Recommendation: Add this test to prove the guard doesn't interfere with normal operation.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest with pytest-asyncio |
| Config file | `packages/conductor-core/pyproject.toml` (asyncio_mode = "auto" inferred) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_orchestrator.py -x -q` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RESM-01 | `review_only` exception fallback approves best-effort | unit | `pytest tests/test_orchestrator.py::TestSemaphoreScope -x` | ✅ partial (1 test exists) |
| RESM-01 | warning log contains task_spec.id | unit | `pytest tests/test_orchestrator.py -k "review_only_approves" -x` | ❌ Wave 0 |
| RESM-01 | state mutation sets APPROVED after fallback | unit | `pytest tests/test_orchestrator.py -k "review_only_approves" -x` | ❌ Wave 0 |
| RESM-01 | non-ReviewError exceptions (RuntimeError, ConnectionError) also trigger fallback | unit | `pytest tests/test_orchestrator.py::TestSemaphoreScope -x` | ❌ Wave 0 |
| RESM-02 | `marked_done` prevents premature break when all ready IDs are completed | unit | `pytest tests/test_orchestrator.py::TestResumeScheduler -x` | ❌ Wave 0 |
| RESM-02 | failed task exception retrieved and logged, loop continues | unit | `pytest tests/test_orchestrator.py::TestResumeScheduler -x` | ❌ Wave 0 |
| RESM-02 | `marked_done=True` + non-empty pending does not interrupt wait | unit | `pytest tests/test_orchestrator.py::TestResumeScheduler -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_orchestrator.py -x -q`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] New tests in `test_orchestrator.py::TestSemaphoreScope` — covers RESM-01 warning log and non-ReviewError exceptions
- [ ] New tests in `test_orchestrator.py::TestResumeScheduler` — covers RESM-02 `marked_done` guard and exception retrieval
- [ ] No framework install needed — pytest + pytest-asyncio already present

## Current Coverage Analysis

### What exists (61 tests, all passing)

**RESM-01 partial coverage:**
- `TestSemaphoreScope::test_review_only_approves_on_review_error` — tests `ReviewError` exception type triggers fallback, verifies `mgr.mutate.call_count >= 2` (proves state was updated). Does NOT verify: log message content, APPROVED review_status, non-`ReviewError` exception types.

**RESM-02 partial coverage:**
- `TestResumeScheduler::test_resume_skips_completed_tasks` — verifies completed tasks don't get `_run_agent_loop` called. Does NOT test the scheduler-level `marked_done` path.
- `TestResumeScheduler::test_resume_respects_dependencies` — tests t1 completes before t2 starts when t1 is IN_PROGRESS. Does NOT test case where t1 is already COMPLETED in state (the `marked_done` path).
- No test exercises the `fut.exception()` retrieval branch.

### What is missing

**RESM-01 gaps:**
1. `test_review_only_approves_on_connection_error` — `review_output` raises `ConnectionError`
2. `test_review_only_approves_on_runtime_error` — `review_output` raises `RuntimeError`
3. `test_review_only_warning_log_contains_task_id` — uses `caplog` to assert log message contains spec ID
4. `test_review_only_state_approved_after_fallback` — tracks mutate to assert `review_status == "approved"` after exception

**RESM-02 gaps:**
1. `test_resume_marked_done_unblocks_dependent_task` — COMPLETED t1 + PENDING t2(requires t1): t2 runs despite pending being empty during t1's scheduler.done() call
2. `test_resume_failed_task_exception_retrieved` — `_run_agent_loop` raises; verifies loop continues and error is logged (using `caplog`)
3. `test_resume_marked_done_with_pending_nonempty` — COMPLETED t1 + IN_PROGRESS t2: verify loop doesn't break when `marked_done=True` but `pending` is non-empty

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `packages/conductor-core/src/conductor/orchestrator/orchestrator.py`
- Direct code inspection of `packages/conductor-core/tests/test_orchestrator.py`
- `uv run pytest` execution: 61 tests, all passing

### Secondary (MEDIUM confidence)
- Python asyncio docs: `Future.exception()` behavior on cancelled futures (known behavior)
- `ReviewError` in `packages/conductor-core/src/conductor/orchestrator/errors.py`

## Metadata

**Confidence breakdown:**
- Current code state: HIGH — read directly from source
- Missing test gaps: HIGH — confirmed by running test suite
- Architecture patterns: HIGH — consistent with entire test file style
- Pitfalls: MEDIUM — based on Python asyncio knowledge, not project-specific docs

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable code, no external dependencies changing)
