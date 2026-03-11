# Resume Support Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `conductor run --resume` and `/resume` TUI command so interrupted orchestration can pick up where it left off, plus move reviews outside the semaphore to eliminate the bottleneck that caused the need to kill in the first place.

**Architecture:** Read persisted `state.json` to reconstruct the dependency scheduler. Completed tasks get pre-marked as `done()`. In-progress tasks check if their target file exists on disk: if yes, run review only; if no, re-run agent from scratch. Pending tasks run normally. Reviews run outside the semaphore.

**Tech Stack:** Python, asyncio, graphlib.TopologicalSorter, Pydantic, Typer, prompt_toolkit

---

### Task 1: Refactor semaphore scope in `_run_agent_loop`

**Files:**
- Modify: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py:518-644`
- Test: `packages/conductor-core/tests/test_orchestrator.py`

**Step 1: Write the failing test**

```python
# In test_orchestrator.py — add to existing test file

class TestSemaphoreScope:
    """Verify review runs outside the semaphore."""

    @pytest.mark.asyncio
    async def test_semaphore_released_before_review(self):
        """Semaphore should be released after agent execution, before review."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path="/tmp/test")

        sem = asyncio.Semaphore(1)
        semaphore_available_during_review = False

        original_review = None

        async def mock_review(**kwargs):
            nonlocal semaphore_available_during_review
            # If we can acquire the semaphore, it was released before review
            semaphore_available_during_review = sem._value > 0
            return ReviewVerdict(approved=True, revision_instructions="")

        spec = _make_task_spec("t1", "/tmp/test/file.txt")

        with patch.object(orch, '_state', mgr), \
             patch("conductor.orchestrator.orchestrator.ACPClient") as mock_acp, \
             patch("conductor.orchestrator.orchestrator.review_output", side_effect=mock_review):
            client = _make_mock_acp_client()
            mock_acp.return_value = client
            await orch._run_agent_loop(spec, sem)

        assert semaphore_available_during_review, \
            "Semaphore should be available (released) when review runs"
```

**Step 2: Run test to verify it fails**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestSemaphoreScope -v`
Expected: FAIL — semaphore is held during review in current code

**Step 3: Refactor `_run_agent_loop` to release semaphore before review**

In `orchestrator.py`, change `_run_agent_loop` so the `async with sem:` only wraps the ACPClient agent execution block, and the review runs after the semaphore is released:

```python
async def _run_agent_loop(
    self,
    task_spec: TaskSpec,
    sem: asyncio.Semaphore,
    max_revisions: int | None = None,
    resume_session_id: str | None = None,
    review_only: bool = False,
) -> None:
    if max_revisions is None:
        max_revisions = self._max_revisions

    agent_id = f"agent-{task_spec.id}-{uuid.uuid4().hex[:8]}"
    identity = AgentIdentity(
        name=agent_id,
        role=task_spec.role,
        target_file=task_spec.target_file,
        material_files=task_spec.material_files,
        task_id=task_spec.id,
        task_description=task_spec.description,
    )
    system_prompt = build_system_prompt(identity)

    # Write AgentRecord to state before opening session
    await asyncio.to_thread(
        self._state.mutate,
        self._make_add_agent_fn(agent_id, task_spec),
    )

    final_verdict: ReviewVerdict | None = None
    revision_num = 0

    if not review_only:
        # --- Agent execution (holds semaphore) ---
        async with sem:
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
                self._active_clients[agent_id] = client
                try:
                    if client._sdk_client is not None:
                        try:
                            server_info = (
                                await client._sdk_client.get_server_info()
                            )
                            if server_info and "session_id" in server_info:
                                session_id = server_info["session_id"]
                                self._session_registry.register(
                                    agent_id, session_id
                                )
                                self._session_registry.save(self._sessions_path)
                                await asyncio.to_thread(
                                    self._state.mutate,
                                    self._make_save_session_fn(
                                        agent_id, session_id
                                    ),
                                )
                        except Exception:  # noqa: BLE001
                            logger.debug(
                                "get_server_info() unavailable for agent %s",
                                agent_id,
                            )

                    await client.send(
                        f"Task {task_spec.id}: {task_spec.description}"
                    )

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
                finally:
                    self._active_clients.pop(agent_id, None)
        # --- Semaphore released here ---
    else:
        # --- Review only (no semaphore needed) ---
        final_verdict = await review_output(
            task_description=task_spec.description,
            target_file=task_spec.target_file,
            agent_summary="(resumed — file already exists on disk)",
            repo_path=self._repo_path,
        )

    # Update state with review result (runs without semaphore)
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

Note: The review still runs inside the semaphore when an agent is active (revision loop needs the client open). The key change is that `review_only=True` skips the semaphore entirely, and the final state update always runs outside it.

**Step 4: Run test to verify it passes**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestSemaphoreScope -v`
Expected: PASS

**Step 5: Run full orchestrator test suite**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v`
Expected: All existing tests PASS

**Step 6: Commit**

```bash
git add packages/conductor-core/src/conductor/orchestrator/orchestrator.py packages/conductor-core/tests/test_orchestrator.py
git commit -m "refactor: release semaphore before review in agent loop, add review_only mode"
```

---

### Task 2: Add `Orchestrator.resume()` with full scheduler reconstruction

**Files:**
- Modify: `packages/conductor-core/src/conductor/orchestrator/orchestrator.py:297-371`
- Test: `packages/conductor-core/tests/test_orchestrator.py`

**Step 1: Write the failing tests**

```python
# In test_orchestrator.py

class TestResume:
    """Tests for Orchestrator.resume() with full scheduler reconstruction."""

    @pytest.mark.asyncio
    async def test_resume_skips_completed_tasks(self):
        """Completed tasks should not be re-run."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        state = ConductorState(tasks=[
            Task(id="t1", title="Done", description="d", status=TaskStatus.COMPLETED,
                 target_file="/tmp/f1.txt"),
            Task(id="t2", title="Pending", description="d", status=TaskStatus.PENDING,
                 target_file="/tmp/f2.txt", requires=["t1"]),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path="/tmp/test")

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        # Only t2 should run, not t1
        assert mock_loop.call_count == 1
        called_spec = mock_loop.call_args_list[0][0][0]
        assert called_spec.id == "t2"

    @pytest.mark.asyncio
    async def test_resume_review_only_when_file_exists(self):
        """In-progress tasks with existing target file should run review_only."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        state = ConductorState(tasks=[
            Task(id="t1", title="InProg", description="d",
                 status=TaskStatus.IN_PROGRESS,
                 target_file="/tmp/existing_file.txt"),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path="/tmp/test")

        with patch("pathlib.Path.exists", return_value=True), \
             patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        assert mock_loop.call_count == 1
        # Check review_only=True was passed
        assert mock_loop.call_args_list[0][1].get("review_only") is True

    @pytest.mark.asyncio
    async def test_resume_reruns_agent_when_file_missing(self):
        """In-progress tasks with no target file should re-run agent."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        state = ConductorState(tasks=[
            Task(id="t1", title="InProg", description="d",
                 status=TaskStatus.IN_PROGRESS,
                 target_file="/tmp/missing_file.txt"),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path="/tmp/test")

        with patch("pathlib.Path.exists", return_value=False), \
             patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        assert mock_loop.call_count == 1
        assert mock_loop.call_args_list[0][1].get("review_only", False) is False

    @pytest.mark.asyncio
    async def test_resume_respects_dependencies(self):
        """Pending task blocked by in-progress task should wait."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        call_order = []

        state = ConductorState(tasks=[
            Task(id="t1", title="InProg", description="d",
                 status=TaskStatus.IN_PROGRESS,
                 target_file="/tmp/f1.txt"),
            Task(id="t2", title="Pending", description="d",
                 status=TaskStatus.PENDING,
                 target_file="/tmp/f2.txt", requires=["t1"]),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path="/tmp/test")

        async def track_call(spec, sem, **kwargs):
            call_order.append(spec.id)

        with patch("pathlib.Path.exists", return_value=True), \
             patch.object(orch, '_run_agent_loop', side_effect=track_call):
            await orch.resume()

        assert call_order == ["t1", "t2"]

    @pytest.mark.asyncio
    async def test_resume_noop_when_all_completed(self):
        """Resume with all tasks completed should be a no-op."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        state = ConductorState(tasks=[
            Task(id="t1", title="Done", description="d",
                 status=TaskStatus.COMPLETED, target_file="/tmp/f1.txt"),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path="/tmp/test")

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        mock_loop.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_no_state_file(self):
        """Resume with empty state should be a no-op."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=ConductorState())
        orch = Orchestrator(state_manager=mgr, repo_path="/tmp/test")

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        mock_loop.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestResume -v`
Expected: FAIL — current `resume()` doesn't use scheduler or handle pending/review_only

**Step 3: Rewrite `Orchestrator.resume()`**

Replace the existing `resume()` method (lines 297-371) with:

```python
async def resume(self) -> None:
    """Resume an interrupted orchestration from persisted state.

    Reads state.json and reconstructs the dependency scheduler:
    - Completed tasks: skipped (pre-marked as done in scheduler)
    - In-progress tasks with target file on disk: review only
    - In-progress tasks without target file: re-run agent from scratch
    - Pending tasks: run normally via scheduler

    Uses the same FIRST_COMPLETED spawn loop as run().
    """
    state = await asyncio.to_thread(self._state.read_state)

    if not state.tasks:
        return

    # Ensure .memory/ exists
    memory_dir = Path(self._repo_path) / ".memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    # Build agent_id -> agent record map
    agent_map = {a.id: a for a in state.agents}

    # Reconstruct dependency graph from persisted tasks
    dep_graph: dict[str, set[str]] = {}
    for t in state.tasks:
        dep_graph[t.id] = set(t.requires)

    scheduler = DependencyScheduler(dep_graph)

    # Pre-mark completed tasks as done
    completed_ids = {
        t.id for t in state.tasks
        if t.status == TaskStatus.COMPLETED
    }
    for cid in completed_ids:
        scheduler.done(cid)

    # Determine how to handle each non-completed task
    task_mode: dict[str, bool] = {}  # task_id -> review_only
    for t in state.tasks:
        if t.id in completed_ids:
            continue
        if t.status == TaskStatus.IN_PROGRESS:
            # Check if target file exists on disk
            target = Path(t.target_file)
            if not target.is_absolute():
                target = Path(self._repo_path) / target
            task_mode[t.id] = target.exists()
        else:
            task_mode[t.id] = False  # pending: full agent run

    # Build TaskSpec lookup from state
    task_specs: dict[str, TaskSpec] = {}
    for t in state.tasks:
        if t.id in completed_ids:
            continue
        agent_id = t.assigned_agent
        role = "developer"
        if agent_id and agent_id in agent_map:
            role = agent_map[agent_id].role
        task_specs[t.id] = TaskSpec(
            id=t.id,
            title=t.title,
            description=t.description,
            role=role,
            target_file=t.target_file,
            material_files=t.material_files,
            requires=t.requires,
            produces=t.produces,
        )

    if not task_specs:
        return

    # Effective concurrency cap
    sem = asyncio.Semaphore(self._max_agents)
    self._semaphore = sem

    # Spawn loop (same pattern as run())
    pending: dict[str, asyncio.Task] = {}

    while scheduler.is_active():
        ready_ids = scheduler.get_ready()

        for task_id in ready_ids:
            if task_id in completed_ids:
                scheduler.done(task_id)
                continue
            if task_id not in pending and task_id in task_specs:
                review_only = task_mode.get(task_id, False)
                t = asyncio.create_task(
                    self._run_agent_loop(
                        task_specs[task_id],
                        sem,
                        review_only=review_only,
                    )
                )
                pending[task_id] = t
                self._active_tasks[task_id] = t

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
            scheduler.done(completed_id)

    if pending:
        await asyncio.gather(*pending.values())
```

**Step 4: Run tests to verify they pass**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py::TestResume -v`
Expected: All 6 tests PASS

**Step 5: Run full orchestrator test suite**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_orchestrator.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add packages/conductor-core/src/conductor/orchestrator/orchestrator.py packages/conductor-core/tests/test_orchestrator.py
git commit -m "feat: rewrite Orchestrator.resume() with full scheduler reconstruction and review_only mode"
```

---

### Task 3: Add `--resume` flag to `conductor run`

**Files:**
- Modify: `packages/conductor-core/src/conductor/cli/commands/run.py`
- Test: `packages/conductor-core/tests/test_run_command.py` (create)

**Step 1: Write the failing test**

```python
# tests/test_run_command.py
"""Tests for conductor run command resume flag."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunResume:
    """Tests for --resume flag on conductor run."""

    @pytest.mark.asyncio
    async def test_resume_calls_orchestrator_resume(self):
        """--resume should call orchestrator.resume() instead of run_auto()."""
        from conductor.cli.commands.run import _run_async
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".conductor").mkdir()
            # Create a dummy state.json
            (repo / ".conductor" / "state.json").write_text('{"version":"1","tasks":[]}')

            with patch("conductor.cli.commands.run.Orchestrator") as MockOrch:
                mock_orch = MockOrch.return_value
                mock_orch.resume = AsyncMock()
                mock_orch.run_auto = AsyncMock()

                await _run_async("ignored", auto=True, repo=repo, resume=True)

                mock_orch.resume.assert_called_once()
                mock_orch.run_auto.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_resume_calls_run_auto(self):
        """Without --resume, should call run_auto() as before."""
        from conductor.cli.commands.run import _run_async
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            with patch("conductor.cli.commands.run.Orchestrator") as MockOrch:
                mock_orch = MockOrch.return_value
                mock_orch.resume = AsyncMock()
                mock_orch.run_auto = AsyncMock()
                mock_orch.run = AsyncMock()

                await _run_async("desc", auto=True, repo=repo, resume=False)

                mock_orch.run_auto.assert_called_once_with("desc")
                mock_orch.resume.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_run_command.py -v`
Expected: FAIL — `_run_async` doesn't have `resume` param yet

**Step 3: Add `--resume` flag to run command**

Modify `commands/run.py`:

```python
def run(
    description: str = typer.Argument(None, help="Feature description"),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Run mode"),
    repo: str = typer.Option(".", "--repo", help="Path to repo root"),
    resume: bool = typer.Option(False, "--resume", help="Resume interrupted orchestration from state.json"),
    dashboard_port: int = typer.Option(None, "--dashboard-port", help="Start dashboard server on this port"),
) -> None:
    """Start the orchestrator for a feature description with live agent display."""
    if not resume and not description:
        _console.print("[red]Error: description is required (or use --resume)[/red]")
        raise typer.Exit(1)
    asyncio.run(_run_async(
        description or "",
        auto=auto,
        repo=Path(repo).resolve(),
        resume=resume,
        dashboard_port=dashboard_port,
    ))
```

In `_run_async`, add the `resume` parameter and branch:

```python
async def _run_async(
    description: str,
    *,
    auto: bool,
    repo: Path,
    resume: bool = False,
    dashboard_port: int | None = None,
) -> None:
    # ... existing setup ...

    if resume:
        orch_coro = orchestrator.resume()
    elif auto:
        orch_coro = orchestrator.run_auto(description)
    else:
        orch_coro = orchestrator.run(description)

    orch_task = asyncio.create_task(orch_coro)
    # ... rest unchanged ...
```

**Step 4: Run tests to verify they pass**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_run_command.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add packages/conductor-core/src/conductor/cli/commands/run.py packages/conductor-core/tests/test_run_command.py
git commit -m "feat: add --resume flag to conductor run command"
```

---

### Task 4: Add `/resume` slash command to chat TUI

**Files:**
- Modify: `packages/conductor-core/src/conductor/cli/chat.py:45-50` (SLASH_COMMANDS)
- Modify: `packages/conductor-core/src/conductor/cli/chat.py:235-258` (`_handle_slash_command`)
- Modify: `packages/conductor-core/src/conductor/cli/delegation.py:114` (`handle_delegate` area — add `resume_delegation`)
- Test: `packages/conductor-core/tests/test_chat.py`

**Step 1: Write the failing test**

```python
# Add to tests/test_chat.py TestSlashCommands class

@pytest.mark.asyncio
async def test_resume_command_registered(self) -> None:
    from conductor.cli.chat import SLASH_COMMANDS
    assert "/resume" in SLASH_COMMANDS

@pytest.mark.asyncio
async def test_resume_dispatches_to_delegation_manager(self) -> None:
    session = self._make_session()
    session._delegation_manager = MagicMock()
    session._delegation_manager.resume_delegation = AsyncMock()
    result = await session._handle_slash_command("/resume")
    assert result is False
    session._delegation_manager.resume_delegation.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_chat.py::TestSlashCommands::test_resume_command_registered tests/test_chat.py::TestSlashCommands::test_resume_dispatches_to_delegation_manager -v`
Expected: FAIL

**Step 3: Add `/resume` to SLASH_COMMANDS and dispatch**

In `chat.py`, add to SLASH_COMMANDS dict:

```python
SLASH_COMMANDS: dict[str, str] = {
    "/help": "Show all available slash commands",
    "/exit": "Exit the chat session and restore terminal",
    "/status": "Show active sub-agents (ID, task, elapsed time)",
    "/summarize": "Summarize conversation to free context space",
    "/resume": "Resume interrupted delegation from state.json",
}
```

In `_handle_slash_command`, add the resume case:

```python
if cmd == "/resume":
    await self._delegation_manager.resume_delegation()
    return False
```

**Step 4: Add `resume_delegation()` to DelegationManager**

In `delegation.py`, add method to `DelegationManager`:

```python
async def resume_delegation(self) -> None:
    """Resume interrupted delegation by calling orchestrator.resume()."""
    conductor_dir = Path(self._repo_path) / ".conductor"
    state_path = conductor_dir / "state.json"

    if not state_path.exists():
        self._console.print("[yellow]No state file found — nothing to resume.[/yellow]")
        return

    state_manager = StateManager(state_path)
    state = state_manager.read_state()

    incomplete = [t for t in state.tasks if t.status != "completed"]
    if not incomplete:
        self._console.print("[green]All tasks already completed — nothing to resume.[/green]")
        return

    total = len(state.tasks)
    done = total - len(incomplete)
    self._console.print(
        f"\n[bold cyan]Resuming delegation...[/bold cyan] "
        f"{done}/{total} tasks completed, {len(incomplete)} remaining."
    )

    # Create escalation queues
    self._human_out = asyncio.Queue()
    self._human_in = asyncio.Queue()

    orchestrator = Orchestrator(
        state_manager=state_manager,
        repo_path=self._repo_path,
        mode="interactive",
        human_out=self._human_out,
        human_in=self._human_in,
    )

    run = _DelegationRun(
        task_description="(resumed)",
        orchestrator=orchestrator,
        state_manager=state_manager,
    )
    self._active_run = run

    # Start background status + escalation tasks (same as handle_delegate)
    self._status_task = asyncio.create_task(self._status_updater())
    if self._input_fn is not None:
        self._escalation_task = asyncio.create_task(self._escalation_listener())

    try:
        await orchestrator.resume()

        state = state_manager.read_state()
        done = sum(1 for t in state.tasks if t.status == "completed")
        self._console.print(
            f"\n[bold green]Delegation complete.[/bold green] "
            f"{done}/{len(state.tasks)} tasks finished."
        )
    except Exception as exc:
        self._console.print(f"\n[red]Resume failed: {exc}[/red]")
    finally:
        self._cancel_background_tasks()
        self._active_run = None
```

**Step 5: Run tests to verify they pass**

Run: `cd packages/conductor-core && uv run python -m pytest tests/test_chat.py::TestSlashCommands -v`
Expected: PASS

**Step 6: Run full test suite**

Run: `cd packages/conductor-core && uv run python -m pytest tests/ -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add packages/conductor-core/src/conductor/cli/chat.py packages/conductor-core/src/conductor/cli/delegation.py packages/conductor-core/tests/test_chat.py
git commit -m "feat: add /resume slash command in chat TUI for resuming delegated work"
```

---

### Task 5: Integration test — resume the calendar app build

**Files:**
- No code changes — manual verification

**Step 1: Resume the calendar app build**

```bash
cd /home/huypham/code/calendar-app
env -u CLAUDECODE uv run --project /home/huypham/code/digest/claude-auto conductor run --resume --repo .
```

**Step 2: Verify it picks up where it left off**

Expected behavior:
- Should print "Resuming: 11/23 completed, 12 remaining" (or similar)
- Should NOT re-decompose the task
- In-progress tasks with files on disk should go straight to review
- Pending tasks should run normally
- All 23 tasks should eventually reach completed

**Step 3: Verify the app builds**

```bash
cd /home/huypham/code/calendar-app && npx tsc --noEmit && npx vite build
```

Expected: Clean build, no TypeScript errors

**Step 4: Commit all fixes**

```bash
git add -A
git commit -m "feat: resume support for conductor run and chat TUI"
```
