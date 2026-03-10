"""ORCH-02/05 tests: Orchestrator class — decompose-validate-schedule-spawn loop."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.orchestrator.errors import FileConflictError
from conductor.orchestrator.models import TaskPlan, TaskSpec
from conductor.orchestrator.reviewer import ReviewVerdict

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_task_spec(
    task_id: str,
    target_file: str,
    requires: list[str] | None = None,
    title: str | None = None,
) -> TaskSpec:
    return TaskSpec(
        id=task_id,
        title=title or f"Task {task_id}",
        description=f"Description for {task_id}",
        role="backend developer",
        target_file=target_file,
        requires=requires or [],
    )


def _make_plan(
    tasks: list[TaskSpec],
    max_agents: int = 4,
) -> TaskPlan:
    return TaskPlan(
        feature_name="TestFeature",
        tasks=tasks,
        max_agents=max_agents,
    )


def _make_state_manager():
    """Return a MagicMock that behaves like StateManager."""
    mgr = MagicMock()
    mgr.mutate = MagicMock(return_value=None)
    return mgr


def _make_mock_acp_client():
    """Return an AsyncMock context manager that behaves like ACPClient."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.send = AsyncMock()

    async def _empty_stream():
        return
        yield

    client.stream_response = MagicMock(side_effect=_empty_stream)
    return client


def _make_mock_acp_client_with_result(result_text: str = "Done"):
    """Return an AsyncMock ACP client whose stream yields a mock ResultMessage."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.send = AsyncMock()

    # Build a fake ResultMessage
    mock_result_msg = MagicMock()
    mock_result_msg.result = result_text

    async def _result_stream():
        yield mock_result_msg

    client.stream_response = MagicMock(side_effect=_result_stream)
    return client


# ---------------------------------------------------------------------------
# Tests: ORCH-02 (existing loop tests)
# ---------------------------------------------------------------------------

_ORCH = "conductor.orchestrator.orchestrator"
_APPROVED = ReviewVerdict(approved=True)


def _approved_review_mock():
    """Return an AsyncMock that always returns an approved ReviewVerdict."""
    return AsyncMock(return_value=_APPROVED)


class TestOrchestrator:
    """ORCH-02: Orchestrator orchestrates the full loop."""

    @pytest.mark.asyncio
    async def test_run_decomposes_and_spawns(self):
        """Two independent tasks: both should get spawned (ACPClient opened twice)."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [
            _make_task_spec("t1", "src/a.py"),
            _make_task_spec("t2", "src/b.py"),
        ]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        spawn_count = 0
        acp_instances = []

        def _acp_factory(**kwargs):
            nonlocal spawn_count
            spawn_count += 1
            inst = _make_mock_acp_client()
            acp_instances.append(inst)
            return inst

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build two features")

        assert spawn_count == 2, f"Expected 2 spawns, got {spawn_count}"

    @pytest.mark.asyncio
    async def test_run_validates_ownership_before_spawn(self):
        """Two tasks sharing the same target_file: FileConflictError, no spawn."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [
            _make_task_spec("t1", "src/shared.py"),
            _make_task_spec("t2", "src/shared.py"),  # conflict
        ]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        spawn_count = 0

        def _acp_factory(**kwargs):
            nonlocal spawn_count
            spawn_count += 1
            return _make_mock_acp_client()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            with pytest.raises(FileConflictError):
                await orch.run("Build conflicting features")

        assert spawn_count == 0, "ACPClient should not be opened on conflict"

    @pytest.mark.asyncio
    async def test_run_respects_dependency_order(self):
        """Tasks A(no deps) and B(requires A): A must spawn before B."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [
            _make_task_spec("a", "src/a.py"),
            _make_task_spec("b", "src/b.py", requires=["a"]),
        ]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        spawn_order: list[str] = []

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        async def _patched_loop(self_ref, task_spec, sem):
            spawn_order.append(task_spec.id)
            async with sem:
                pass

        OrchestratorClass = __import__(
            "conductor.orchestrator.orchestrator", fromlist=["Orchestrator"]
        ).Orchestrator
        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient"),
            patch.object(OrchestratorClass, "_run_agent_loop", _patched_loop),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build with dependencies")

        assert spawn_order.index("a") < spawn_order.index("b"), \
            f"Expected a before b, got: {spawn_order}"

    @pytest.mark.asyncio
    async def test_run_max_agents_cap(self):
        """4 independent tasks with max_agents=2: at most 2 concurrent sessions."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec(f"t{i}", f"src/file{i}.py") for i in range(4)]
        plan = _make_plan(tasks, max_agents=2)
        state_mgr = _make_state_manager()

        concurrent_high_water = 0
        current_concurrent = 0

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        async def _slow_loop(self_ref, task_spec, sem):
            nonlocal concurrent_high_water, current_concurrent
            async with sem:
                current_concurrent += 1
                if current_concurrent > concurrent_high_water:
                    concurrent_high_water = current_concurrent
                await asyncio.sleep(0.01)
                current_concurrent -= 1

        OrchestratorClass = __import__(
            "conductor.orchestrator.orchestrator", fromlist=["Orchestrator"]
        ).Orchestrator
        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient"),
            patch.object(OrchestratorClass, "_run_agent_loop", _slow_loop),
        ):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path="/repo", max_agents=5
            )
            await orch.run("Build 4 tasks with cap 2")

        assert concurrent_high_water <= 2, \
            f"Semaphore exceeded: {concurrent_high_water} concurrent"

    @pytest.mark.asyncio
    async def test_spawn_writes_agent_record_before_session(self):
        """AgentRecord is written to state before ACPClient.__aenter__ is called."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        call_order: list[str] = []

        original_mutate = state_mgr.mutate

        def _track_mutate(fn, *args, **kwargs):
            call_order.append("mutate")
            return original_mutate(fn, *args, **kwargs)

        state_mgr.mutate = _track_mutate

        def _acp_factory(**kwargs):
            client = _make_mock_acp_client()

            async def _enter(self=None):
                call_order.append("acp_enter")
                return client

            client.__aenter__ = _enter
            return client

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build one task")

        # At least one mutate call must precede acp_enter
        assert "mutate" in call_order, "mutate was never called"
        assert "acp_enter" in call_order, "acp_enter was never called"
        first_mutate = call_order.index("mutate")
        first_acp = call_order.index("acp_enter")
        assert first_mutate < first_acp, \
            f"AgentRecord mutate must precede acp_enter: {call_order}"

    @pytest.mark.asyncio
    async def test_spawn_builds_identity_prompt(self):
        """ACPClient receives system_prompt containing agent name, role, target_file."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [TaskSpec(
            id="t1",
            title="Auth Task",
            description="Implement auth",
            role="security engineer",
            target_file="src/auth.py",
        )]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        captured_kwargs: list[dict] = []

        def _acp_factory(**kwargs):
            captured_kwargs.append(kwargs)
            return _make_mock_acp_client()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build auth")

        assert captured_kwargs, "ACPClient was not instantiated"
        system_prompt = captured_kwargs[0].get("system_prompt", "")
        assert "security engineer" in system_prompt
        assert "src/auth.py" in system_prompt

    @pytest.mark.asyncio
    async def test_run_uses_min_max_agents(self):
        """Orchestrator max_agents=3, plan max_agents=2: semaphore uses 2 (min)."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec(f"t{i}", f"src/file{i}.py") for i in range(3)]
        plan = _make_plan(tasks, max_agents=2)  # plan says 2
        state_mgr = _make_state_manager()

        semaphore_values: list[int] = []

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        async def _capture_loop(self_ref, task_spec, sem):
            semaphore_values.append(sem._value)  # asyncio.Semaphore internal
            async with sem:
                pass

        OrchestratorClass = __import__(
            "conductor.orchestrator.orchestrator", fromlist=["Orchestrator"]
        ).Orchestrator
        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient"),
            patch.object(OrchestratorClass, "_run_agent_loop", _capture_loop),
        ):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path="/repo", max_agents=3
            )
            await orch.run("Build 3 tasks")

        # The semaphore should have been created with value 2 (min of 3 and 2)
        assert semaphore_values, "No spawn calls"
        # Semaphore value at first call should be at most 2
        assert semaphore_values[0] <= 2, \
            f"Semaphore value {semaphore_values[0]} exceeds plan max_agents=2"

    @pytest.mark.asyncio
    async def test_run_updates_task_status_on_completion(self):
        """Task status must be set to COMPLETED after agent session closes."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        completed_task_ids: list[str] = []

        def _track_mutate(fn):
            from conductor.state.models import ConductorState, Task, TaskStatus
            dummy_state = ConductorState(
                tasks=[Task(id="t1", title="T1", description="D1")]
            )
            fn(dummy_state)
            for task in dummy_state.tasks:
                if task.status == TaskStatus.COMPLETED:
                    completed_task_ids.append(task.id)
            return None

        state_mgr.mutate = _track_mutate

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        def _acp_factory(**kwargs):
            return _make_mock_acp_client()

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build one task")

        assert "t1" in completed_task_ids, (
            f"Task t1 was not marked COMPLETED. "
            f"Mutations recorded: {completed_task_ids}"
        )


# ---------------------------------------------------------------------------
# ORCH-04 / ORCH-05 tests: observe-review-revise cycle
# ---------------------------------------------------------------------------


class TestOrch04CompleteGate:
    """ORCH-04: Task status COMPLETED only after review passes."""

    @pytest.mark.asyncio
    async def test_approved_review_marks_task_completed_with_approved_status(self):
        """When review_output returns approved=True, task gets COMPLETED + APPROVED."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        # Track all mutations to inspect final review_status / task status
        completed_tasks: list[tuple[str, str, str]] = []  # (id, status, review_status)

        def _track_mutate(fn):
            from conductor.state.models import ConductorState, Task
            dummy = ConductorState(
                tasks=[Task(id="t1", title="T1", description="D1")]
            )
            fn(dummy)
            for task in dummy.tasks:
                if task.status == "completed":
                    completed_tasks.append((task.id, task.status, task.review_status))
            return None

        state_mgr.mutate = _track_mutate

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        approved_verdict = ReviewVerdict(approved=True)

        def _acp_factory(**kwargs):
            return _make_mock_acp_client_with_result("All done")

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", AsyncMock(return_value=approved_verdict)),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build feature")

        assert completed_tasks, "No COMPLETED mutation observed"
        task_id, status, review_status = completed_tasks[-1]
        assert task_id == "t1"
        assert status == "completed"
        assert review_status == "approved", f"Expected approved, got {review_status}"

    @pytest.mark.asyncio
    async def test_failed_review_with_no_revisions_still_completes(self):
        """When review fails and no revisions possible, task still COMPLETED."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        completed_tasks: list[tuple[str, str, str]] = []

        def _track_mutate(fn):
            from conductor.state.models import ConductorState, Task
            dummy = ConductorState(
                tasks=[Task(id="t1", title="T1", description="D1")]
            )
            fn(dummy)
            for task in dummy.tasks:
                if task.status == "completed":
                    completed_tasks.append((task.id, task.status, task.review_status))
            return None

        state_mgr.mutate = _track_mutate

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        failed_verdict = ReviewVerdict(
            approved=False, revision_instructions="Fix it"
        )

        def _acp_factory(**kwargs):
            return _make_mock_acp_client_with_result("Partial")

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", AsyncMock(return_value=failed_verdict)),
        ):
            orch = Orchestrator(
                state_manager=state_mgr,
                repo_path="/repo",
                max_revisions=0,
            )
            await orch.run("Build feature")

        # Task must still be completed (best-effort)
        assert completed_tasks, "Task was never completed even on best-effort"


class TestOrch05RevisionSend:
    """ORCH-05: client.send() called with revision feedback on failed review."""

    @pytest.mark.asyncio
    async def test_send_called_twice_on_one_revision(self):
        """When review fails once then passes: client.send called exactly twice."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()
        state_mgr.mutate = MagicMock(return_value=None)

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        # First call: fail. Second call: pass.
        verdicts = [
            ReviewVerdict(approved=False, revision_instructions="Fix the bug"),
            ReviewVerdict(approved=True),
        ]
        mock_review = AsyncMock(side_effect=verdicts)

        captured_clients: list = []

        def _acp_factory(**kwargs):
            client = _make_mock_acp_client_with_result("Done")
            captured_clients.append(client)
            return client

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", mock_review),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build feature")

        assert captured_clients, "ACPClient was never instantiated"
        client = captured_clients[0]
        # send() called: 1 initial + 1 revision = 2
        assert client.send.call_count == 2, \
            f"Expected send called 2 times, got {client.send.call_count}"


class TestOrch05MaxRevisions:
    """ORCH-05: Revision loop terminates at max_revisions cap."""

    @pytest.mark.asyncio
    async def test_loop_runs_max_revisions_plus_one_iterations(self):
        """With max_revisions=2 and always failing: 3 iterations, revision_count=2."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        final_revision_count: list[int] = []

        def _track_mutate(fn):
            from conductor.state.models import ConductorState, Task
            dummy = ConductorState(
                tasks=[Task(id="t1", title="T1", description="D1")]
            )
            fn(dummy)
            for task in dummy.tasks:
                if task.status == "completed":
                    final_revision_count.append(task.revision_count)
            return None

        state_mgr.mutate = _track_mutate

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        review_call_count: list[int] = [0]

        async def _counting_review(**kwargs):
            review_call_count[0] += 1
            return ReviewVerdict(approved=False, revision_instructions="Fix it")

        captured_clients: list = []

        def _acp_factory(**kwargs):
            client = _make_mock_acp_client_with_result("Partial")
            captured_clients.append(client)
            return client

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", AsyncMock(side_effect=_counting_review)),
        ):
            orch = Orchestrator(
                state_manager=state_mgr,
                repo_path="/repo",
                max_revisions=2,
            )
            await orch.run("Build feature")

        # review_output called 3 times: initial + 2 revisions
        assert review_call_count[0] == 3, \
            f"Expected 3 review calls (initial+2 revisions), got {review_call_count[0]}"

        # Task marked with revision_count=2
        assert final_revision_count, "Task was never completed"
        assert final_revision_count[-1] == 2, \
            f"Expected revision_count=2, got {final_revision_count[-1]}"


class TestOrch05SessionOpenForRevision:
    """ORCH-05: ACPClient session stays open for the entire revision loop."""

    @pytest.mark.asyncio
    async def test_aexit_called_exactly_once_after_all_revisions(self):
        """__aexit__ is called exactly once — session stays open for the loop."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()
        state_mgr.mutate = MagicMock(return_value=None)

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        # 2 failures then approve
        verdicts = [
            ReviewVerdict(approved=False, revision_instructions="Round 1"),
            ReviewVerdict(approved=False, revision_instructions="Round 2"),
            ReviewVerdict(approved=True),
        ]
        mock_review = AsyncMock(side_effect=verdicts)

        captured_clients: list = []

        def _acp_factory(**kwargs):
            client = _make_mock_acp_client_with_result("Done")
            captured_clients.append(client)
            return client

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", mock_review),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build feature")

        assert captured_clients, "ACPClient was never instantiated"
        client = captured_clients[0]
        aexit_count = client.__aexit__.call_count
        assert aexit_count == 1, \
            f"Expected __aexit__ called exactly 1 time, got {aexit_count}"


# ---------------------------------------------------------------------------
# COMM-05 tests: cancel_agent — cancel running sub-agent and reassign
# ---------------------------------------------------------------------------


class TestComm05CancelReassign:
    """COMM-05: cancel_agent cancels a running task and spawns a new session."""

    @pytest.mark.asyncio
    async def test_cancel_agent_cancels_running_task(self):
        """cancel_agent cancels the asyncio.Task for agent_id and removes from _active_tasks."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        orch._semaphore = asyncio.Semaphore(2)

        # Simulate a running task in _active_tasks
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.cancel = MagicMock()
        orch._active_tasks["agent-t1-abc"] = mock_task

        corrected_spec = _make_task_spec("t1", "src/a.py", title="Corrected T1")

        with patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: _make_mock_acp_client()):
            await orch.cancel_agent("agent-t1-abc", corrected_spec)

        # Task was cancelled
        mock_task.cancel.assert_called_once()
        # Entry removed from _active_tasks (new task may have been added under a new key)
        assert "agent-t1-abc" not in orch._active_tasks

    @pytest.mark.asyncio
    async def test_cancel_agent_spawns_new_loop_with_corrected_spec(self):
        """cancel_agent spawns a new _run_agent_loop with the corrected TaskSpec."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        orch._semaphore = asyncio.Semaphore(2)

        corrected_spec = _make_task_spec("t1", "src/corrected.py", title="Corrected")
        spawned_specs: list[TaskSpec] = []

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_specs.append(task_spec)

        orch._run_agent_loop = _capture_loop

        await orch.cancel_agent("agent-unknown-id", corrected_spec)
        # Yield to event loop to allow the spawned asyncio.Task to execute
        await asyncio.sleep(0)

        assert len(spawned_specs) == 1
        assert spawned_specs[0].target_file == "src/corrected.py"

    @pytest.mark.asyncio
    async def test_cancel_agent_unknown_id_is_idempotent(self):
        """cancel_agent on unknown agent_id does not raise — just spawns new task."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        orch._semaphore = asyncio.Semaphore(2)

        corrected_spec = _make_task_spec("t1", "src/a.py")

        async def _noop_loop(task_spec, sem, **kwargs):
            pass

        orch._run_agent_loop = _noop_loop

        # Should not raise even though agent_id is not in _active_tasks
        await orch.cancel_agent("nonexistent-agent", corrected_spec)
        # Yield to allow any spawned task to complete cleanly
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# COMM-06 tests: inject_guidance — send guidance without stopping agent
# ---------------------------------------------------------------------------


class TestComm06InjectGuidance:
    """COMM-06: inject_guidance sends guidance to active agent without interrupting."""

    @pytest.mark.asyncio
    async def test_inject_guidance_calls_client_send(self):
        """inject_guidance calls client.send(guidance) on the active client."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        mock_client = AsyncMock()
        mock_client.send = AsyncMock()
        orch._active_clients["agent-t1"] = mock_client

        await orch.inject_guidance("agent-t1", "Please use snake_case for variables.")

        mock_client.send.assert_called_once_with("Please use snake_case for variables.")

    @pytest.mark.asyncio
    async def test_inject_guidance_does_not_interrupt(self):
        """inject_guidance does NOT call client.interrupt()."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        mock_client = AsyncMock()
        mock_client.send = AsyncMock()
        mock_client.interrupt = AsyncMock()
        orch._active_clients["agent-t1"] = mock_client

        await orch.inject_guidance("agent-t1", "Use type hints everywhere.")

        mock_client.interrupt.assert_not_called()

    @pytest.mark.asyncio
    async def test_inject_guidance_unknown_agent_raises_escalation_error(self):
        """inject_guidance raises EscalationError when agent_id is not active."""
        from conductor.orchestrator.errors import EscalationError
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        with pytest.raises(EscalationError):
            await orch.inject_guidance("nonexistent-agent", "Some guidance")


# ---------------------------------------------------------------------------
# COMM-07 tests: pause_for_human_decision — interrupt, escalate, resume
# ---------------------------------------------------------------------------


def _make_mock_acp_client_with_interrupt():
    """Return a mock ACPClient that supports interrupt() and stream_response()."""
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.send = AsyncMock()
    client.interrupt = AsyncMock()

    async def _empty_stream():
        return
        yield

    client.stream_response = MagicMock(side_effect=_empty_stream)
    return client


class TestComm07PauseAndDecide:
    """COMM-07: pause_for_human_decision interrupts, escalates, resumes."""

    @pytest.mark.asyncio
    async def test_pause_calls_interrupt_and_drains_stream(self):
        """pause_for_human_decision calls client.interrupt() and drains stream_response()."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        mock_client = _make_mock_acp_client_with_interrupt()
        orch._active_clients["agent-t1"] = mock_client

        human_out: asyncio.Queue = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()
        await human_in.put("Proceed with option A")

        await orch.pause_for_human_decision(
            "agent-t1", "Which approach?", human_out, human_in, timeout=5.0
        )

        mock_client.interrupt.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_pushes_human_query_to_out_queue(self):
        """pause_for_human_decision puts a HumanQuery on human_out."""
        from conductor.orchestrator.escalation import HumanQuery
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        mock_client = _make_mock_acp_client_with_interrupt()
        orch._active_clients["agent-t1"] = mock_client

        human_out: asyncio.Queue = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()
        await human_in.put("Option B")

        await orch.pause_for_human_decision(
            "agent-t1", "What should I do?", human_out, human_in, timeout=5.0
        )

        assert not human_out.empty(), "HumanQuery was not pushed to human_out"
        query = human_out.get_nowait()
        assert isinstance(query, HumanQuery)
        assert query.question == "What should I do?"

    @pytest.mark.asyncio
    async def test_pause_sends_decision_via_client_send(self):
        """pause_for_human_decision sends human decision via client.send()."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        mock_client = _make_mock_acp_client_with_interrupt()
        orch._active_clients["agent-t1"] = mock_client

        human_out: asyncio.Queue = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()
        await human_in.put("Use approach X")

        await orch.pause_for_human_decision(
            "agent-t1", "Which approach?", human_out, human_in, timeout=5.0
        )

        # client.send should be called with the human decision embedded
        mock_client.send.assert_called_once()
        sent_text: str = mock_client.send.call_args[0][0]
        assert "Use approach X" in sent_text

    @pytest.mark.asyncio
    async def test_pause_falls_back_on_timeout(self):
        """pause_for_human_decision falls back to 'proceed with best judgment' on timeout."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        mock_client = _make_mock_acp_client_with_interrupt()
        orch._active_clients["agent-t1"] = mock_client

        human_out: asyncio.Queue = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()  # empty — will time out

        await orch.pause_for_human_decision(
            "agent-t1", "What next?", human_out, human_in, timeout=0.01
        )

        # Should send fallback message
        mock_client.send.assert_called_once()
        sent_text: str = mock_client.send.call_args[0][0]
        assert "proceed with best judgment" in sent_text

    @pytest.mark.asyncio
    async def test_pause_unknown_agent_raises_escalation_error(self):
        """pause_for_human_decision raises EscalationError for unknown agent_id."""
        from conductor.orchestrator.errors import EscalationError
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")

        human_out: asyncio.Queue = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()

        with pytest.raises(EscalationError):
            await orch.pause_for_human_decision(
                "nonexistent-agent", "What next?", human_out, human_in
            )


# ---------------------------------------------------------------------------
# RUNT-03/05 tests: mode wiring, .memory/ creation, session persistence, resume
# ---------------------------------------------------------------------------


class TestOrchestratorModeWiring:
    """RUNT-05: Orchestrator accepts mode and queue params, creates EscalationRouter."""

    def test_mode_default_is_auto(self):
        """Orchestrator default mode is 'auto'."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        assert orch._mode == "auto"

    def test_mode_interactive_stored(self):
        """Orchestrator stores mode='interactive' when specified."""
        from conductor.orchestrator.orchestrator import Orchestrator

        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        state_mgr = _make_state_manager()
        orch = Orchestrator(
            state_manager=state_mgr,
            repo_path="/repo",
            mode="interactive",
            human_out=q1,
            human_in=q2,
        )
        assert orch._mode == "interactive"
        assert orch._human_out is q1
        assert orch._human_in is q2

    def test_escalation_router_created_with_mode(self):
        """Orchestrator creates EscalationRouter with mode and queue params."""
        from conductor.orchestrator.escalation import EscalationRouter
        from conductor.orchestrator.orchestrator import Orchestrator

        q1: asyncio.Queue = asyncio.Queue()
        q2: asyncio.Queue = asyncio.Queue()
        state_mgr = _make_state_manager()
        orch = Orchestrator(
            state_manager=state_mgr,
            repo_path="/repo",
            mode="interactive",
            human_out=q1,
            human_in=q2,
        )
        assert isinstance(orch._escalation_router, EscalationRouter)
        assert orch._escalation_router._mode == "interactive"
        assert orch._escalation_router._human_out is q1
        assert orch._escalation_router._human_in is q2

    def test_escalation_router_auto_mode_no_queues(self):
        """In auto mode, EscalationRouter receives no queues."""
        from conductor.orchestrator.escalation import EscalationRouter
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo", mode="auto")
        assert isinstance(orch._escalation_router, EscalationRouter)
        assert orch._escalation_router._mode == "auto"
        assert orch._escalation_router._human_out is None
        assert orch._escalation_router._human_in is None


class TestOrchestratorMemoryDir:
    """RUNT-02: Orchestrator creates .memory/ directory at run start."""

    @pytest.mark.asyncio
    async def test_run_creates_memory_dir(self, tmp_path):
        """run() creates .memory/ directory under repo_path before spawning agents."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        memory_dir = tmp_path / ".memory"
        assert not memory_dir.exists()

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: _make_mock_acp_client()),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            await orch.run("Build feature")

        assert memory_dir.exists(), ".memory/ directory was not created"
        assert memory_dir.is_dir()


class TestOrchestratorSessionPersistence:
    """RUNT-03: session_id persisted to AgentRecord before first send()."""

    @pytest.mark.asyncio
    async def test_session_id_persisted_before_first_send(self, tmp_path):
        """_run_agent_loop persists session_id to AgentRecord before client.send()."""
        from conductor.orchestrator.orchestrator import Orchestrator

        task_spec = _make_task_spec("t1", "src/a.py")
        sem = asyncio.Semaphore(2)
        state_mgr = _make_state_manager()

        persisted_session_ids: list[str] = []
        send_order: list[str] = []

        def _track_mutate(fn):
            from conductor.state.models import AgentRecord, AgentStatus, ConductorState

            dummy = ConductorState(
                agents=[
                    AgentRecord(id="dummy-agent", name="dummy-agent", role="dev")
                ]
            )
            fn(dummy)
            for agent in dummy.agents:
                if agent.session_id is not None:
                    persisted_session_ids.append(agent.session_id)
                    send_order.append("persist_session")

        state_mgr.mutate = _track_mutate

        client = _make_mock_acp_client()

        original_send = client.send.side_effect

        async def _tracking_send(msg):
            send_order.append("send")

        client.send = AsyncMock(side_effect=_tracking_send)

        mock_server_info = {"session_id": "sess-xyz"}

        mock_sdk_client = MagicMock()
        mock_sdk_client.get_server_info = AsyncMock(return_value=mock_server_info)
        client._sdk_client = mock_sdk_client

        with (
            patch(f"{_ORCH}.ACPClient", return_value=client),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            await orch._run_agent_loop(task_spec, sem)

        assert "sess-xyz" in persisted_session_ids, (
            "session_id 'sess-xyz' was not persisted to AgentRecord"
        )
        # persist_session must precede first send
        if "persist_session" in send_order and "send" in send_order:
            assert send_order.index("persist_session") < send_order.index("send"), (
                f"session_id persist must happen before first send: {send_order}"
            )

    @pytest.mark.asyncio
    async def test_resume_session_id_passed_to_acp_client(self, tmp_path):
        """_run_agent_loop passes resume=session_id to ACPClient when provided."""
        from conductor.orchestrator.orchestrator import Orchestrator

        task_spec = _make_task_spec("t1", "src/a.py")
        sem = asyncio.Semaphore(2)
        state_mgr = _make_state_manager()

        captured_kwargs: list[dict] = []

        def _acp_factory(**kwargs):
            captured_kwargs.append(kwargs)
            return _make_mock_acp_client()

        with (
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            await orch._run_agent_loop(
                task_spec, sem, resume_session_id="sess-resume-123"
            )

        assert captured_kwargs, "ACPClient was not instantiated"
        assert captured_kwargs[0].get("resume") == "sess-resume-123", (
            f"Expected resume='sess-resume-123', got: {captured_kwargs[0].get('resume')}"
        )

    @pytest.mark.asyncio
    async def test_resume_session_id_none_by_default(self, tmp_path):
        """_run_agent_loop uses resume=None when resume_session_id not provided."""
        from conductor.orchestrator.orchestrator import Orchestrator

        task_spec = _make_task_spec("t1", "src/a.py")
        sem = asyncio.Semaphore(2)
        state_mgr = _make_state_manager()

        captured_kwargs: list[dict] = []

        def _acp_factory(**kwargs):
            captured_kwargs.append(kwargs)
            return _make_mock_acp_client()

        with (
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            await orch._run_agent_loop(task_spec, sem)

        assert captured_kwargs, "ACPClient was not instantiated"
        assert captured_kwargs[0].get("resume") is None


class TestOrchestratorResume:
    """RUNT-03: Orchestrator.resume() re-spawns IN_PROGRESS tasks."""

    @pytest.mark.asyncio
    async def test_resume_finds_in_progress_tasks(self, tmp_path):
        """resume() reads state, finds IN_PROGRESS tasks, calls _run_agent_loop."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        state_mgr = _make_state_manager()

        # Build a state with one IN_PROGRESS task
        in_progress_task = Task(
            id="task-resume-1",
            title="Resume Task",
            description="A task to resume",
            status=TaskStatus.IN_PROGRESS,
            assigned_agent="agent-task-resume-1-abc",
            target_file="src/resume.py",
        )
        agent_record = AgentRecord(
            id="agent-task-resume-1-abc",
            name="agent-task-resume-1-abc",
            role="developer",
            current_task_id="task-resume-1",
            status=AgentStatus.WORKING,
        )
        mock_state = ConductorState(
            tasks=[in_progress_task],
            agents=[agent_record],
        )

        def _read_state():
            return mock_state

        state_mgr.read_state = _read_state

        spawned_specs: list = []
        spawned_resumes: list = []

        async def _capture_loop(task_spec, sem, resume_session_id=None):
            spawned_specs.append(task_spec)
            spawned_resumes.append(resume_session_id)

        with patch(f"{_ORCH}.ACPClient"):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            orch._run_agent_loop = _capture_loop
            await orch.resume()

        assert len(spawned_specs) == 1, (
            f"Expected 1 spawned spec for IN_PROGRESS task, got {len(spawned_specs)}"
        )
        assert spawned_specs[0].id == "task-resume-1"

    @pytest.mark.asyncio
    async def test_resume_uses_stored_session_id(self, tmp_path):
        """resume() looks up session_id from SessionRegistry and passes it."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        state_mgr = _make_state_manager()

        in_progress_task = Task(
            id="task-2",
            title="Task 2",
            description="Task with session",
            status=TaskStatus.IN_PROGRESS,
            assigned_agent="agent-task-2-xyz",
            target_file="src/foo.py",
        )
        agent_record = AgentRecord(
            id="agent-task-2-xyz",
            name="agent-task-2-xyz",
            role="developer",
            current_task_id="task-2",
            status=AgentStatus.WORKING,
            session_id="stored-sess-999",
        )
        mock_state = ConductorState(
            tasks=[in_progress_task],
            agents=[agent_record],
        )
        state_mgr.read_state = MagicMock(return_value=mock_state)

        spawned_resumes: list = []

        async def _capture_loop(task_spec, sem, resume_session_id=None):
            spawned_resumes.append(resume_session_id)

        with patch(f"{_ORCH}.ACPClient"):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            # Manually register the session_id in the registry
            orch._session_registry.register("agent-task-2-xyz", "stored-sess-999")
            orch._run_agent_loop = _capture_loop
            await orch.resume()

        assert spawned_resumes == ["stored-sess-999"], (
            f"Expected resume with 'stored-sess-999', got: {spawned_resumes}"
        )

    @pytest.mark.asyncio
    async def test_resume_fresh_session_when_no_session_id(self, tmp_path):
        """resume() spawns fresh session (resume=None) when no session_id stored."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        state_mgr = _make_state_manager()

        in_progress_task = Task(
            id="task-3",
            title="Task 3",
            description="No session",
            status=TaskStatus.IN_PROGRESS,
            assigned_agent="agent-task-3-nnn",
            target_file="src/bar.py",
        )
        agent_record = AgentRecord(
            id="agent-task-3-nnn",
            name="agent-task-3-nnn",
            role="developer",
            current_task_id="task-3",
            status=AgentStatus.WORKING,
            # no session_id set
        )
        mock_state = ConductorState(
            tasks=[in_progress_task],
            agents=[agent_record],
        )
        state_mgr.read_state = MagicMock(return_value=mock_state)

        spawned_resumes: list = []

        async def _capture_loop(task_spec, sem, resume_session_id=None):
            spawned_resumes.append(resume_session_id)

        with patch(f"{_ORCH}.ACPClient"):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            orch._run_agent_loop = _capture_loop
            await orch.resume()

        assert spawned_resumes == [None], (
            f"Expected resume=None for fresh session, got: {spawned_resumes}"
        )


# ---------------------------------------------------------------------------
# Registry cleanup tests
# ---------------------------------------------------------------------------


class TestActiveClientCleanup:
    """Registry cleanup: _active_clients and _active_tasks cleaned up on error."""

    @pytest.mark.asyncio
    async def test_active_clients_cleaned_up_on_exception(self):
        """_active_clients entry is deleted in finally block when _run_agent_loop raises."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        sem = asyncio.Semaphore(2)
        task_spec = _make_task_spec("t1", "src/a.py")

        error_client = AsyncMock()
        error_client.__aenter__ = AsyncMock(return_value=error_client)
        error_client.__aexit__ = AsyncMock(return_value=False)
        error_client.send = AsyncMock(side_effect=RuntimeError("Session crashed"))

        with (
            patch(f"{_ORCH}.ACPClient", return_value=error_client),
        ):
            with pytest.raises(RuntimeError):
                await orch._run_agent_loop(task_spec, sem)

        # Agent ID key (whatever it was) should not be in _active_clients
        assert len(orch._active_clients) == 0, (
            f"_active_clients not cleaned up: {orch._active_clients}"
        )

    @pytest.mark.asyncio
    async def test_active_clients_cleaned_up_on_normal_completion(self):
        """_active_clients entry is deleted when agent loop completes normally."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        sem = asyncio.Semaphore(2)
        task_spec = _make_task_spec("t1", "src/a.py")

        normal_client = _make_mock_acp_client()

        with (
            patch(f"{_ORCH}.ACPClient", return_value=normal_client),
            patch(f"{_ORCH}.review_output", _approved_review_mock()),
        ):
            await orch._run_agent_loop(task_spec, sem)

        assert len(orch._active_clients) == 0, (
            f"_active_clients not cleaned up after normal completion: {orch._active_clients}"
        )
