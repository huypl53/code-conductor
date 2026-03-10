"""ORCH-02 tests: Orchestrator class — decompose-validate-schedule-spawn loop."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.orchestrator.errors import FileConflictError
from conductor.orchestrator.models import TaskPlan, TaskSpec
from conductor.state.models import AgentStatus, AgentRecord, TaskStatus


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOrchestrator:
    """ORCH-02: Orchestrator orchestrates the full decompose-validate-schedule-spawn loop."""

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
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient", side_effect=_acp_factory),
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
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient", side_effect=_acp_factory),
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

        def _acp_factory(**kwargs):
            return _make_mock_acp_client()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        original_spawn = None

        async def _patched_spawn(self_ref, task_spec, sem):
            spawn_order.append(task_spec.id)
            async with sem:
                pass

        with (
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient", side_effect=_acp_factory),
            patch.object(
                __import__("conductor.orchestrator.orchestrator", fromlist=["Orchestrator"]).Orchestrator,
                "_spawn_agent",
                _patched_spawn,
            ),
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

        def _acp_factory(**kwargs):
            return _make_mock_acp_client()

        mock_decomposer = AsyncMock()
        mock_decomposer.decompose = AsyncMock(return_value=plan)

        async def _slow_spawn(self_ref, task_spec, sem):
            nonlocal concurrent_high_water, current_concurrent
            async with sem:
                current_concurrent += 1
                if current_concurrent > concurrent_high_water:
                    concurrent_high_water = current_concurrent
                await asyncio.sleep(0.01)
                current_concurrent -= 1

        with (
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient", side_effect=_acp_factory),
            patch.object(
                __import__("conductor.orchestrator.orchestrator", fromlist=["Orchestrator"]).Orchestrator,
                "_spawn_agent",
                _slow_spawn,
            ),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo", max_agents=5)
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
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient", side_effect=_acp_factory),
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

        tasks = [_make_task_spec("t1", "src/auth.py")]
        tasks[0] = TaskSpec(
            id="t1",
            title="Auth Task",
            description="Implement auth",
            role="security engineer",
            target_file="src/auth.py",
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
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient", side_effect=_acp_factory),
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

        async def _capture_spawn(self_ref, task_spec, sem):
            semaphore_values.append(sem._value)  # asyncio.Semaphore internal
            async with sem:
                pass

        with (
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient"),
            patch.object(
                __import__("conductor.orchestrator.orchestrator", fromlist=["Orchestrator"]).Orchestrator,
                "_spawn_agent",
                _capture_spawn,
            ),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo", max_agents=3)
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
            # Capture any mutation that sets status to COMPLETED
            # We check via a dummy state
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
            patch("conductor.orchestrator.orchestrator.TaskDecomposer", return_value=mock_decomposer),
            patch("conductor.orchestrator.orchestrator.ACPClient", side_effect=_acp_factory),
        ):
            orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
            await orch.run("Build one task")

        assert "t1" in completed_task_ids, \
            f"Task t1 was not marked COMPLETED. Mutations recorded: {completed_task_ids}"
