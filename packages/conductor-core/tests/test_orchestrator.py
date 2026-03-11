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
    async def test_run_decomposes_and_spawns(self, tmp_path):
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.run("Build two features")

        assert spawn_count == 2, f"Expected 2 spawns, got {spawn_count}"

    @pytest.mark.asyncio
    async def test_run_validates_ownership_before_spawn(self, tmp_path):
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            with pytest.raises(FileConflictError):
                await orch.run("Build conflicting features")

        assert spawn_count == 0, "ACPClient should not be opened on conflict"

    @pytest.mark.asyncio
    async def test_run_respects_dependency_order(self, tmp_path):
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.run("Build with dependencies")

        assert spawn_order.index("a") < spawn_order.index("b"), \
            f"Expected a before b, got: {spawn_order}"

    @pytest.mark.asyncio
    async def test_run_max_agents_cap(self, tmp_path):
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
                state_manager=state_mgr, repo_path=str(tmp_path), max_agents=5
            )
            await orch.run("Build 4 tasks with cap 2")

        assert concurrent_high_water <= 2, \
            f"Semaphore exceeded: {concurrent_high_water} concurrent"

    @pytest.mark.asyncio
    async def test_spawn_writes_agent_record_before_session(self, tmp_path):
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.run("Build one task")

        # At least one mutate call must precede acp_enter
        assert "mutate" in call_order, "mutate was never called"
        assert "acp_enter" in call_order, "acp_enter was never called"
        first_mutate = call_order.index("mutate")
        first_acp = call_order.index("acp_enter")
        assert first_mutate < first_acp, \
            f"AgentRecord mutate must precede acp_enter: {call_order}"

    @pytest.mark.asyncio
    async def test_spawn_builds_identity_prompt(self, tmp_path):
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.run("Build auth")

        assert captured_kwargs, "ACPClient was not instantiated"
        system_prompt = captured_kwargs[0].get("system_prompt", "")
        assert "security engineer" in system_prompt
        assert "src/auth.py" in system_prompt

    @pytest.mark.asyncio
    async def test_run_uses_min_max_agents(self, tmp_path):
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
                state_manager=state_mgr, repo_path=str(tmp_path), max_agents=3
            )
            await orch.run("Build 3 tasks")

        # The semaphore should have been created with value 2 (min of 3 and 2)
        assert semaphore_values, "No spawn calls"
        # Semaphore value at first call should be at most 2
        assert semaphore_values[0] <= 2, \
            f"Semaphore value {semaphore_values[0]} exceeds plan max_agents=2"

    @pytest.mark.asyncio
    async def test_run_updates_task_status_on_completion(self, tmp_path):
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
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
    async def test_approved_review_marks_task_completed_with_approved_status(
        self, tmp_path
    ):
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

        # Pre-create the target file so the file existence gate does not intercept
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "a.py").write_text("# done")

        def _acp_factory(**kwargs):
            return _make_mock_acp_client_with_result("All done")

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient", side_effect=_acp_factory),
            patch(f"{_ORCH}.review_output", AsyncMock(return_value=approved_verdict)),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.run("Build feature")

        assert completed_tasks, "No COMPLETED mutation observed"
        task_id, status, review_status = completed_tasks[-1]
        assert task_id == "t1"
        assert status == "completed"
        assert review_status == "approved", f"Expected approved, got {review_status}"

    @pytest.mark.asyncio
    async def test_failed_review_with_no_revisions_still_completes(self, tmp_path):
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
                repo_path=str(tmp_path),
                max_revisions=0,
            )
            await orch.run("Build feature")

        # Task must still be completed (best-effort)
        assert completed_tasks, "Task was never completed even on best-effort"


class TestOrch05RevisionSend:
    """ORCH-05: client.send() called with revision feedback on failed review."""

    @pytest.mark.asyncio
    async def test_send_called_twice_on_one_revision(self, tmp_path):
        """When review fails once then passes: client.send called exactly twice."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()
        state_mgr.mutate = MagicMock(return_value=None)

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        # Pre-create target file so file existence gate does not add extra revisions
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "a.py").write_text("# done")

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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.run("Build feature")

        assert captured_clients, "ACPClient was never instantiated"
        client = captured_clients[0]
        # send() called: 1 initial + 1 revision = 2
        assert client.send.call_count == 2, \
            f"Expected send called 2 times, got {client.send.call_count}"


class TestOrch05MaxRevisions:
    """ORCH-05: Revision loop terminates at max_revisions cap."""

    @pytest.mark.asyncio
    async def test_loop_runs_max_revisions_plus_one_iterations(self, tmp_path):
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
                repo_path=str(tmp_path),
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
    async def test_aexit_called_exactly_once_after_all_revisions(self, tmp_path):
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
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
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )
        from conductor.orchestrator.orchestrator import Orchestrator

        # Set up state so cancel_agent can reconstruct the spec
        task = Task(
            id="t1",
            title="Corrected T1",
            description="Do X",
            status=TaskStatus.IN_PROGRESS,
            target_file="src/a.py",
            assigned_agent="agent-t1-abc",
        )
        agent = AgentRecord(
            id="agent-t1-abc",
            name="agent-t1-abc",
            role="developer",
            status=AgentStatus.WORKING,
            current_task_id="t1",
        )
        state = ConductorState(tasks=[task], agents=[agent])

        state_mgr = _make_state_manager()
        state_mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        orch._semaphore = asyncio.Semaphore(2)

        # Simulate a running task in _active_tasks
        mock_task = MagicMock(spec=asyncio.Task)
        mock_task.cancel = MagicMock()
        orch._active_tasks["agent-t1-abc"] = mock_task

        with patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: _make_mock_acp_client()):
            await orch.cancel_agent("agent-t1-abc")

        # Task was cancelled
        mock_task.cancel.assert_called_once()
        # Entry removed from _active_tasks (new task may have been added under a new key)
        assert "agent-t1-abc" not in orch._active_tasks

    @pytest.mark.asyncio
    async def test_cancel_agent_spawns_new_loop_with_new_instructions(self):
        """cancel_agent(agent_id, new_instructions=...) spawns a new _run_agent_loop."""
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )
        from conductor.orchestrator.orchestrator import Orchestrator

        # Set up state with a known agent and task
        task = Task(
            id="t1",
            title="Task t1",
            description="Original description",
            status=TaskStatus.IN_PROGRESS,
            target_file="src/a.py",
            assigned_agent="agent-t1-xyz",
        )
        agent = AgentRecord(
            id="agent-t1-xyz",
            name="agent-t1-xyz",
            role="developer",
            status=AgentStatus.WORKING,
            current_task_id="t1",
        )
        state = ConductorState(tasks=[task], agents=[agent])

        state_mgr = _make_state_manager()
        state_mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        orch._semaphore = asyncio.Semaphore(2)

        spawned_specs: list[TaskSpec] = []

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_specs.append(task_spec)

        orch._run_agent_loop = _capture_loop

        await orch.cancel_agent("agent-t1-xyz", new_instructions="Do Y instead")
        # Yield to event loop to allow the spawned asyncio.Task to execute
        await asyncio.sleep(0)

        assert len(spawned_specs) == 1
        assert spawned_specs[0].description == "Do Y instead"

    @pytest.mark.asyncio
    async def test_cancel_agent_unknown_id_is_noop(self):
        """cancel_agent on unknown agent_id (not in state) is a safe no-op."""
        from conductor.state.models import ConductorState
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        state_mgr.read_state = MagicMock(return_value=ConductorState())
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        orch._semaphore = asyncio.Semaphore(2)

        async def _noop_loop(task_spec, sem, **kwargs):
            pass

        orch._run_agent_loop = _noop_loop

        # Should not raise even though agent_id is not in state
        await orch.cancel_agent("nonexistent-agent")
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
        registered_agent_ids: list[str] = []

        def _track_mutate(fn):
            from conductor.state.models import (
                AgentRecord,
                AgentStatus,
                ConductorState,
                Task,
            )
            # Create a state that can accept both add_agent and save_session mutations
            # Use a sentinel agent we can detect
            dummy_agents = [
                AgentRecord(id=aid, name=aid, role="dev")
                for aid in registered_agent_ids
            ] if registered_agent_ids else []
            dummy = ConductorState(
                tasks=[Task(id="t1", title="T1", description="D1")],
                agents=dummy_agents,
            )
            fn(dummy)
            # Detect if an agent was newly added (add_agent mutation)
            for agent in dummy.agents:
                if agent.id not in registered_agent_ids:
                    registered_agent_ids.append(agent.id)
            # Detect session_id set (save_session mutation)
            for agent in dummy.agents:
                if agent.session_id is not None:
                    if agent.session_id not in persisted_session_ids:
                        persisted_session_ids.append(agent.session_id)
                        send_order.append("persist_session")

        state_mgr.mutate = _track_mutate

        client = _make_mock_acp_client()

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

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_specs.append(task_spec)
            spawned_resumes.append(kwargs.get("resume_session_id"))

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

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_resumes.append(kwargs.get("resume_session_id"))

        with patch(f"{_ORCH}.ACPClient"):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            # Manually register the session_id in the registry
            orch._session_registry.register("agent-task-2-xyz", "stored-sess-999")
            orch._run_agent_loop = _capture_loop
            await orch.resume()

        # Note: rewritten resume() no longer passes resume_session_id
        # (it uses review_only for in-progress tasks instead)
        assert len(spawned_resumes) == 1

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

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_resumes.append(kwargs.get("resume_session_id"))

        with patch(f"{_ORCH}.ACPClient"):
            orch = Orchestrator(
                state_manager=state_mgr, repo_path=str(tmp_path)
            )
            orch._run_agent_loop = _capture_loop
            await orch.resume()

        # Rewritten resume() no longer passes resume_session_id
        assert len(spawned_resumes) == 1


# ---------------------------------------------------------------------------
# RUNT-04 tests: pre_run_review and run_auto
# ---------------------------------------------------------------------------


def _make_spec_review_result(
    is_clear: bool = True,
    issues: list[str] | None = None,
    confirmed_description: str = "Build feature",
):
    """Return a real ResultMessage with SpecReview structured_output."""
    from claude_agent_sdk import ResultMessage

    return ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=1,
        session_id="test-session-id",
        structured_output={
            "is_clear": is_clear,
            "issues": issues or [],
            "confirmed_description": confirmed_description,
        },
    )


class TestPreRunReview:
    """RUNT-04: pre_run_review() performs upfront single-exchange spec analysis."""

    @pytest.mark.asyncio
    async def test_pre_run_review_returns_confirmed_description(self, tmp_path):
        """pre_run_review() returns confirmed_description from structured output."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()

        result_msg = _make_spec_review_result(
            confirmed_description="Build a REST API with auth"
        )

        async def _mock_query(prompt, options):
            yield result_msg

        with patch(f"{_ORCH}.query", side_effect=_mock_query):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            result = await orch.pre_run_review(
                "Build a REST API with authentication"
            )

        assert result == "Build a REST API with auth"

    @pytest.mark.asyncio
    async def test_pre_run_review_logs_warning_on_issues(self, tmp_path, caplog):
        """pre_run_review() logs warning when review identifies issues."""
        import logging

        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()

        result_msg = _make_spec_review_result(
            is_clear=False,
            issues=["Missing auth mechanism", "No error handling specified"],
            confirmed_description="Build an API assuming JWT auth",
        )

        async def _mock_query(prompt, options):
            yield result_msg

        with patch(f"{_ORCH}.query", side_effect=_mock_query):
            with caplog.at_level(logging.WARNING, logger="conductor.orchestrator"):
                orch = Orchestrator(
                    state_manager=state_mgr, repo_path=str(tmp_path)
                )
                result = await orch.pre_run_review("Build an API")

        assert result == "Build an API assuming JWT auth"
        assert any("issue" in msg.lower() for msg in caplog.messages), (
            f"Expected warning about issues, got: {caplog.messages}"
        )

    @pytest.mark.asyncio
    async def test_pre_run_review_raises_on_no_result(self, tmp_path):
        """pre_run_review() raises DecompositionError when SDK returns no result."""
        from conductor.orchestrator.errors import DecompositionError
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()

        async def _empty_query(prompt, options):
            return
            yield  # make it an async generator

        with patch(f"{_ORCH}.query", side_effect=_empty_query):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            with pytest.raises(DecompositionError):
                await orch.pre_run_review("Build something")

    @pytest.mark.asyncio
    async def test_pre_run_review_is_single_exchange_no_permission_handler(
        self, tmp_path
    ):
        """pre_run_review() uses query() (not ClaudeSDKClient/PermissionHandler)."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()

        result_msg = _make_spec_review_result(
            confirmed_description="Build feature X"
        )

        query_calls: list = []

        async def _mock_query(prompt, options):
            query_calls.append({"prompt": prompt, "options": options})
            yield result_msg

        with (
            patch(f"{_ORCH}.query", side_effect=_mock_query),
            patch(f"{_ORCH}.ACPClient") as mock_acp,
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.pre_run_review("Build feature X")

        # query() was called (not ACPClient/ClaudeSDKClient)
        assert len(query_calls) == 1, "query() should be called exactly once"
        # ACPClient should NOT be instantiated for spec review
        mock_acp.assert_not_called()


class TestRunAuto:
    """RUNT-04: run_auto() chains pre_run_review -> run."""

    @pytest.mark.asyncio
    async def test_run_auto_calls_pre_run_review_then_run(self, tmp_path):
        """run_auto() calls pre_run_review() then run() with confirmed description."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()

        call_log: list[str] = []
        confirmed_desc = "Build a REST API with confirmed spec"

        async def _mock_pre_run_review(feature_description):
            call_log.append(f"pre_run_review:{feature_description}")
            return confirmed_desc

        async def _mock_run(feature_description):
            call_log.append(f"run:{feature_description}")

        with patch(f"{_ORCH}.ACPClient"):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            orch.pre_run_review = _mock_pre_run_review
            orch.run = _mock_run
            await orch.run_auto("Build a REST API")

        assert len(call_log) == 2, f"Expected 2 calls, got: {call_log}"
        assert call_log[0] == "pre_run_review:Build a REST API"
        assert call_log[1] == f"run:{confirmed_desc}"


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


# ---------------------------------------------------------------------------
# Integration tests: cancel_agent new-signature (CLI-01, CLI-03, COMM-05)
# ---------------------------------------------------------------------------


class TestCancelAgentIntegration:
    """Integration tests for cancel_agent(agent_id, new_instructions=None).

    These tests call cancel_agent with the CLI's call shape:
      - cancel_agent(agent_id)               — cancel and re-spawn with original spec
      - cancel_agent(agent_id, new_instructions=...)  — re-spawn with updated description
      - cancel_agent("nonexistent")           — safe no-op

    They use a real Orchestrator instance with a mocked StateManager whose
    read_state() returns a ConductorState with known agents and tasks.
    """

    def _make_state_with_agent(self):
        """Build a ConductorState with agent-1 assigned to task-1."""
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        task = Task(
            id="task-1",
            title="T",
            description="Do X",
            status=TaskStatus.IN_PROGRESS,
            target_file="src/foo.py",
            assigned_agent="agent-1",
        )
        agent = AgentRecord(
            id="agent-1",
            name="agent-1",
            role="developer",
            status=AgentStatus.WORKING,
            current_task_id="task-1",
        )
        return ConductorState(tasks=[task], agents=[agent])

    def _make_sm_with_state(self, state):
        """Return a MagicMock StateManager whose read_state returns *state*."""
        sm = MagicMock()
        sm.mutate = MagicMock(return_value=None)
        sm.read_state = MagicMock(return_value=state)
        return sm

    @pytest.mark.asyncio
    async def test_cancel_agent_no_new_instructions(self, tmp_path):
        """cancel_agent(agent_id) does not raise TypeError and re-spawns with original description."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state = self._make_state_with_agent()
        sm = self._make_sm_with_state(state)
        orch = Orchestrator(state_manager=sm, repo_path=str(tmp_path))

        spawned_specs = []

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_specs.append(task_spec)

        with patch.object(orch, "_run_agent_loop", side_effect=_capture_loop):
            # Must NOT raise TypeError — CLI calls cancel_agent with only agent_id
            await orch.cancel_agent("agent-1")

        # Yield to event loop to allow the spawned asyncio.Task to execute
        await asyncio.sleep(0)

        assert len(spawned_specs) == 1
        assert spawned_specs[0].description == "Do X"  # original description preserved

    @pytest.mark.asyncio
    async def test_cancel_agent_with_new_instructions(self, tmp_path):
        """cancel_agent(agent_id, new_instructions=...) re-spawns with updated description."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state = self._make_state_with_agent()
        sm = self._make_sm_with_state(state)
        orch = Orchestrator(state_manager=sm, repo_path=str(tmp_path))

        spawned_specs = []

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_specs.append(task_spec)

        with patch.object(orch, "_run_agent_loop", side_effect=_capture_loop):
            # Must NOT raise TypeError — CLI calls with keyword new_instructions
            await orch.cancel_agent("agent-1", new_instructions="work on auth instead")

        await asyncio.sleep(0)

        assert len(spawned_specs) == 1
        assert spawned_specs[0].description == "work on auth instead"

    @pytest.mark.asyncio
    async def test_cancel_agent_unknown_agent(self, tmp_path):
        """cancel_agent for an unknown agent_id is a safe no-op (no exception)."""
        from conductor.state.models import ConductorState
        from conductor.orchestrator.orchestrator import Orchestrator

        sm = self._make_sm_with_state(ConductorState())
        orch = Orchestrator(state_manager=sm, repo_path=str(tmp_path))

        # Must NOT raise any exception for a nonexistent agent
        await orch.cancel_agent("nonexistent")


# ---------------------------------------------------------------------------
# COMM-03 tests: EscalationRouter wired as PermissionHandler in _run_agent_loop
# ---------------------------------------------------------------------------


class TestPermissionHandlerWiring:
    """COMM-03: ACPClient sessions receive PermissionHandler wrapping EscalationRouter."""

    @pytest.mark.asyncio
    async def test_acp_client_receives_permission_handler(self, tmp_path):
        """_run_agent_loop passes permission_handler kwarg to ACPClient."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.acp.permission import PermissionHandler

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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch._run_agent_loop(task_spec, sem)

        assert captured_kwargs, "ACPClient was not instantiated"
        handler = captured_kwargs[0].get("permission_handler")
        assert handler is not None, "permission_handler kwarg was not passed to ACPClient"
        assert isinstance(handler, PermissionHandler), (
            f"Expected PermissionHandler, got {type(handler)}"
        )

    @pytest.mark.asyncio
    async def test_permission_handler_answer_fn_is_escalation_router_resolve(self, tmp_path):
        """PermissionHandler's _answer_fn is the escalation router's resolve method."""
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch._run_agent_loop(task_spec, sem)

        assert captured_kwargs, "ACPClient was not instantiated"
        handler = captured_kwargs[0].get("permission_handler")
        assert handler is not None, "permission_handler was not passed"
        # The answer_fn should be bound to the escalation router's resolve method
        assert handler._answer_fn == orch._escalation_router.resolve, (
            "permission_handler._answer_fn should be escalation_router.resolve"
        )

    @pytest.mark.asyncio
    async def test_permission_handler_timeout_is_150s(self, tmp_path):
        """PermissionHandler timeout is escalation_router._human_timeout + 30 (150s by default)."""
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
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch._run_agent_loop(task_spec, sem)

        assert captured_kwargs, "ACPClient was not instantiated"
        handler = captured_kwargs[0].get("permission_handler")
        assert handler is not None, "permission_handler was not passed"
        expected_timeout = orch._escalation_router._human_timeout + 30.0
        assert handler._timeout == expected_timeout, (
            f"Expected timeout={expected_timeout}, got {handler._timeout}"
        )


# ---------------------------------------------------------------------------
# Tests: Phase 16 — Agent status lifecycle mutations
# ---------------------------------------------------------------------------


class TestAgentStatusLifecycle:
    """Phase 16: Agent status lifecycle mutations."""

    def test_complete_task_sets_agent_done(self):
        """_make_complete_task_fn sets agent.status to DONE."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        state = ConductorState(
            tasks=[Task(id="t1", title="T", description="D", status=TaskStatus.IN_PROGRESS)],
            agents=[AgentRecord(id="a1", name="a1", role="dev", status=AgentStatus.WORKING, current_task_id="t1")],
        )

        fn = Orchestrator._make_complete_task_fn("t1", "a1")
        fn(state)

        assert state.tasks[0].status == "completed"
        assert state.agents[0].status == "done"

    def test_set_agent_status_fn(self):
        """_make_set_agent_status_fn changes agent status."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
        )

        state = ConductorState(
            agents=[AgentRecord(id="a1", name="a1", role="dev", status=AgentStatus.WORKING)],
        )

        fn = Orchestrator._make_set_agent_status_fn("a1", AgentStatus.WAITING)
        fn(state)
        assert state.agents[0].status == "waiting"

        fn2 = Orchestrator._make_set_agent_status_fn("a1", AgentStatus.WORKING)
        fn2(state)
        assert state.agents[0].status == "working"

    @pytest.mark.asyncio
    async def test_pause_sets_waiting_then_working(self, tmp_path):
        """pause_for_human_decision sets WAITING before human_out and WORKING after resume."""
        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))

        mock_client = AsyncMock()
        mock_client.interrupt = AsyncMock()

        async def _empty():
            return
            yield

        mock_client.stream_response = MagicMock(side_effect=_empty)
        mock_client.send = AsyncMock()
        orch._active_clients["a1"] = mock_client

        human_out = asyncio.Queue()
        human_in: asyncio.Queue = asyncio.Queue()
        await human_in.put("proceed")

        await orch.pause_for_human_decision("a1", "What?", human_out, human_in)

        # Verify mutate was called at least twice (WAITING + WORKING)
        assert state_mgr.mutate.call_count >= 2


# ---------------------------------------------------------------------------
# Tests: Semaphore scope — review_only mode
# ---------------------------------------------------------------------------


class TestSemaphoreScope:
    """Verify review_only runs outside the semaphore."""

    @pytest.mark.asyncio
    async def test_review_only_skips_semaphore(self, tmp_path):
        """review_only=True should not acquire the semaphore at all."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        sem = asyncio.Semaphore(1)
        # Lock the semaphore — if review_only tries to acquire, it will block forever
        await sem.acquire()

        spec = _make_task_spec("t1", str(tmp_path / "file.txt"))

        with patch(f"{_ORCH}.review_output", _approved_review_mock()):
            # Should complete without blocking (doesn't need semaphore)
            await asyncio.wait_for(
                orch._run_agent_loop(spec, sem, review_only=True),
                timeout=5.0,
            )

        # Release the semaphore we locked
        sem.release()

    @pytest.mark.asyncio
    async def test_review_only_calls_review_output(self, tmp_path):
        """review_only=True should still call review_output."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        sem = asyncio.Semaphore(1)
        spec = _make_task_spec("t1", str(tmp_path / "file.txt"))

        mock_review = _approved_review_mock()
        with patch(f"{_ORCH}.review_output", mock_review):
            await orch._run_agent_loop(spec, sem, review_only=True)

        mock_review.assert_called_once()

    @pytest.mark.asyncio
    async def test_review_only_false_acquires_semaphore(self, tmp_path):
        """review_only=False (default) should acquire the semaphore."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        sem = asyncio.Semaphore(1)
        spec = _make_task_spec("t1", str(tmp_path / "file.txt"))

        with patch(f"{_ORCH}.ACPClient") as mock_acp, \
             patch(f"{_ORCH}.review_output", _approved_review_mock()):
            mock_acp.return_value = _make_mock_acp_client()
            await orch._run_agent_loop(spec, sem)

        # Semaphore should be released after completion (value back to 1)
        assert sem._value == 1

    @pytest.mark.asyncio
    async def test_review_only_approves_on_review_error(self, tmp_path):
        """review_only=True should approve best-effort if review_output raises."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.orchestrator.errors import ReviewError

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        sem = asyncio.Semaphore(1)
        spec = _make_task_spec("t1", str(tmp_path / "file.txt"))

        failing_review = AsyncMock(side_effect=ReviewError("no structured output"))
        with patch(f"{_ORCH}.review_output", failing_review):
            # Should not raise — best-effort approval
            await orch._run_agent_loop(spec, sem, review_only=True)

        # State should have been updated (mutate called for add_agent + complete_task)
        assert mgr.mutate.call_count >= 2


# ---------------------------------------------------------------------------
# Tests: Orchestrator.resume() with full scheduler reconstruction
# ---------------------------------------------------------------------------


class TestResumeScheduler:
    """Tests for rewritten Orchestrator.resume() with scheduler reconstruction."""

    @pytest.mark.asyncio
    async def test_resume_skips_completed_tasks(self, tmp_path):
        """Completed tasks should not be re-run."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        # Create target file for completed task so it's recognized as truly done
        (tmp_path / "f1.txt").write_text("done")

        state = ConductorState(tasks=[
            Task(id="t1", title="Done", description="d", status=TaskStatus.COMPLETED,
                 target_file=str(tmp_path / "f1.txt")),
            Task(id="t2", title="Pending", description="d", status=TaskStatus.PENDING,
                 target_file=str(tmp_path / "f2.txt"), requires=["t1"]),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        # Only t2 should run, not t1
        assert mock_loop.call_count == 1
        called_spec = mock_loop.call_args_list[0][0][0]
        assert called_spec.id == "t2"

    @pytest.mark.asyncio
    async def test_resume_review_only_when_file_exists(self, tmp_path):
        """In-progress tasks with existing target file should run review_only."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        # Create the target file on disk
        target = tmp_path / "existing_file.txt"
        target.write_text("content")

        state = ConductorState(tasks=[
            Task(id="t1", title="InProg", description="d",
                 status=TaskStatus.IN_PROGRESS,
                 target_file=str(target)),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        assert mock_loop.call_count == 1
        assert mock_loop.call_args_list[0][1].get("review_only") is True

    @pytest.mark.asyncio
    async def test_resume_reruns_agent_when_file_missing(self, tmp_path):
        """In-progress tasks with no target file should re-run agent."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        state = ConductorState(tasks=[
            Task(id="t1", title="InProg", description="d",
                 status=TaskStatus.IN_PROGRESS,
                 target_file=str(tmp_path / "missing_file.txt")),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        assert mock_loop.call_count == 1
        assert mock_loop.call_args_list[0][1].get("review_only", False) is False

    @pytest.mark.asyncio
    async def test_resume_respects_dependencies(self, tmp_path):
        """Pending task blocked by in-progress task should wait."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        call_order: list[str] = []

        state = ConductorState(tasks=[
            Task(id="t1", title="InProg", description="d",
                 status=TaskStatus.IN_PROGRESS,
                 target_file=str(tmp_path / "f1.txt")),
            Task(id="t2", title="Pending", description="d",
                 status=TaskStatus.PENDING,
                 target_file=str(tmp_path / "f2.txt"), requires=["t1"]),
        ])

        # Create target file for t1 so it's review_only
        (tmp_path / "f1.txt").write_text("content")

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        async def track_call(spec, sem, **kwargs):
            call_order.append(spec.id)

        with patch.object(orch, '_run_agent_loop', side_effect=track_call):
            await orch.resume()

        assert call_order == ["t1", "t2"]

    @pytest.mark.asyncio
    async def test_resume_noop_when_all_completed(self, tmp_path):
        """Resume with all tasks completed should be a no-op."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        # Create target file so completed task is recognized
        (tmp_path / "f1.txt").write_text("done")

        state = ConductorState(tasks=[
            Task(id="t1", title="Done", description="d",
                 status=TaskStatus.COMPLETED, target_file=str(tmp_path / "f1.txt")),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        mock_loop.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_demotes_completed_with_missing_file(self, tmp_path):
        """Completed task with missing target file should be re-run, not skipped."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        # Do NOT create the target file — simulates the EventChip bug
        state = ConductorState(tasks=[
            Task(id="t1", title="Done but missing", description="d",
                 status=TaskStatus.COMPLETED,
                 target_file=str(tmp_path / "missing.tsx")),
        ])

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=state)
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        # Task should be re-run since file is missing
        assert mock_loop.call_count == 1
        called_spec = mock_loop.call_args_list[0][0][0]
        assert called_spec.id == "t1"

    @pytest.mark.asyncio
    async def test_resume_no_state_file(self, tmp_path):
        """Resume with empty state should be a no-op."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState

        mgr = _make_state_manager()
        mgr.read_state = MagicMock(return_value=ConductorState())
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

        with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
            await orch.resume()

        mock_loop.assert_not_called()


# ---------------------------------------------------------------------------
# RESM-01 tests: review_only exception fallback in _run_agent_loop
# ---------------------------------------------------------------------------


class TestReviewOnlyFallback:
    """RESM-01: When review_output raises during review_only, fall back to APPROVED."""

    @pytest.mark.asyncio
    async def test_review_only_exception_does_not_crash(self, tmp_path):
        """When review_output raises RuntimeError during review_only, _run_agent_loop
        completes normally without re-raising the exception."""
        from conductor.orchestrator.orchestrator import Orchestrator

        task_spec = _make_task_spec("t-resm-01", "src/resm.py")
        sem = asyncio.Semaphore(2)
        state_mgr = _make_state_manager()

        with patch(f"{_ORCH}.review_output", side_effect=RuntimeError("review boom")):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            # Must NOT raise
            await orch._run_agent_loop(task_spec, sem, review_only=True)

    @pytest.mark.asyncio
    async def test_review_only_exception_logs_warning(self, tmp_path, caplog):
        """When review_output raises ValueError during review_only, a WARNING log
        is emitted containing 'approving best-effort'."""
        import logging

        from conductor.orchestrator.orchestrator import Orchestrator

        task_spec = _make_task_spec("t-resm-01", "src/resm.py")
        sem = asyncio.Semaphore(2)
        state_mgr = _make_state_manager()

        with (
            patch(f"{_ORCH}.review_output", side_effect=ValueError("bad review")),
            caplog.at_level(logging.WARNING, logger="conductor.orchestrator"),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch._run_agent_loop(task_spec, sem, review_only=True)

        assert any(
            "approving best-effort" in record.message
            for record in caplog.records
        ), f"Expected 'approving best-effort' in log. Records: {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_review_only_exception_sets_approved_state(self, tmp_path):
        """When review_output raises RuntimeError during review_only, the final state
        mutation marks the task COMPLETED with review_status='approved'."""
        from conductor.orchestrator.orchestrator import Orchestrator

        task_spec = _make_task_spec("t-resm-01", "src/resm.py")
        sem = asyncio.Semaphore(2)
        state_mgr = _make_state_manager()

        completed_tasks: list[tuple[str, str]] = []  # (id, review_status)

        def _track_mutate(fn):
            from conductor.state.models import ConductorState, Task
            dummy = ConductorState(
                tasks=[Task(id="t-resm-01", title="T", description="D")]
            )
            fn(dummy)
            for task in dummy.tasks:
                if task.status == "completed":
                    completed_tasks.append((task.id, task.review_status))
            return None

        state_mgr.mutate = _track_mutate

        with patch(f"{_ORCH}.review_output", side_effect=RuntimeError("review boom")):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch._run_agent_loop(task_spec, sem, review_only=True)

        assert completed_tasks, "No COMPLETED mutation observed"
        task_id, review_status = completed_tasks[-1]
        assert task_id == "t-resm-01"
        assert review_status == "approved", (
            f"Expected review_status='approved', got '{review_status}'"
        )


# ---------------------------------------------------------------------------
# RESM-02 tests: resume spawn loop edge cases
# ---------------------------------------------------------------------------


class TestResumeSpawnLoop:
    """RESM-02: Resume spawn loop handles pre-completed, all-completed, and
    failed-future edge cases correctly."""

    @pytest.mark.asyncio
    async def test_resume_marked_done_guard_allows_pending_task(self, tmp_path):
        """When state has one COMPLETED task (no deps) and one PENDING task that
        requires the completed one, resume() calls _run_agent_loop exactly once —
        for the pending task only."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import (
            AgentRecord,
            AgentStatus,
            ConductorState,
            Task,
            TaskStatus,
        )

        state_mgr = _make_state_manager()

        # Create target file so completed task is recognized
        (tmp_path / "done.py").write_text("# done")

        completed_task = Task(
            id="task-done",
            title="Completed Task",
            description="Already done",
            status=TaskStatus.COMPLETED,
            target_file=str(tmp_path / "done.py"),
        )
        pending_task = Task(
            id="task-pending",
            title="Pending Task",
            description="Waiting for task-done",
            status=TaskStatus.PENDING,
            target_file=str(tmp_path / "pending.py"),
            requires=["task-done"],
        )
        agent_record = AgentRecord(
            id="agent-done-abc",
            name="agent-done-abc",
            role="developer",
            current_task_id="task-done",
            status=AgentStatus.DONE,
        )
        mock_state = ConductorState(
            tasks=[completed_task, pending_task],
            agents=[agent_record],
        )
        state_mgr.read_state = MagicMock(return_value=mock_state)

        spawned_ids: list[str] = []

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_ids.append(task_spec.id)

        orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
        orch._run_agent_loop = _capture_loop
        await orch.resume()

        assert spawned_ids == ["task-pending"], (
            f"Expected only 'task-pending' to be spawned, got {spawned_ids}"
        )

    @pytest.mark.asyncio
    async def test_resume_all_completed_exits_immediately(self, tmp_path):
        """When all tasks in state are COMPLETED, resume() calls _run_agent_loop
        zero times and returns cleanly."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, Task, TaskStatus

        # Create target files so completed tasks are recognized
        (tmp_path / "a.py").write_text("# done")
        (tmp_path / "b.py").write_text("# done")

        state_mgr = _make_state_manager()

        mock_state = ConductorState(tasks=[
            Task(
                id="task-a",
                title="Task A",
                description="Done A",
                status=TaskStatus.COMPLETED,
                target_file=str(tmp_path / "a.py"),
            ),
            Task(
                id="task-b",
                title="Task B",
                description="Done B",
                status=TaskStatus.COMPLETED,
                target_file=str(tmp_path / "b.py"),
            ),
        ])
        state_mgr.read_state = MagicMock(return_value=mock_state)

        spawned_ids: list[str] = []

        async def _capture_loop(task_spec, sem, **kwargs):
            spawned_ids.append(task_spec.id)

        orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
        orch._run_agent_loop = _capture_loop
        await orch.resume()

        assert spawned_ids == [], (
            f"Expected no tasks spawned for all-completed state, got {spawned_ids}"
        )

    @pytest.mark.asyncio
    async def test_resume_failed_future_exception_retrieved(self, tmp_path, caplog):
        """When a spawned task future raises an exception, resume() retrieves it
        (no 'Task exception was never retrieved' warning) and completes without
        crashing. The exception is logged at ERROR level."""
        import logging

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
            id="task-failing",
            title="Failing Task",
            description="This task will fail",
            status=TaskStatus.IN_PROGRESS,
            assigned_agent="agent-failing-xyz",
            target_file=str(tmp_path / "missing.py"),  # file does NOT exist
        )
        agent_record = AgentRecord(
            id="agent-failing-xyz",
            name="agent-failing-xyz",
            role="developer",
            current_task_id="task-failing",
            status=AgentStatus.WORKING,
        )
        mock_state = ConductorState(
            tasks=[in_progress_task],
            agents=[agent_record],
        )
        state_mgr.read_state = MagicMock(return_value=mock_state)

        async def _failing_loop(task_spec, sem, **kwargs):
            raise RuntimeError("agent failed during resume")

        with caplog.at_level(logging.ERROR, logger="conductor.orchestrator"):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            orch._run_agent_loop = _failing_loop
            # Must NOT raise — exception should be retrieved and logged
            await orch.resume()

        assert any(
            "failed during resume" in record.message
            for record in caplog.records
        ), f"Expected 'failed during resume' in ERROR log. Records: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# VRFY-01/QUAL-01/QUAL-02 tests: File existence gate
# ---------------------------------------------------------------------------


class TestFileExistenceGate:
    """VRFY-01/QUAL-01/QUAL-02: File existence gate in _run_agent_loop revision loop."""

    @pytest.mark.asyncio
    async def test_missing_file_triggers_revision(self, tmp_path):
        """Reviewer approves but file is absent — gate injects revision message."""
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

    @pytest.mark.asyncio
    async def test_existing_file_no_revision(self, tmp_path):
        """File exists before loop runs, reviewer approves — no extra revision send."""
        from conductor.orchestrator.orchestrator import Orchestrator

        # Pre-create the target file
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "present.tsx").write_text("export default 2;")

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))
        sem = asyncio.Semaphore(1)
        spec = _make_task_spec("t1", "src/present.tsx")

        mock_client = _make_mock_acp_client()

        with patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: mock_client), \
             patch(f"{_ORCH}.review_output", _approved_review_mock()):
            await orch._run_agent_loop(spec, sem, max_revisions=2)

        # mutate called exactly twice: add_agent + complete_task
        assert mgr.mutate.call_count == 2, (
            f"Expected exactly 2 mutate calls (add_agent + complete), "
            f"got {mgr.mutate.call_count}"
        )
        # No revision send (only the initial task send)
        assert mock_client.send.call_count == 1, (
            f"Expected only 1 send (initial task), got {mock_client.send.call_count}"
        )

    @pytest.mark.asyncio
    async def test_missing_file_exhausts_revisions(self, tmp_path):
        """File never appears after max_revisions=1 — task ends with NEEDS_REVISION."""
        from conductor.orchestrator.orchestrator import Orchestrator
        from conductor.state.models import ConductorState, ReviewStatus, Task, TaskStatus

        # Pre-populate state with the task so _make_complete_task_fn can find it
        state = ConductorState(tasks=[
            Task(id="t1", title="Task t1", description="Description for t1",
                 status=TaskStatus.PENDING)
        ])
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

    @pytest.mark.asyncio
    async def test_empty_target_file_skips_check(self, tmp_path):
        """target_file='' — gate never runs, task completes normally."""
        from conductor.orchestrator.orchestrator import Orchestrator

        mgr = _make_state_manager()
        orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))
        sem = asyncio.Semaphore(1)
        spec = _make_task_spec("t1", "")  # empty target_file

        mock_client = _make_mock_acp_client()

        with patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: mock_client), \
             patch(f"{_ORCH}.review_output", _approved_review_mock()):
            await orch._run_agent_loop(spec, sem, max_revisions=2)

        # mutate called exactly twice: add_agent + complete_task
        assert mgr.mutate.call_count == 2, (
            f"Expected exactly 2 mutate calls (add_agent + complete), "
            f"got {mgr.mutate.call_count}"
        )


# ---------------------------------------------------------------------------
# QUAL-03: Post-run build check
# ---------------------------------------------------------------------------


class TestPostRunBuild:
    """QUAL-03: Optional post-run build_command runs after tasks complete."""

    @pytest.mark.asyncio
    async def test_build_command_runs_after_tasks(self, tmp_path):
        """Orchestrator(build_command='echo ok') -> subprocess called once after tasks."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        mgr = _make_state_manager()
        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        # Pre-create target file so gate doesn't intercept
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "a.py").write_text("# done")

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

    @pytest.mark.asyncio
    async def test_no_build_command_skips_check(self, tmp_path):
        """Without build_command, asyncio.create_subprocess_shell is never called."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        mgr = _make_state_manager()
        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        # Pre-create target file so gate doesn't intercept
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "a.py").write_text("# done")

        with patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer), \
             patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: _make_mock_acp_client()), \
             patch(f"{_ORCH}.review_output", _approved_review_mock()), \
             patch("asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_proc:
            orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))
            await orch.run("test feature")

        mock_proc.assert_not_called()

    @pytest.mark.asyncio
    async def test_build_failure_logged(self, tmp_path):
        """Build failure (non-zero returncode) is logged, not raised."""
        import logging
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        plan = _make_plan(tasks)
        mgr = _make_state_manager()
        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        # Pre-create target file so gate doesn't intercept
        (tmp_path / "src").mkdir(parents=True, exist_ok=True)
        (tmp_path / "src" / "a.py").write_text("# done")

        proc = AsyncMock()
        proc.communicate = AsyncMock(return_value=(b"", b"error: missing module"))
        proc.returncode = 1

        with patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer), \
             patch(f"{_ORCH}.ACPClient", side_effect=lambda **kw: _make_mock_acp_client()), \
             patch(f"{_ORCH}.review_output", _approved_review_mock()), \
             patch("asyncio.create_subprocess_shell", new_callable=AsyncMock, return_value=proc):
            orch = Orchestrator(
                state_manager=mgr, repo_path=str(tmp_path), build_command="tsc"
            )
            # Must NOT raise — build failure is logged only
            await orch.run("test feature")

    @pytest.mark.asyncio
    async def test_build_runs_after_resume(self, tmp_path):
        """All tasks already COMPLETED — resume() triggers build_command."""
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


# ---------------------------------------------------------------------------
# Phase 26: OrchestratorConfig wiring tests
# ---------------------------------------------------------------------------


class TestOrchestratorConfigWiring:
    """Verify Orchestrator accepts OrchestratorConfig and uses it for defaults."""

    def test_default_construction_uses_config_defaults(self):
        """Default Orchestrator should have max_revisions=2, max_agents=10 from config."""
        from conductor.orchestrator.orchestrator import Orchestrator
        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        assert orch._max_revisions == 2
        assert orch._max_agents == 10

    def test_custom_config_flows_through(self):
        """OrchestratorConfig values flow through to _max_revisions and _max_agents."""
        from conductor.orchestrator.models import OrchestratorConfig
        from conductor.orchestrator.orchestrator import Orchestrator
        state_mgr = _make_state_manager()
        cfg = OrchestratorConfig(max_review_iterations=5, max_agents=3)
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo", config=cfg)
        assert orch._max_revisions == 5
        assert orch._max_agents == 3

    def test_explicit_max_revisions_overrides_config(self):
        """Explicitly passing max_revisions (non-default) takes precedence over config."""
        from conductor.orchestrator.models import OrchestratorConfig
        from conductor.orchestrator.orchestrator import Orchestrator
        state_mgr = _make_state_manager()
        cfg = OrchestratorConfig(max_review_iterations=5)
        orch = Orchestrator(
            state_manager=state_mgr, repo_path="/repo",
            config=cfg, max_revisions=7,
        )
        assert orch._max_revisions == 7

    def test_explicit_max_agents_overrides_config(self):
        """Explicitly passing max_agents (non-default) takes precedence over config."""
        from conductor.orchestrator.models import OrchestratorConfig
        from conductor.orchestrator.orchestrator import Orchestrator
        state_mgr = _make_state_manager()
        cfg = OrchestratorConfig(max_agents=3)
        orch = Orchestrator(
            state_manager=state_mgr, repo_path="/repo",
            config=cfg, max_agents=8,
        )
        assert orch._max_agents == 8

    def test_config_attribute_stored(self):
        """_config attribute is accessible on Orchestrator instance."""
        from conductor.orchestrator.models import OrchestratorConfig
        from conductor.orchestrator.orchestrator import Orchestrator
        state_mgr = _make_state_manager()
        cfg = OrchestratorConfig(max_review_iterations=3)
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo", config=cfg)
        assert orch._config is cfg
        assert orch._config.max_review_iterations == 3

    def test_no_config_creates_default_config(self):
        """When no config is passed, a default OrchestratorConfig is created."""
        from conductor.orchestrator.models import OrchestratorConfig
        from conductor.orchestrator.orchestrator import Orchestrator
        state_mgr = _make_state_manager()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        assert isinstance(orch._config, OrchestratorConfig)
        assert orch._config.max_review_iterations == 2
        assert orch._config.max_decomposition_retries == 3


# ---------------------------------------------------------------------------
# Phase 27 tests: Wave execution, model routing, lean prompts
# ---------------------------------------------------------------------------


class TestWaveExecution:
    """WAVE-01: run() executes tasks in dependency waves via asyncio.gather."""

    @pytest.mark.asyncio
    async def test_run_executes_waves_sequentially(self, tmp_path):
        """3 tasks (A no-dep, B no-dep, C depends on A+B): A+B in wave 1, C in wave 2."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [
            _make_task_spec("a", "src/a.py"),
            _make_task_spec("b", "src/b.py"),
            _make_task_spec("c", "src/c.py", requires=["a", "b"]),
        ]
        plan = _make_plan(tasks)
        state_mgr = _make_state_manager()

        execution_log: list[str] = []

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        OrchestratorClass = __import__(
            "conductor.orchestrator.orchestrator", fromlist=["Orchestrator"]
        ).Orchestrator

        async def _log_loop(self_ref, task_spec, sem):
            execution_log.append(task_spec.id)
            async with sem:
                pass

        with (
            patch(f"{_ORCH}.TaskDecomposer", return_value=mock_decomposer),
            patch(f"{_ORCH}.ACPClient"),
            patch.object(OrchestratorClass, "_run_agent_loop", _log_loop),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path=str(tmp_path))
            await orch.run("Build 3 tasks with wave ordering")

        # C must start after A and B
        assert "c" in execution_log
        assert "a" in execution_log
        assert "b" in execution_log
        c_idx = execution_log.index("c")
        a_idx = execution_log.index("a")
        b_idx = execution_log.index("b")
        assert a_idx < c_idx, f"Expected a before c, got: {execution_log}"
        assert b_idx < c_idx, f"Expected b before c, got: {execution_log}"

    @pytest.mark.asyncio
    async def test_run_passes_model_to_acp_client(self, tmp_path):
        """run() with model_profile passes role-specific model to ACPClient."""
        from conductor.orchestrator.models import ModelProfile
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
        # Set role to "executor" to match balanced profile
        tasks[0] = TaskSpec(
            id="t1",
            title="Task t1",
            description="Description for t1",
            role="executor",
            target_file="src/a.py",
        )
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
            orch = Orchestrator(
                state_manager=state_mgr,
                repo_path=str(tmp_path),
                model_profile=ModelProfile.balanced(),
            )
            await orch.run("Build with model routing")

        assert captured_kwargs, "ACPClient was not instantiated"
        assert captured_kwargs[0].get("model") == "claude-haiku-35-20241022", (
            f"Expected haiku model for executor role, got: {captured_kwargs[0].get('model')}"
        )

    @pytest.mark.asyncio
    async def test_run_no_model_profile_omits_model(self, tmp_path):
        """run() without model_profile passes model=None to ACPClient."""
        from conductor.orchestrator.orchestrator import Orchestrator

        tasks = [_make_task_spec("t1", "src/a.py")]
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
            orch = Orchestrator(
                state_manager=state_mgr,
                repo_path=str(tmp_path),
                # No model_profile
            )
            await orch.run("Build without model routing")

        assert captured_kwargs, "ACPClient was not instantiated"
        assert captured_kwargs[0].get("model") is None, (
            f"Expected model=None when no profile, got: {captured_kwargs[0].get('model')}"
        )

    def test_lean_system_prompt_under_500_tokens(self):
        """build_system_prompt() with long task_description stays under 500 tokens."""
        from conductor.orchestrator.identity import AgentIdentity, build_system_prompt

        long_description = "x " * 300  # 600 words — would bloat old prompt
        identity = AgentIdentity(
            name="agent-lean",
            role="backend developer",
            target_file="src/lean.py",
            material_files=["src/models.py", "src/utils.py"],
            task_id="task-lean-1",
            task_description=long_description,
        )
        prompt = build_system_prompt(identity)

        word_count = len(prompt.split())
        assert word_count < 375, (
            f"Lean prompt should be under 375 words (~500 tokens), got {word_count}"
        )
        assert long_description.strip() not in prompt, (
            "Task description should NOT be embedded in lean system prompt"
        )

    def test_acp_client_model_param(self, tmp_path):
        """ACPClient stores model param and passes it to ClaudeAgentOptions."""
        from conductor.acp.client import ACPClient

        with patch("conductor.acp.client.ClaudeAgentOptions") as mock_options_cls:
            mock_options_cls.return_value = MagicMock()
            client_with_model = ACPClient(
                cwd=str(tmp_path),
                model="claude-haiku-35-20241022",
            )
            # model is stored on instance
            assert client_with_model._model == "claude-haiku-35-20241022"
            # model was passed to ClaudeAgentOptions
            call_kwargs = mock_options_cls.call_args[1]
            assert call_kwargs.get("model") == "claude-haiku-35-20241022"

        with patch("conductor.acp.client.ClaudeAgentOptions") as mock_options_cls:
            mock_options_cls.return_value = MagicMock()
            client_no_model = ACPClient(cwd=str(tmp_path))
            assert client_no_model._model is None
            # model should NOT be passed to ClaudeAgentOptions when None
            call_kwargs = mock_options_cls.call_args[1]
            assert "model" not in call_kwargs
