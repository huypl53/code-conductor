# Phase 24: Task Verification and Quality Loops - Research

**Researched:** 2026-03-11
**Domain:** Python asyncio orchestration — file existence gating, revision loops, post-run build verification
**Confidence:** HIGH

## Summary

Phase 24 adds two verification layers to the Conductor orchestrator. Layer 1 is a per-task
file existence gate that hooks into the already-working revision loop: after the reviewer
returns `approved=True`, the orchestrator checks whether `target_file` actually exists on
disk; if it does not, a synthetic `ReviewVerdict(approved=False)` is injected and the loop
retries as normal. Layer 2 adds an optional `build_command` parameter to the Orchestrator
that runs a shell command (e.g. `npx tsc --noEmit`) via `asyncio.create_subprocess_shell`
after all tasks complete in both `run()` and `resume()`, reporting failures without blocking
task completion status.

All necessary primitives exist today: `ReviewVerdict` has `quality_issues` and
`revision_instructions` fields; `ReviewStatus.NEEDS_REVISION` is already defined; the
revision loop already handles `approved=False` verdicts; `Path` is already imported in
`orchestrator.py`. No schema changes are required.

**Primary recommendation:** Insert the file existence gate directly inside the existing
`for revision_num in range(max_revisions + 1)` block in `_run_agent_loop`, after calling
`review_output()`. Add `build_command: str | None = None` to `__init__` and a new
`_post_run_build_check()` method called at the tail of `run()` and `resume()`.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VRFY-01 | When a task has `target_file` set and the file does not exist on disk after review, the orchestrator retries via the revision loop instead of marking COMPLETED | Revision loop at lines 675-695 in `_run_agent_loop` is the correct insertion point; `Path` already imported; synthetic `ReviewVerdict` pattern matches existing model |
| QUAL-01 | Reviewer returns structured feedback; agent receives revision instructions and resubmits within a configurable maximum number of rounds | `ReviewVerdict.revision_instructions` already used in existing revision message; `max_revisions` param already on `_run_agent_loop`; loop structure handles this today |
| QUAL-02 | When revision attempts are exhausted, the task is marked NEEDS_REVISION with the reason, not silently completed | `ReviewStatus.NEEDS_REVISION` already defined in `state/models.py`; `_make_complete_task_fn` already accepts `review_status` and sets it on the `Task` record |
</phase_requirements>

---

## Research Question Answers

### 1. `_run_agent_loop` structure — where review happens and where the file gate goes

The method signature (lines 578-585):
```python
async def _run_agent_loop(
    self,
    task_spec: TaskSpec,
    sem: asyncio.Semaphore,
    max_revisions: int | None = None,
    resume_session_id: str | None = None,
    review_only: bool = False,
) -> None:
```

Two branches:
- `if not review_only:` (lines 631-697) — full agent execution inside `async with sem` and `async with ACPClient(...)`. The inner revision loop is `for revision_num in range(max_revisions + 1)` at line 675. After `stream_response()` drains, `review_output()` is called (line 680-685). The verdict check (`if verdict.approved: break`) is at line 688. The revision send is at lines 691-695.
- `else:` (lines 699-714) — review-only path for resumed tasks whose file already exists; runs `review_output()` once and uses best-effort fallback on exception.

**File gate insertion point:** Inside the `if not review_only:` branch, between the `review_output()` call (line 685) and `if verdict.approved: break` (line 688). The design doc confirms this is the correct placement. Since `review_only` is only used for tasks where the file already exists on disk, the gate is a no-op there.

After the entire block (line 716+), the final state mutation sets `TaskStatus.COMPLETED` regardless of the verdict outcome — this is the current behavior that QUAL-02 needs to preserve (COMPLETED is always set, but `review_status` carries `NEEDS_REVISION` when exhausted).

### 2. ReviewVerdict structure — what fields exist

From `reviewer.py` (lines 21-27):
```python
class ReviewVerdict(BaseModel):
    approved: bool
    quality_issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""
```

The reviewer already returns structured feedback:
- `approved: bool` — pass/fail
- `quality_issues: list[str]` — list of specific problems
- `revision_instructions: str` — actionable string sent back to agent

When the target file does not exist, `review_output()` already returns a non-approved verdict (lines 88-98 in `reviewer.py`):
```python
return ReviewVerdict(
    approved=False,
    quality_issues=["Target file was not created"],
    revision_instructions=f"Create the file at {target_file}",
)
```

However this is only reached when `review_output()` is called. The problem (from the design doc) is that the reviewer already returns `approved=False` for missing files, but `_run_agent_loop` currently still marks the task COMPLETED when revisions are exhausted. The fix therefore is simply to ensure the existing non-approved verdict from `review_output()` is respected throughout the loop — or, alternatively, to insert a synthetic verdict override after an approved verdict if the file is still absent (the override approach described in the design doc handles the edge case where the reviewer mistakenly approves a missing file).

The design doc's approach is: after `review_output()` returns `approved=True`, check the file again and inject a synthetic `ReviewVerdict(approved=False, ...)` if the file is still missing. This is a belt-and-suspenders approach that handles reviewer hallucination.

### 3. Current revision loop — how it works and where max_revisions applies

The loop (lines 675-695):
```python
for revision_num in range(max_revisions + 1):
    monitor = StreamMonitor(task_spec.id)
    async for message in client.stream_response():
        monitor.process(message)

    verdict = await review_output(...)
    final_verdict = verdict

    if verdict.approved:
        break

    if revision_num < max_revisions:
        await client.send(
            f"Revision needed:\n{verdict.revision_instructions}"
            "\n\nPlease revise your implementation."
        )
```

Key observations:
- `range(max_revisions + 1)` means the agent gets `max_revisions + 1` attempts total (initial run + N revisions).
- On `revision_num == max_revisions` (last iteration), if not approved, the `if revision_num < max_revisions:` guard prevents sending another revision message — the loop simply exits.
- `final_verdict` captures the last verdict. Post-loop, `review_status` is set from `final_verdict.approved`.
- `max_revisions` defaults to `self._max_revisions` which defaults to `2` in `__init__`.

The file gate's synthetic verdict must also set `final_verdict` so the post-loop state mutation correctly reflects NEEDS_REVISION.

### 4. TaskStatus and ReviewStatus — is NEEDS_REVISION defined?

From `state/models.py`:

```python
class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
```

`ReviewStatus.NEEDS_REVISION` is already defined. `TaskStatus` does NOT have a `NEEDS_REVISION` value — the design is that `TaskStatus` stays `COMPLETED` while `ReviewStatus` is set to `NEEDS_REVISION` (best-effort completion).

This is the current behavior in `_make_complete_task_fn` (lines 803-824):
```python
def _complete(state: ConductorState) -> None:
    for task in state.tasks:
        if task.id == task_id:
            task.status = TaskStatus.COMPLETED  # always COMPLETED
            task.review_status = review_status  # APPROVED or NEEDS_REVISION
            task.revision_count = revision_count
            ...
```

No model changes needed.

### 5. Task state model — TaskSpec fields

`TaskSpec` (orchestrator/models.py):
```python
class TaskSpec(BaseModel):
    id: str
    title: str
    description: str
    role: str
    target_file: str          # relative path; empty string means no file gate
    material_files: list[str]
    requires: list[str]
    produces: list[str]
```

`Task` (state/models.py) mirrors this plus runtime state fields:
- `status: TaskStatus`
- `review_status: ReviewStatus`
- `revision_count: int`
- `assigned_agent: str | None`
- `outputs: dict[str, Any]`

Both models already support everything Phase 24 needs — no new fields required.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python asyncio | stdlib | Async subprocess via `create_subprocess_shell` | Already used throughout orchestrator |
| pathlib.Path | stdlib | File existence check (`path.exists()`) | Already imported in orchestrator.py |
| Pydantic v2 | installed | ReviewVerdict model already uses it | Entire codebase uses Pydantic v2 |
| pytest-asyncio | installed | Test framework for async tests | All existing orchestrator tests use it |

### No New Dependencies Required
All implementation uses stdlib and libraries already present.

---

## Architecture Patterns

### Pattern 1: Synthetic verdict injection (file gate)
**What:** After `review_output()` returns `approved=True`, check `Path(self._repo_path) / task_spec.target_file` with `.exists()`. If missing and `task_spec.target_file` is non-empty, replace `verdict` with a synthetic `ReviewVerdict(approved=False, ...)`.

**When to use:** Only inside `if not review_only:` branch. The `review_only` branch is only used when the file already exists (this is the precondition for entering that branch in `resume()`).

**Code shape:**
```python
verdict = await review_output(...)
final_verdict = verdict

# File existence gate (VRFY-01)
if verdict.approved and task_spec.target_file:
    target_path = Path(self._repo_path) / task_spec.target_file
    if not target_path.exists():
        verdict = ReviewVerdict(
            approved=False,
            quality_issues=["Target file was not created on disk"],
            revision_instructions=(
                f"The target file {task_spec.target_file} was not created. "
                "Please create it."
            ),
        )
        final_verdict = verdict

if verdict.approved:
    break

if revision_num < max_revisions:
    await client.send(
        f"Revision needed:\n{verdict.revision_instructions}"
        "\n\nPlease revise your implementation."
    )
```

### Pattern 2: Post-run build verification
**What:** Optional `build_command: str | None` on `Orchestrator.__init__`. A private `_post_run_build_check()` method runs it via `asyncio.create_subprocess_shell`, logs the result, and returns a bool. Called at the tail of both `run()` and `resume()`.

**When to use:** When `self._build_command` is set. Does NOT block task completion or raise.

**asyncio.subprocess pattern (stdlib):**
```python
proc = await asyncio.create_subprocess_shell(
    self._build_command,
    cwd=self._repo_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()
if proc.returncode != 0:
    logger.error("Build check failed (exit %d):\n%s", proc.returncode, stderr.decode(errors="replace"))
    return False
return True
```

### Pattern 3: CLI flag passthrough
**What:** `--build-command` Typer option in `run()` → passed to `_run_async()` → passed to `Orchestrator()` constructor.

**Typer pattern:**
```python
build_command: str = typer.Option(None, "--build-command", help="...")
```

### Anti-Patterns to Avoid
- **Raising on build failure:** The build command is a final report, not a gate. It must NOT raise or change task statuses.
- **Applying file gate in review_only branch:** The `review_only` branch is for tasks where the file already exists (precondition). Adding the gate there would add useless overhead and risk breaking the resume path.
- **Mutating TaskStatus to NEEDS_REVISION:** Only `ReviewStatus` should carry NEEDS_REVISION; `TaskStatus` stays COMPLETED (best-effort completion design).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async subprocess | Custom thread executor | `asyncio.create_subprocess_shell` | stdlib, already used pattern in codebase |
| File existence | Retry wrapper | `Path.exists()` inline | One-liner, already imported |
| Verdict override | Custom review class | Instantiate `ReviewVerdict(approved=False, ...)` | Already a plain Pydantic model, cheap to instantiate |

---

## Common Pitfalls

### Pitfall 1: Forgetting to update `final_verdict` when injecting synthetic verdict
**What goes wrong:** `verdict` is overridden but `final_verdict` is not, so the post-loop `review_status` ends up as APPROVED even when the file was missing.
**How to avoid:** Always set `final_verdict = verdict` after the synthetic injection, before the `if verdict.approved: break` check.
**Warning signs:** Test `test_missing_file_exhausts_revisions` fails — task ends with APPROVED review_status despite file never existing.

### Pitfall 2: Applying file gate when `task_spec.target_file` is empty string
**What goes wrong:** `Path(repo_path) / ""` resolves to `repo_path` itself, which exists, so the gate is a no-op — but the intent check `if task_spec.target_file` guards this correctly.
**How to avoid:** The condition must be `if verdict.approved and task_spec.target_file:` — the truthiness check on the string handles empty string.

### Pitfall 3: Build command called before `asyncio` event loop has subprocess support on some platforms
**What goes wrong:** On some Python versions/platforms, `asyncio.create_subprocess_shell` requires the event loop to be a `ProactorEventLoop` (Windows).
**How to avoid:** The existing codebase targets Linux/macOS for CI; document as known limitation for Windows if applicable.

### Pitfall 4: `revision_num` variable scope after loop
**What goes wrong:** After the `for revision_num in range(...)` loop, `revision_num` holds the last value of the loop variable. If the loop body never executes (e.g. `max_revisions = -1`), the variable is undefined. The current code assigns `revision_num = 0` before the loop at line 629 as a safety initializer — this must be preserved.
**Warning signs:** `UnboundLocalError` in edge-case tests with `max_revisions=0`.

---

## Code Examples

### Current revision loop (lines 675-695 in orchestrator.py)
```python
for revision_num in range(max_revisions + 1):
    monitor = StreamMonitor(task_spec.id)
    async for message in client.stream_response():
        monitor.process(message)

    verdict = await review_output(
        task_description=task_spec.description,
        target_file=task_spec.target_file,
        agent_summary=monitor.result_text or "",
        repo_path=self._repo_path,
    )
    final_verdict = verdict

    if verdict.approved:
        break

    if revision_num < max_revisions:
        await client.send(
            f"Revision needed:\n{verdict.revision_instructions}"
            "\n\nPlease revise your implementation."
        )
```

### File gate insertion (replaces lines 686-695)
```python
# After: verdict = await review_output(...)
# After: final_verdict = verdict

# File existence gate: override if reviewer approves but file is absent
if verdict.approved and task_spec.target_file:
    target_path = Path(self._repo_path) / task_spec.target_file
    if not target_path.exists():
        verdict = ReviewVerdict(
            approved=False,
            quality_issues=["Target file was not created on disk"],
            revision_instructions=(
                f"The target file {task_spec.target_file} was not created. "
                "Please create it."
            ),
        )
        final_verdict = verdict

if verdict.approved:
    break

if revision_num < max_revisions:
    await client.send(
        f"Revision needed:\n{verdict.revision_instructions}"
        "\n\nPlease revise your implementation."
    )
```

### Post-loop state mutation (already correct, lines 716-731)
```python
review_status = (
    ReviewStatus.APPROVED
    if final_verdict and final_verdict.approved
    else ReviewStatus.NEEDS_REVISION
)

await asyncio.to_thread(
    self._state.mutate,
    self._make_complete_task_fn(
        task_spec.id,
        agent_id,
        review_status=review_status,
        revision_count=revision_num,
    ),
)
```
This code already sets NEEDS_REVISION when `final_verdict.approved` is False — no changes needed here.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Reviewer returns non-approved for missing file, but orchestrator always completes | File gate injects synthetic non-approved verdict, orchestrator retries | Closes gap where reviewer correctly reports missing file but retry never happens |
| No post-run verification | Optional `build_command` runs after all tasks | Cross-file integration errors surfaced after the run |

---

## Open Questions

1. **Should the build command result affect anything in state?**
   - What we know: Design doc says it's a "final report, not a gate" and "does not block task completion"
   - What's unclear: Should `ConductorState` gain a `build_status` field for dashboard display?
   - Recommendation: Omit state tracking for Phase 24. Log only. Future enhancement if needed.

2. **What if `task_spec.target_file` is an absolute path?**
   - What we know: The current `resume()` method handles this case: `if not target.is_absolute(): target = Path(self._repo_path) / target`
   - What's unclear: `_run_agent_loop` does not have this guard currently (the reviewer also uses `Path(repo_path) / target_file` unconditionally)
   - Recommendation: Match reviewer.py behavior — use `Path(self._repo_path) / task_spec.target_file` unconditionally. Absolute paths are not expected from the decomposer schema.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `packages/conductor-core/pyproject.toml` |
| Quick run command | `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v` |
| Full suite command | `cd packages/conductor-core && uv run python -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VRFY-01 | Missing file triggers revision message | unit | `pytest tests/test_orchestrator.py::TestFileExistenceGate::test_missing_file_triggers_revision -x` | ❌ Wave 0 |
| VRFY-01 | Existing file skips gate | unit | `pytest tests/test_orchestrator.py::TestFileExistenceGate::test_existing_file_no_revision -x` | ❌ Wave 0 |
| QUAL-01 | Agent receives revision_instructions string | unit | `pytest tests/test_orchestrator.py::TestFileExistenceGate -x` | ❌ Wave 0 |
| QUAL-02 | Exhausted retries sets NEEDS_REVISION | unit | `pytest tests/test_orchestrator.py::TestFileExistenceGate::test_missing_file_exhausts_revisions -x` | ❌ Wave 0 |
| QUAL-02 | No target_file skips gate entirely | unit | `pytest tests/test_orchestrator.py::TestFileExistenceGate::test_empty_target_file_skips_check -x` | ❌ Wave 0 |
| (build) | build_command runs after tasks | unit | `pytest tests/test_orchestrator.py::TestPostRunBuild::test_build_command_runs_after_tasks -x` | ❌ Wave 0 |
| (build) | no build_command = no subprocess | unit | `pytest tests/test_orchestrator.py::TestPostRunBuild::test_no_build_command_skips_check -x` | ❌ Wave 0 |
| (build) | build failure logged, not raised | unit | `pytest tests/test_orchestrator.py::TestPostRunBuild::test_build_failure_logged -x` | ❌ Wave 0 |
| (build) | build runs after resume | unit | `pytest tests/test_orchestrator.py::TestPostRunBuild::test_build_runs_after_resume -x` | ❌ Wave 0 |
| (CLI) | --build-command forwarded to Orchestrator | unit | `pytest tests/test_run_command.py::TestRunBuildCommand -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v`
- **Per wave merge:** `cd packages/conductor-core && uv run python -m pytest tests/ -v`
- **Phase gate:** Full suite green before marking phase complete

### Wave 0 Gaps
- [ ] `tests/test_orchestrator.py` — add `TestFileExistenceGate` class (4 tests for VRFY-01/QUAL-01/QUAL-02)
- [ ] `tests/test_orchestrator.py` — add `TestPostRunBuild` class (4 tests for build_command behavior)
- [ ] `tests/test_run_command.py` — add `TestRunBuildCommand` class (2 tests for CLI flag passthrough)

*(Test templates for all gaps are provided verbatim in the implementation plan at `docs/plans/2026-03-11-task-verification.md`.)*

---

## Sources

### Primary (HIGH confidence)
- Direct code reading — `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` lines 578-840
- Direct code reading — `packages/conductor-core/src/conductor/orchestrator/reviewer.py`
- Direct code reading — `packages/conductor-core/src/conductor/state/models.py`
- Direct code reading — `packages/conductor-core/src/conductor/orchestrator/models.py`
- Direct code reading — `packages/conductor-core/src/conductor/cli/commands/run.py`
- Design doc — `docs/plans/2026-03-11-task-verification-design.md`
- Implementation plan — `docs/plans/2026-03-11-task-verification.md`

### Secondary (MEDIUM confidence)
- N/A — all findings are from direct code inspection of the live codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — read directly from source files
- Architecture: HIGH — insertion point identified by line number from actual code
- Pitfalls: HIGH — derived from reading the actual loop logic and data flow
- Test patterns: HIGH — existing test helpers (`_make_task_spec`, `_make_mock_acp_client`, `_approved_review_mock`, `_ORCH`) confirmed by reading test file

**Research date:** 2026-03-11
**Valid until:** 2026-04-10 (stable codebase, no fast-moving dependencies)
