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
