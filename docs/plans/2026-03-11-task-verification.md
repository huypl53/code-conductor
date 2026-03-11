# Task Verification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a per-task file existence gate that forces agent retries when the target file is missing, plus a post-run build verification command that catches cross-file integration errors.

**Architecture:** Layer 1 inserts a file existence check inside the existing revision loop in `_run_agent_loop` — if the file is missing after the agent finishes, it sends a revision message and retries. Layer 2 adds an optional `build_command` that runs after all tasks complete in `run()` and `resume()`.

**Tech Stack:** Python, asyncio, asyncio.subprocess, Pydantic, Typer

---

### Task 1: Add file existence gate in `_run_agent_loop`

**Files:**
- Modify: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py:675-697`
- Test: `packages/conductor-core/tests/test_orchestrator.py`

**Step 1: Write the failing tests**

```python
# In test_orchestrator.py — add to a new class

class TestFileExistenceGate:
    """Verify agent retries when target file is missing after execution."""

    @pytest.mark.asyncio
    async def test_missing_file_triggers_revision(self, tmp_path):
        """If target file doesn't exist after agent run, agent should get revision message."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        sem = asyncio.Semaphore(1)
        # Target file that will never exist
        spec = _make_task_spec("t1", "src/missing.tsx")

        revision_sent = False

        def _acp_factory(**kwargs):
            client = _make_mock_acp_client()
            original_send = client.send

            async def _track_send(msg):
                nonlocal revision_sent
                if "target file" in msg.lower() and "not created" in msg.lower():
                    revision_sent = True
                    # Create the file on the "second attempt" so the loop terminates
                    (tmp_path / "src").mkdir(parents=True, exist_ok=True)
                    (tmp_path / "src" / "missing.tsx").write_text("export default 1;")
                return await original_send(msg)

            client.send = _track_send
            return client

        with patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory), \
             patch(f"{_ORCH}.review_output", _approved_review_mock()):
            await orch._run_agent_loop(spec, sem, max_revisions=2)

        assert revision_sent, "Should have sent revision about missing file"

    @pytest.mark.asyncio
    async def test_existing_file_no_revision(self, tmp_path):
        """If target file exists after agent run, no extra revision needed."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        sem = asyncio.Semaphore(1)
        # Create the file so it exists
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "exists.tsx").write_text("export default 1;")
        spec = _make_task_spec("t1", "src/exists.tsx")

        with patch(f"{_ORCH}.ACPClient") as mock_acp, \
             patch(f"{_ORCH}.review_output", _approved_review_mock()):
            mock_acp.return_value = _make_mock_acp_client()
            await orch._run_agent_loop(spec, sem)

        # Task should complete without extra revision — mutate called for
        # add_agent + complete_task = 2
        assert mgr.mutate.call_count == 2

    @pytest.mark.asyncio
    async def test_missing_file_exhausts_revisions(self, tmp_path):
        """If file never appears after all retries, task marked NEEDS_REVISION."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, ReviewStatus

        state = ConductorState()
        mgr = _make_state_manager()
        # Track what complete_task_fn gets called with
        completed_statuses = []
        original_mutate = mgr.mutate

        def _track_mutate(fn):
            fn(state)
            # Check if any task got NEEDS_REVISION
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

    @pytest.mark.asyncio
    async def test_empty_target_file_skips_check(self, tmp_path):
        """Tasks with no target_file should skip the existence check."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        sem = asyncio.Semaphore(1)
        spec = _make_task_spec("t1", "")  # No target file

        with patch(f"{_ORCH}.ACPClient") as mock_acp, \
             patch(f"{_ORCH}.review_output", _approved_review_mock()):
            mock_acp.return_value = _make_mock_acp_client()
            await orch._run_agent_loop(spec, sem)

        # Should complete normally — mutate called for add_agent + complete_task
        assert mgr.mutate.call_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestFileExistenceGate -v`
Expected: FAIL — no file existence check exists yet

**Step 3: Add file existence gate after review loop**

In `orchestrator.py`, modify the revision loop inside `_run_agent_loop` (the `if not review_only:` branch). After the review verdict check, add a file existence gate. Replace lines 675-697:

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

                            # File existence gate: override verdict if target
                            # file was not created on disk
                            if (
                                verdict.approved
                                and task_spec.target_file
                            ):
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
                                            f"The target file {task_spec.target_file} "
                                            "was not created. Please create it."
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

**Step 4: Run tests to verify they pass**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestFileExistenceGate -v`
Expected: All 4 tests PASS

**Step 5: Run full orchestrator test suite**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add packages/conductor-core/src/conductor/orchestrator/orchestrator.py packages/conductor-core/tests/test_orchestrator.py
git commit -m "feat: add file existence gate in agent loop — retry if target file missing"
```

---

### Task 2: Add `build_command` parameter to Orchestrator

**Files:**
- Modify: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py:108-141` (init), lines after `run()` and `resume()` spawn loops
- Test: `packages/conductor-core/tests/test_orchestrator.py`

**Step 1: Write the failing tests**

```python
# In test_orchestrator.py — add new class

class TestPostRunBuild:
    """Verify post-run build command execution."""

    @pytest.mark.asyncio
    async def test_build_command_runs_after_tasks(self, tmp_path):
        """build_command should run after all tasks complete."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        mgr = _make_state_manager()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        with patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer), \
             patch(f"{_ORCH}.ACPClient") as mock_acp, \
             patch(f"{_ORCH}.review_output", _approved_review_mock()), \
             patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
            mock_acp.return_value = _make_mock_acp_client()
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            orch = Orchestrator(
                state_manager=mgr,
                repo_path=str(tmp_path),
                build_command="echo ok",
            )
            await orch.run("test feature")

        mock_proc.assert_called_once_with(
            "echo ok",
            cwd=str(tmp_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    @pytest.mark.asyncio
    async def test_no_build_command_skips_check(self, tmp_path):
        """Without build_command, no subprocess should run."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        mgr = _make_state_manager()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        with patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer), \
             patch(f"{_ORCH}.ACPClient") as mock_acp, \
             patch(f"{_ORCH}.review_output", _approved_review_mock()), \
             patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
            mock_acp.return_value = _make_mock_acp_client()

            orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))
            await orch.run("test feature")

        mock_proc.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_failure_logged(self, tmp_path):
        """Failed build should log error but not raise."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        mgr = _make_state_manager()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        with patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer), \
             patch(f"{_ORCH}.ACPClient") as mock_acp, \
             patch(f"{_ORCH}.review_output", _approved_review_mock()), \
             patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
            mock_acp.return_value = _make_mock_acp_client()
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"", b"error: missing module"))
            proc.returncode = 1
            mock_proc.return_value = proc

            orch = Orchestrator(
                state_manager=mgr,
                repo_path=str(tmp_path),
                build_command="tsc --noEmit",
            )
            # Should not raise
            await orch.run("test feature")

    @pytest.mark.asyncio
    async def test_build_runs_after_resume(self, tmp_path):
        """build_command should also run after resume()."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        state = ConductorState(tasks=[
            Task(id="t1", title="Done", description="d",
                 status=TaskStatus.COMPLETED, target_file="/tmp/f1.txt"),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)

        with patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
            proc = AsyncMock()
            proc.communicate = AsyncMock(return_value=(b"ok", b""))
            proc.returncode = 0
            mock_proc.return_value = proc

            orch = Orchestrator(
                state_manager=mgr,
                repo_path=str(tmp_path),
                build_command="echo ok",
            )
            await orch.resume()

        mock_proc.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestPostRunBuild -v`
Expected: FAIL — `build_command` parameter doesn't exist yet

**Step 3: Add `build_command` to Orchestrator.__init__ and _post_run_build_check**

In `orchestrator.py`, modify `__init__` to accept `build_command`:

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
        # ... existing assignments ...
        self._build_command = build_command
```

Add a new private method after `_run_agent_loop`:

```python
    async def _post_run_build_check(self) -> bool:
        """Run the configured build command and report results.

        Returns True if build passed (or no command configured), False on failure.
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

Add call at the end of `run()` (after the spawn loop, line ~226):

```python
        # Wait for any stragglers (shouldn't normally happen)
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)

        await self._post_run_build_check()
```

Add call at the end of `resume()` (after the spawn loop, line ~430):

```python
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)

        await self._post_run_build_check()
```

**Step 4: Run tests to verify they pass**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestPostRunBuild -v`
Expected: All 4 tests PASS

**Step 5: Run full orchestrator test suite**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add packages/conductor-core/src/conductor/orchestrator/orchestrator.py packages/conductor-core/tests/test_orchestrator.py
git commit -m "feat: add optional build_command for post-run build verification"
```

---

### Task 3: Add `--build-command` flag to CLI

**Files:**
- Modify: `packages/conductor-core/src/conductor/cli/commands/run.py`
- Modify: `packages/conductor-core/src/conductor/cli/delegation.py` (pass through on resume)
- Test: `packages/conductor-core/tests/test_run_command.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_run_command.py

class TestRunBuildCommand:
    """Tests for --build-command flag."""

    @pytest.mark.asyncio
    async def test_build_command_passed_to_orchestrator(self, tmp_path):
        """--build-command should be forwarded to Orchestrator."""
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

            # Check Orchestrator was created with build_command
            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") == "npx tsc --noEmit"

    @pytest.mark.asyncio
    async def test_no_build_command_default(self, tmp_path):
        """Without --build-command, Orchestrator should get None."""
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

**Step 2: Run tests to verify they fail**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_run_command.py::TestRunBuildCommand -v`
Expected: FAIL — `_run_async` doesn't accept `build_command` yet

**Step 3: Add `--build-command` to run command**

In `run.py`, add the flag to `run()`:

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

Pass through in the `asyncio.run` call and `_run_async` signature:

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

Pass to Orchestrator constructor:

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

**Step 4: Run tests to verify they pass**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_run_command.py -v`
Expected: All tests PASS

**Step 5: Run full test suite**

Run: `cd packages/conductor-core && uv run python -m pytest tests/ -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add packages/conductor-core/src/conductor/cli/commands/run.py packages/conductor-core/tests/test_run_command.py
git commit -m "feat: add --build-command flag to conductor run for post-run verification"
```
