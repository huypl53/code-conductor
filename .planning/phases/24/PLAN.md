---
phase: 24-task-verification
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
  - packages/conductor-core/tests/test_orchestrator.py
  - packages/conductor-core/tests/test_run_command.py
  - packages/conductor-core/src/conductor/cli/commands/run.py
autonomous: true
requirements: [VRFY-01, QUAL-01, QUAL-02]

must_haves:
  truths:
    - "When a task's target_file is set and the file is absent after the agent runs, the orchestrator sends a revision message and re-enters the loop instead of marking COMPLETED"
    - "When revisions are exhausted and the file is still missing, the task is marked COMPLETED with review_status=NEEDS_REVISION, never silently approved"
    - "When the reviewer returns approved=True but the file does not exist on disk, the orchestrator overrides to non-approved and retries (belt-and-suspenders against reviewer hallucination)"
    - "Tasks with no target_file (empty string) skip the file existence gate entirely and complete normally"
    - "The maximum number of revision rounds is configurable via Orchestrator(max_revisions=N), not hardcoded"
    - "A post-run build_command (optional) runs via asyncio.create_subprocess_shell after all tasks complete in run() and resume(), logging failures without raising or changing task statuses"
    - "conductor run --build-command 'cmd' forwards the command to the Orchestrator constructor"
  artifacts:
    - path: "packages/conductor-core/tests/test_orchestrator.py"
      provides: "TestFileExistenceGate class (4 tests) + TestPostRunBuild class (4 tests)"
      contains: "TestFileExistenceGate"
    - path: "packages/conductor-core/tests/test_run_command.py"
      provides: "TestRunBuildCommand class (2 tests)"
      contains: "TestRunBuildCommand"
    - path: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      provides: "File existence gate inside revision loop + _post_run_build_check method + build_command init param"
      contains: "target_path.exists"
    - path: "packages/conductor-core/src/conductor/cli/commands/run.py"
      provides: "--build-command Typer option forwarded to Orchestrator"
      contains: "build_command"
  key_links:
    - from: "orchestrator.py _run_agent_loop revision loop (line 686)"
      to: "Path(self._repo_path) / task_spec.target_file"
      via: "file existence gate injecting synthetic ReviewVerdict(approved=False)"
      pattern: "target_path.exists"
    - from: "orchestrator.py run() and resume()"
      to: "_post_run_build_check()"
      via: "tail call after spawn loop"
      pattern: "_post_run_build_check"
    - from: "run.py _run_async"
      to: "Orchestrator(build_command=build_command)"
      via: "kwarg passthrough"
      pattern: "build_command=build_command"
---

<objective>
Add two verification layers to the Conductor orchestrator so no task silently completes with missing output:

1. **File existence gate (VRFY-01/QUAL-01/QUAL-02):** Inside `_run_agent_loop`, after `review_output()` returns, check whether `target_file` exists on disk. If it does not, inject a synthetic `ReviewVerdict(approved=False)` so the revision loop retries. When retries are exhausted, the post-loop state mutation already sets `ReviewStatus.NEEDS_REVISION` — no model changes needed.

2. **Post-run build check:** An optional `build_command: str | None` parameter on `Orchestrator.__init__` runs a shell command after all tasks complete in `run()` and `resume()`. Failures are logged, never raised.

3. **CLI flag:** `conductor run --build-command '...'` forwards to the Orchestrator constructor.

Purpose: A real calendar-app task (EventChip) was marked `completed + approved` with the target file absent, breaking downstream tasks. This closes that gap.

Output:
- Modified `orchestrator.py`: file gate + `_post_run_build_check` + `build_command` init param
- Modified `run.py`: `--build-command` flag
- New tests in `test_orchestrator.py` (8 tests) and `test_run_command.py` (2 tests)
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@packages/conductor-core/src/conductor/orchestrator/orchestrator.py
@packages/conductor-core/src/conductor/orchestrator/reviewer.py
@packages/conductor-core/src/conductor/state/models.py
@packages/conductor-core/src/conductor/cli/commands/run.py
@packages/conductor-core/tests/test_orchestrator.py
@packages/conductor-core/tests/test_run_command.py

<interfaces>
<!-- Key contracts from the live codebase. Executor should use these directly. -->

From orchestrator.py — revision loop (lines 675-695, inside `if not review_only:` branch):
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
    final_verdict = verdict          # <-- line 686, FILE GATE GOES HERE

    if verdict.approved:             # <-- line 688
        break

    if revision_num < max_revisions: # <-- line 691
        await client.send(
            f"Revision needed:\n{verdict.revision_instructions}"
            "\n\nPlease revise your implementation."
        )
```

From orchestrator.py — post-loop state mutation (lines 716-731, NO changes needed):
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

From orchestrator.py — `__init__` signature (lines 108-124):
```python
def __init__(
    self,
    state_manager: StateManager,
    repo_path: str,
    mode: str = "auto",
    human_out: asyncio.Queue | None = None,
    human_in: asyncio.Queue | None = None,
    max_agents: int = 10,
    max_revisions: int = 2,   # configurable — do not hardcode
) -> None:
    self._state = state_manager
    self._repo_path = repo_path
    ...
    self._max_revisions = max_revisions
```

From reviewer.py — ReviewVerdict (lines 21-27):
```python
class ReviewVerdict(BaseModel):
    approved: bool
    quality_issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""
```

From state/models.py — ReviewStatus (lines 19-23):
```python
class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
```

From test_orchestrator.py — existing test helpers (used in all new tests):
```python
_ORCH = "conductor.orchestrator.orchestrator"
_APPROVED = ReviewVerdict(approved=True)

def _make_task_spec(task_id, target_file, requires=None, title=None) -> TaskSpec: ...
def _make_plan(tasks, max_agents=4) -> TaskPlan: ...
def _make_state_manager() -> MagicMock: ...
def _make_mock_acp_client() -> AsyncMock: ...
def _make_mock_acp_client_with_result(result_text="Done") -> AsyncMock: ...
def _approved_review_mock() -> AsyncMock: ...  # returns AsyncMock(return_value=_APPROVED)
```

From run.py — current `_run_async` signature (lines 43-50):
```python
async def _run_async(
    description: str,
    *,
    auto: bool,
    repo: Path,
    resume: bool = False,
    dashboard_port: int | None = None,
) -> None:
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write failing tests for file existence gate (TestFileExistenceGate)</name>
  <files>packages/conductor-core/tests/test_orchestrator.py</files>
  <behavior>
    - test_missing_file_triggers_revision: reviewer always approves, file never exists -> agent.send called with a message containing "target file" and "not created" (the revision message from the synthetic verdict)
    - test_existing_file_no_revision: file created before loop runs, reviewer approves -> loop completes with no extra revision send (mutate called exactly twice: add_agent + complete_task)
    - test_missing_file_exhausts_revisions: max_revisions=1, file never appears -> task ends with review_status="needs_revision" in state mutation
    - test_empty_target_file_skips_check: target_file="" -> gate never runs, completes normally (mutate call count == 2)
  </behavior>
  <action>
Append a new class `TestFileExistenceGate` to `test_orchestrator.py`. Place it after the existing `TestOrch05SessionOpenForRevision` class (around line 672). All 4 tests must import from `conductor.orchestrator.orchestrator` and use the existing helpers `_make_task_spec`, `_make_state_manager`, `_make_mock_acp_client`, `_approved_review_mock`, and `_ORCH`.

Key test patterns:

**test_missing_file_triggers_revision:**
```python
@pytest.mark.asyncio
async def test_missing_file_triggers_revision(self, tmp_path):
    from conductor.orchestrator.orchestrator import Orchestrator
    mgr = _make_state_manager()
    orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))
    sem = asyncio.Semaphore(1)
    spec = _make_task_spec("t1", "src/missing.tsx")
    revision_sent = False

    def _acp_factory(**kwargs):
        client = _make_mock_acp_client()
        original_send = client.send
        async def _track_send(msg):
            nonlocal revision_sent
            if "target file" in msg.lower() and "not created" in msg.lower():
                revision_sent = True
                # Create file so loop terminates on next pass
                (tmp_path / "src").mkdir(parents=True, exist_ok=True)
                (tmp_path / "src" / "missing.tsx").write_text("export default 1;")
            return await original_send(msg)
        client.send = _track_send
        return client

    with patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory), \
         patch(f"{_ORCH}.review_output", _approved_review_mock()):
        await orch._run_agent_loop(spec, sem, max_revisions=2)

    assert revision_sent, "Should have sent revision about missing target file"
```

**test_missing_file_exhausts_revisions:**
```python
@pytest.mark.asyncio
async def test_missing_file_exhausts_revisions(self, tmp_path):
    from conductor.orchestrator.orchestrator import Orchestrator
    from conductor.state.models import ConductorState, ReviewStatus
    state = ConductorState()
    mgr = _make_state_manager()
    completed_statuses = []
    def _track_mutate(fn):
        fn(state)
        for t in state.tasks:
            if t.review_status == ReviewStatus.NEEDS_REVISION:
                completed_statuses.append("needs_revision")
    mgr.mutate = _track_mutate
    orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))
    sem = asyncio.Semaphore(1)
    spec = _make_task_spec("t1", "src/never_created.tsx")
    with patch(f"{_ORCH}.ACPClient") as mock_acp, \
         patch(f"{_ORCH}.review_output", _approved_review_mock()):
        mock_acp.return_value = _make_mock_acp_client()
        await orch._run_agent_loop(spec, sem, max_revisions=1)
    assert "needs_revision" in completed_statuses
```

Run to confirm RED: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestFileExistenceGate -v`
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestFileExistenceGate -v 2>&1 | tail -20</automated>
  </verify>
  <done>All 4 TestFileExistenceGate tests collected and FAILING (RED) — test class exists in file, no import errors, failures are due to missing implementation not syntax errors.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement file existence gate in orchestrator.py</name>
  <files>packages/conductor-core/src/conductor/orchestrator/orchestrator.py</files>
  <behavior>
    - After `final_verdict = verdict` (line 686), if `verdict.approved` is True AND `task_spec.target_file` is non-empty AND the file does not exist at `Path(self._repo_path) / task_spec.target_file`, replace `verdict` AND `final_verdict` with a synthetic `ReviewVerdict(approved=False, ...)` before the `if verdict.approved: break` check
    - The synthetic verdict's `revision_instructions` must contain both "target file" and "not created" (so the existing send logic forwards it to the agent as a revision message)
    - `revision_num = 0` safety initializer at line 629 must not be removed
    - The `review_only` branch (lines 699-714) must not be touched
    - The post-loop state mutation (lines 716-731) must not be touched — it already handles NEEDS_REVISION correctly
  </behavior>
  <action>
Edit `orchestrator.py`. The only change is inside the `if not review_only:` branch, replacing lines 686-695 with the file gate block.

**Exact replacement for lines 686-695:**

BEFORE (lines 686-695):
```python
                            final_verdict = verdict

                            if verdict.approved:
                                break

                            if revision_num < max_revisions:
                                await client.send(
                                    f"Revision needed:\n{verdict.revision_instructions}"
                                    "\n\nPlease revise your implementation."
                                )
```

AFTER:
```python
                            final_verdict = verdict

                            # File existence gate (VRFY-01): if the reviewer
                            # approves but the target file is absent, override
                            # to non-approved so the revision loop retries.
                            if verdict.approved and task_spec.target_file:
                                target_path = (
                                    Path(self._repo_path) / task_spec.target_file
                                )
                                if not target_path.exists():
                                    verdict = ReviewVerdict(
                                        approved=False,
                                        quality_issues=[
                                            "Target file was not created on disk"
                                        ],
                                        revision_instructions=(
                                            f"The target file "
                                            f"{task_spec.target_file} was not "
                                            "created. Please create it."
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

`ReviewVerdict` is already imported at line 28. `Path` is already imported at line 14. No new imports needed.

After editing, run GREEN check: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestFileExistenceGate -v`

Then run full orchestrator suite to confirm no regressions: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v`
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v 2>&1 | tail -30</automated>
  </verify>
  <done>All TestFileExistenceGate tests PASS (GREEN). All pre-existing orchestrator tests still PASS. No FAILED or ERROR lines in output.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Write failing tests for post-run build check (TestPostRunBuild)</name>
  <files>packages/conductor-core/tests/test_orchestrator.py</files>
  <behavior>
    - test_build_command_runs_after_tasks: Orchestrator(build_command="echo ok") -> asyncio.create_subprocess_shell called once with ("echo ok", cwd=str(tmp_path), stdout=PIPE, stderr=PIPE) after tasks complete
    - test_no_build_command_skips_check: Orchestrator() with no build_command -> asyncio.create_subprocess_shell never called
    - test_build_failure_logged: proc.returncode=1, stderr=b"error: missing module" -> orch.run() completes without raising (build failure is logged, not propagated)
    - test_build_runs_after_resume: all tasks already COMPLETED in state, Orchestrator(build_command="echo ok").resume() -> subprocess called once
  </behavior>
  <action>
Append `TestPostRunBuild` class to `test_orchestrator.py` after `TestFileExistenceGate`. Patch `asyncio.create_subprocess_shell` (not a module-level import, patch it at the asyncio namespace level).

**test_build_command_runs_after_tasks pattern:**
```python
@pytest.mark.asyncio
async def test_build_command_runs_after_tasks(self, tmp_path):
    from conductor.orchestrator.orchestrator import Orchestrator
    tasks = [_make_task_spec("t1", "src/a.py")]
    plan = _make_plan(tasks)
    mgr = _make_state_manager()
    mock_decomposer = AsyncMock()
    mock_decomposer.decompose = AsyncMock(return_value=plan)
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"ok", b""))
    proc.returncode = 0
    with patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer), \
         patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: _make_mock_acp_client()), \
         patch(f"{_ORCH}.review_output", _approved_review_mock()), \
         patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=proc) as mock_proc:
        orch = Orchestrator(
            state_manager=mgr, repo_path=str(tmp_path), build_command="echo ok"
        )
        await orch.run("test feature")
    mock_proc.assert_called_once_with(
        "echo ok",
        cwd=str(tmp_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
```

**test_build_runs_after_resume pattern:**
```python
@pytest.mark.asyncio
async def test_build_runs_after_resume(self, tmp_path):
    from conductor.orchestrator.orchestrator import Orchestrator
    from conductor.state.models import ConductorState, Task, TaskStatus
    state = ConductorState(tasks=[
        Task(id="t1", title="Done", description="d",
             status=TaskStatus.COMPLETED, target_file="/tmp/f1.txt"),
    ])
    mgr = _make_state_manager()
    mgr.read_state = MagicMock(return_value=state)
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(b"ok", b""))
    proc.returncode = 0
    with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=proc) as mock_proc:
        orch = Orchestrator(
            state_manager=mgr, repo_path=str(tmp_path), build_command="echo ok"
        )
        await orch.resume()
    mock_proc.assert_called_once()
```

Run to confirm RED: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestPostRunBuild -v`
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestPostRunBuild -v 2>&1 | tail -20</automated>
  </verify>
  <done>All 4 TestPostRunBuild tests collected and FAILING (RED) — failures are `TypeError: __init__() got an unexpected keyword argument 'build_command'` or similar, not syntax errors.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: Implement build_command parameter and _post_run_build_check</name>
  <files>packages/conductor-core/src/conductor/orchestrator/orchestrator.py</files>
  <behavior>
    - Orchestrator.__init__ accepts build_command: str | None = None, stores as self._build_command
    - New private method _post_run_build_check() -> bool: if no command return True; otherwise run via asyncio.create_subprocess_shell with cwd=self._repo_path, stdout=PIPE, stderr=PIPE; await communicate(); log error on non-zero returncode; never raise
    - run() calls await self._post_run_build_check() as the last line (after the straggler gather)
    - resume() calls await self._post_run_build_check() as the last line (after the straggler gather)
  </behavior>
  <action>
Three edits to `orchestrator.py`:

**Edit 1 — __init__ signature (line 117), add `build_command` param after `max_revisions`:**
```python
    def __init__(
        self,
        state_manager: StateManager,
        repo_path: str,
        mode: str = "auto",
        human_out: asyncio.Queue | None = None,
        human_in: asyncio.Queue | None = None,
        max_agents: int = 10,
        max_revisions: int = 2,
        build_command: str | None = None,
    ) -> None:
```
And in the body, after `self._max_revisions = max_revisions`, add:
```python
        self._build_command = build_command
```

**Edit 2 — Add _post_run_build_check method** after `_run_agent_loop` (before `_make_add_tasks_fn` at line 733):
```python
    async def _post_run_build_check(self) -> bool:
        """Run the optional build_command and log results (never raises).

        Returns:
            True if build passed or no command is configured, False on failure.
        """
        if not self._build_command:
            return True

        logger.info("Running post-run build check: %s", self._build_command)
        proc = await asyncio.create_subprocess_shell(
            self._build_command,
            cwd=self._repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info("Build check passed")
            return True

        logger.error(
            "Build check failed (exit %d):\n%s",
            proc.returncode,
            stderr.decode(errors="replace"),
        )
        return False
```

**Edit 3 — Add tail call in run() and resume():**

In `run()`, after the straggler gather (current line ~226):
```python
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)

        await self._post_run_build_check()
```

In `resume()`, after the straggler gather (current line ~430):
```python
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)

        await self._post_run_build_check()
```

Run GREEN check: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestPostRunBuild -v`

Then full suite: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v`
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v 2>&1 | tail -30</automated>
  </verify>
  <done>All TestPostRunBuild tests PASS. All pre-existing tests still PASS. Full test_orchestrator.py suite green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 5: Write failing CLI tests then wire --build-command through run.py</name>
  <files>packages/conductor-core/tests/test_run_command.py, packages/conductor-core/src/conductor/cli/commands/run.py</files>
  <behavior>
    - test_build_command_passed_to_orchestrator: _run_async(..., build_command="npx tsc --noEmit") -> Orchestrator instantiated with build_command="npx tsc --noEmit"
    - test_no_build_command_default: _run_async(...) without build_command -> Orchestrator instantiated with build_command=None (or key absent)
  </behavior>
  <action>
**Step 1 — Write failing tests in test_run_command.py:**

Append `TestRunBuildCommand` class after `TestRunResume`:
```python
class TestRunBuildCommand:
    """Tests for --build-command flag on conductor run."""

    @pytest.mark.asyncio
    async def test_build_command_passed_to_orchestrator(self, tmp_path):
        """--build-command value should be forwarded to Orchestrator constructor."""
        from conductor.cli.commands.run import _run_async

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.run_auto = AsyncMock()

            await _run_async(
                "desc", auto=True, repo=tmp_path,
                build_command="npx tsc --noEmit",
            )

            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") == "npx tsc --noEmit"

    @pytest.mark.asyncio
    async def test_no_build_command_default(self, tmp_path):
        """Without --build-command, Orchestrator receives build_command=None."""
        from conductor.cli.commands.run import _run_async

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.run_auto = AsyncMock()

            await _run_async("desc", auto=True, repo=tmp_path)

            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") is None
```

Confirm RED: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_run_command.py::TestRunBuildCommand -v`

**Step 2 — Implement in run.py:**

Update the `run()` function signature (line 23) to add `build_command` option:
```python
def run(
    description: str = typer.Argument(None, help="Feature description"),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Run mode"),
    repo: str = typer.Option(".", "--repo", help="Path to repo root"),
    resume: bool = typer.Option(False, "--resume", help="Resume interrupted orchestration from state.json"),
    build_command: str = typer.Option(None, "--build-command", help="Shell command to verify build after orchestration (e.g. 'npx tsc --noEmit')"),
    dashboard_port: int = typer.Option(None, "--dashboard-port", help="Start dashboard server on this port"),
) -> None:
```

Update the `asyncio.run(...)` call (line 34) to pass `build_command`:
```python
    asyncio.run(_run_async(
        description or "",
        auto=auto,
        repo=Path(repo).resolve(),
        resume=resume,
        build_command=build_command,
        dashboard_port=dashboard_port,
    ))
```

Update `_run_async` signature (line 43) to accept `build_command`:
```python
async def _run_async(
    description: str,
    *,
    auto: bool,
    repo: Path,
    resume: bool = False,
    build_command: str | None = None,
    dashboard_port: int | None = None,
) -> None:
```

Update the `Orchestrator(...)` instantiation (line 59) to pass `build_command`:
```python
    orchestrator = Orchestrator(
        state_manager=state_manager,
        repo_path=str(repo),
        mode="auto" if auto else "interactive",
        human_out=human_out,
        human_in=human_in,
        build_command=build_command,
    )
```

Run GREEN: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/test_run_command.py -v`

Run full suite: `cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/ -v`
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/ -v 2>&1 | tail -30</automated>
  </verify>
  <done>All TestRunBuildCommand tests PASS. Full test suite (all test files) green. No FAILED or ERROR lines.</done>
</task>

</tasks>

<verification>
After all tasks complete, run the full test suite:

```
cd /home/huypham/code/digest/claude-auto/packages/conductor-core && uv run python -m pytest tests/ -v
```

Requirement coverage check:
- VRFY-01: `TestFileExistenceGate::test_missing_file_triggers_revision` — missing file forces retry via revision message
- QUAL-01: `TestFileExistenceGate::test_missing_file_triggers_revision` — agent receives `revision_instructions` string, not a raw boolean
- QUAL-02: `TestFileExistenceGate::test_missing_file_exhausts_revisions` — exhausted retries produce `review_status=NEEDS_REVISION`, never silently approved

Success criterion check:
1. Agent session ends + target_file absent + file does not exist -> revision message sent, loop re-enters: `test_missing_file_triggers_revision` PASS
2. File still missing after all revision attempts -> `NEEDS_REVISION`, not silently completed: `test_missing_file_exhausts_revisions` PASS
3. Reviewer returns structured `ReviewVerdict` with `revision_instructions` string -> agent receives it via `client.send()`: covered by existing `TestOrch05RevisionSend` + new gate tests
4. Max revision rounds reached without approval -> `NEEDS_REVISION` with reviewer's last reason: `test_missing_file_exhausts_revisions` PASS
5. Max revision rounds is configurable via `Orchestrator(max_revisions=N)`: already true pre-phase; `test_loop_runs_max_revisions_plus_one_iterations` confirms it; new tests call `_run_agent_loop(spec, sem, max_revisions=1)` explicitly
</verification>

<success_criteria>
- `uv run python -m pytest tests/test_orchestrator.py::TestFileExistenceGate -v` — 4/4 PASSED
- `uv run python -m pytest tests/test_orchestrator.py::TestPostRunBuild -v` — 4/4 PASSED
- `uv run python -m pytest tests/test_run_command.py::TestRunBuildCommand -v` — 2/2 PASSED
- `uv run python -m pytest tests/ -v` — full suite green, zero regressions
- `orchestrator.py` contains `target_path.exists()` inside the revision loop
- `orchestrator.py` contains `_post_run_build_check` method using `asyncio.create_subprocess_shell`
- `run.py` `_run_async` accepts `build_command: str | None = None` and passes it to `Orchestrator`
</success_criteria>

<output>
After all tasks complete and the full test suite is green, create `.planning/phases/24/24-01-SUMMARY.md` with:
- What was implemented (file gate logic with exact line reference, _post_run_build_check, CLI flag)
- Key decisions made (gate placement between line 686 and 688, synthetic verdict pattern, build failures logged not raised)
- Test class names and counts
- Any deviations from this plan
</output>
