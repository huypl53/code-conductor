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
