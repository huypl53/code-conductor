---
phase: 23-resume-robustness
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/tests/test_orchestrator.py
autonomous: true
requirements:
  - RESM-01
  - RESM-02

must_haves:
  truths:
    - "All 61 existing tests still pass after additions"
    - "review_only exception fallback is tested for non-ReviewError types with log verification"
    - "review_only fallback produces an explicit APPROVED state mutation"
    - "Resume spawn loop correctly short-circuits on pre-completed tasks via marked_done"
    - "Resume loop processes newly-unblocked tasks after marking completed ones done"
    - "fut.exception() retrieval in resume loop is tested without hang or crash"
  artifacts:
    - path: "packages/conductor-core/tests/test_orchestrator.py"
      provides: "All new RESM-01 and RESM-02 test cases"
      contains: "TestReviewOnlyFallback"
  key_links:
    - from: "tests/test_orchestrator.py"
      to: "orchestrator._run_agent_loop (review_only branch)"
      via: "patch review_output to raise RuntimeError, assert warning logged + approved state"
    - from: "tests/test_orchestrator.py"
      to: "orchestrator.resume (marked_done guard)"
      via: "state with pre-completed + pending tasks, assert all tasks processed"
---

<objective>
Add targeted test coverage for the two resume robustness behaviors already implemented in production code but lacking tests.

Purpose: Prevent regressions in crash-recovery paths. Both code paths exist and work — these tests lock in the contract so future refactors cannot silently break them.
Output: New test classes `TestReviewOnlyFallback` and `TestResumeSpawnLoop` appended to `test_orchestrator.py`.
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@packages/conductor-core/src/conductor/orchestrator/orchestrator.py
@packages/conductor-core/tests/test_orchestrator.py

<interfaces>
<!-- Key code paths under test. Read from orchestrator.py. -->

From orchestrator.py — review_only branch in _run_agent_loop (lines 699-714):
```python
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

From orchestrator.py — resume spawn loop (lines 381-428):
```python
while scheduler.is_active():
    ready_ids = scheduler.get_ready()

    marked_done = False
    for task_id in ready_ids:
        if task_id in completed_ids:
            scheduler.done(task_id)
            marked_done = True
            continue
        if task_id not in pending and task_id in task_specs:
            ...
            pending[task_id] = t

    # If we only marked completed tasks done, loop again to get
    # newly-unblocked tasks before waiting on pending futures
    if not pending and marked_done:
        continue
    if not pending:
        break

    done_futures, _ = await asyncio.wait(...)
    for fut in done_futures:
        ...
        if fut.exception() is not None:
            logger.error(
                "Task %s failed during resume: %s",
                completed_id,
                fut.exception(),
            )
        scheduler.done(completed_id)
```

From test_orchestrator.py — existing resume state builder pattern (lines 1238-1285):
```python
state_mgr.read_state = MagicMock(return_value=mock_state)
orch._run_agent_loop = _capture_loop
await orch.resume()
```

Logger name: "conductor.orchestrator"
_ORCH constant: "conductor.orchestrator.orchestrator"
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Test RESM-01 — review_only exception fallback</name>
  <files>packages/conductor-core/tests/test_orchestrator.py</files>
  <behavior>
    - Test A: When review_output raises RuntimeError during review_only, _run_agent_loop does NOT raise — it completes normally with an APPROVED state mutation.
    - Test B: When review_output raises a generic ValueError during review_only, a WARNING log is emitted containing the task ID.
    - Test C: When review_output raises during review_only, the task is mutated to COMPLETED with review_status=APPROVED (not NEEDS_REVISION).
  </behavior>
  <action>
Append a new class `TestReviewOnlyFallback` to `test_orchestrator.py` after the last existing class. Do NOT modify any existing tests.

The class tests `_run_agent_loop` called directly with `review_only=True`.

Setup pattern for each test:
1. Create a `TaskSpec` using `_make_task_spec("t-resm-01", "src/resm.py")`
2. Create `sem = asyncio.Semaphore(2)` and `state_mgr = _make_state_manager()`
3. Patch `f"{_ORCH}.review_output"` to raise the target exception type
4. Call `await orch._run_agent_loop(task_spec, sem, review_only=True)` — must NOT raise
5. Assert state mutation observed `review_status == "approved"`

For log verification (Test B), use `caplog` fixture with `caplog.at_level(logging.WARNING, logger="conductor.orchestrator")` and assert `"approving best-effort"` appears in caplog messages.

For state mutation tracking (Tests A and C), intercept `state_mgr.mutate` calls using the `_track_mutate` pattern from the existing test `test_approved_review_marks_task_completed_with_approved_status`:
```python
completed_tasks = []
def _track_mutate(fn):
    from conductor.state.models import ConductorState, Task
    dummy = ConductorState(tasks=[Task(id="t-resm-01", title="T", description="D")])
    fn(dummy)
    for task in dummy.tasks:
        if task.status == "completed":
            completed_tasks.append((task.id, task.review_status))
    return None
state_mgr.mutate = _track_mutate
```

Note: `review_only=True` skips ACPClient entirely — no need to patch `ACPClient`.

Three test methods:
- `test_review_only_exception_does_not_crash` — raises RuntimeError, asserts no exception propagates
- `test_review_only_exception_logs_warning` — raises ValueError, asserts warning log contains task id
- `test_review_only_exception_sets_approved_state` — raises RuntimeError, asserts final mutation is (task_id, "approved")
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && python -m pytest tests/test_orchestrator.py::TestReviewOnlyFallback -v 2>&1 | tail -20</automated>
  </verify>
  <done>
    - 3 new tests in TestReviewOnlyFallback all pass (green)
    - All 61 previously-passing tests still pass
    - No production code modified
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Test RESM-02 — resume spawn loop edge cases</name>
  <files>packages/conductor-core/tests/test_orchestrator.py</files>
  <behavior>
    - Test A: When state has one COMPLETED task (no deps) and one PENDING task (requires completed), resume() calls _run_agent_loop exactly once — for the pending task only — and the loop does not exit prematurely without processing it.
    - Test B: When state has only COMPLETED tasks, resume() calls _run_agent_loop zero times and returns cleanly (no hang).
    - Test C: When a spawned task future raises an exception, resume() retrieves the exception (no "Task exception was never retrieved" warning) and completes without crashing — the exception is logged.
  </behavior>
  <action>
Append a new class `TestResumeSpawnLoop` to `test_orchestrator.py` after `TestReviewOnlyFallback`.

State builder pattern: use `ConductorState` with explicit `TaskStatus.COMPLETED` / `TaskStatus.PENDING` tasks and matching `AgentRecord` entries. Follow the pattern from `test_resume_finds_in_progress_tasks` (lines 1228-1285 in existing tests).

Test A — marked_done guard allows pending task through:
```python
# completed_task: no deps, status=COMPLETED
# pending_task: requires=["completed_task"], status=PENDING
# State: both tasks present, one agent record for completed_task
# Expected: _run_agent_loop called once, with spec for pending_task
```
- `state_mgr.read_state = MagicMock(return_value=mock_state)`
- Replace `orch._run_agent_loop` with a capture coroutine
- `await orch.resume()`
- Assert spawned spec IDs == ["pending_task_id"]

Test B — all-completed state exits immediately:
```python
# Two tasks both COMPLETED, no pending
# Expected: _run_agent_loop called zero times
```

Test C — failed future exception retrieved without crash:
- Create an IN_PROGRESS task (target file does NOT exist on disk so it gets a full agent run, not review_only)
- Replace `orch._run_agent_loop` with a coroutine that raises `RuntimeError("agent failed")`
- `await orch.resume()` must complete without raising
- Use `caplog` to verify a log record with `"failed during resume"` appears at ERROR level

For Test C, the resume loop calls `fut.exception()` which requires the future to have actually raised. Use a real asyncio.Task that raises, not a MagicMock. The simplest approach: do NOT replace `_run_agent_loop` with a capture function — instead patch `review_output` to raise RuntimeError and provide an IN_PROGRESS task whose target file does not exist (triggering full agent run path). But that path requires ACPClient. Simpler alternative: replace `_run_agent_loop` with a coroutine that raises, which makes the asyncio.Task store the exception, then resume's `fut.exception()` retrieves it:

```python
async def _failing_loop(task_spec, sem, **kwargs):
    raise RuntimeError("agent failed during resume")

orch._run_agent_loop = _failing_loop
```

This is the correct approach — the asyncio.Task wrapping the coroutine will have `exception() != None`, which is exactly the code path being tested.

Do not patch `ACPClient` for Tests A and B since `_run_agent_loop` is replaced wholesale. For Test C, also replace `_run_agent_loop` — no need to patch ACPClient.
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && python -m pytest tests/test_orchestrator.py::TestResumeSpawnLoop -v 2>&1 | tail -20</automated>
  </verify>
  <done>
    - 3 new tests in TestResumeSpawnLoop all pass (green)
    - Full test suite passes: `python -m pytest tests/test_orchestrator.py` shows 67+ passed, 0 failed
    - No production code modified
  </done>
</task>

</tasks>

<verification>
Run the full orchestrator test suite to confirm no regressions:

```bash
cd /home/huypham/code/digest/claude-auto/packages/conductor-core
python -m pytest tests/test_orchestrator.py -v --tb=short 2>&1 | tail -30
```

Expected: all original 61 tests pass plus 6 new tests (3 RESM-01 + 3 RESM-02) = 67 total passed, 0 failed.
</verification>

<success_criteria>
1. `TestReviewOnlyFallback` has 3 passing tests covering non-ReviewError exception, warning log content, and APPROVED state mutation.
2. `TestResumeSpawnLoop` has 3 passing tests covering marked_done guard (pending task processed after completed), all-completed early exit, and failed future exception retrieval.
3. Zero existing tests broken.
4. Zero production code files modified.
5. `pytest tests/test_orchestrator.py` exits 0.
</success_criteria>

<output>
After completion, create `.planning/phases/23/23-01-SUMMARY.md` with:
- Tests added (class names and method names)
- Final test count
- Any notable implementation decisions
</output>
