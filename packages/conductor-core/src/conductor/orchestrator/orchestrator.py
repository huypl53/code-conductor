"""ORCH-02: Orchestrator — full decompose-validate-schedule-spawn loop."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from conductor.acp import ACPClient
from conductor.orchestrator.decomposer import TaskDecomposer
from conductor.orchestrator.identity import AgentIdentity, build_system_prompt
from conductor.orchestrator.models import TaskSpec
from conductor.orchestrator.ownership import validate_file_ownership
from conductor.orchestrator.scheduler import DependencyScheduler
from conductor.state import StateManager
from conductor.state.models import (
    AgentRecord,
    AgentStatus,
    ConductorState,
    Task,
    TaskStatus,
)


class Orchestrator:
    """Orchestrates the full feature decomposition and agent spawning lifecycle.

    Usage::

        orch = Orchestrator(state_manager=mgr, repo_path="/path/to/repo")
        await orch.run("Implement user authentication")

    The orchestration loop:
        1. Decompose feature description into a TaskPlan via TaskDecomposer
        2. Validate file ownership (raises FileConflictError on overlap)
        3. Write Task records to state before spawning
        4. Schedule tasks via DependencyScheduler (respects ``requires`` deps)
        5. Spawn agents concurrently up to ``min(plan.max_agents, max_agents)``
        6. Update task status to COMPLETED after each agent finishes

    Args:
        state_manager: StateManager for atomic state mutations.
        repo_path: Absolute path to the repository root (agent cwd).
        max_agents: Hard cap on concurrent agent sessions (default 5).
    """

    def __init__(
        self,
        state_manager: StateManager,
        repo_path: str,
        max_agents: int = 5,
    ) -> None:
        self._state = state_manager
        self._repo_path = repo_path
        self._max_agents = max_agents
        self._decomposer = TaskDecomposer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, feature_description: str) -> None:
        """Execute the full orchestration loop for *feature_description*.

        Args:
            feature_description: Natural language description of the feature
                to be built by the agent team.

        Raises:
            DecompositionError: If task decomposition fails.
            FileConflictError: If any two tasks claim the same target file.
            CycleError: If task dependencies contain a cycle.
        """
        # 1. Decompose
        plan = await self._decomposer.decompose(feature_description)

        # 2. Validate file ownership (raises FileConflictError on overlap)
        validate_file_ownership(
            [(t.id, t.target_file) for t in plan.tasks]
        )

        # 3. Write Task records to state
        await asyncio.to_thread(
            self._state.mutate,
            self._make_add_tasks_fn(plan.tasks),
        )

        # 4. Effective concurrency cap
        effective_max = min(plan.max_agents, self._max_agents)
        sem = asyncio.Semaphore(effective_max)

        # 5. Build scheduler
        scheduler = DependencyScheduler(
            {t.id: set(t.requires) for t in plan.tasks}
        )

        # Index tasks by ID for fast lookup
        task_map = {t.id: t for t in plan.tasks}

        # 6. Spawn loop
        pending: dict[str, asyncio.Task] = {}

        while scheduler.is_active():
            ready_ids = scheduler.get_ready()

            for task_id in ready_ids:
                if task_id not in pending:
                    task_spec = task_map[task_id]
                    pending[task_id] = asyncio.create_task(
                        self._spawn_agent(task_spec, sem)
                    )

            if not pending:
                break

            done_futures, _ = await asyncio.wait(
                pending.values(), return_when=asyncio.FIRST_COMPLETED
            )

            # Mark completed tasks in the scheduler
            for fut in done_futures:
                completed_id = next(
                    tid for tid, t in pending.items() if t is fut
                )
                del pending[completed_id]
                scheduler.done(completed_id)

        # Wait for any stragglers (shouldn't normally happen)
        if pending:
            await asyncio.gather(*pending.values())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _spawn_agent(
        self,
        task_spec: TaskSpec,
        sem: asyncio.Semaphore,
    ) -> None:
        """Acquire semaphore, spawn an agent for *task_spec*, stream to completion.

        Writes an AgentRecord to state before opening the session, then
        updates task status to COMPLETED after the session closes.

        Args:
            task_spec: Task specification for the agent to execute.
            sem: Semaphore limiting concurrent sessions.
        """
        async with sem:
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

            async with ACPClient(
                cwd=self._repo_path,
                system_prompt=system_prompt,
            ) as client:
                await client.send(
                    f"Task {task_spec.id}: {task_spec.description}"
                )
                async for _ in client.stream_response():
                    pass  # consume response stream

            # Update task to COMPLETED
            await asyncio.to_thread(
                self._state.mutate,
                self._make_complete_task_fn(task_spec.id),
            )

    @staticmethod
    def _make_add_tasks_fn(
        tasks: list[TaskSpec],
    ) -> Callable[[ConductorState], None]:
        """Return a mutate fn that adds Task records for each TaskSpec."""

        def _add_tasks(state: ConductorState) -> None:
            existing_ids = {t.id for t in state.tasks}
            for spec in tasks:
                if spec.id not in existing_ids:
                    state.tasks.append(
                        Task(
                            id=spec.id,
                            title=spec.title,
                            description=spec.description,
                            target_file=spec.target_file,
                            material_files=spec.material_files,
                            requires=spec.requires,
                            produces=spec.produces,
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                        )
                    )

        return _add_tasks

    @staticmethod
    def _make_add_agent_fn(
        agent_id: str,
        task_spec: TaskSpec,
    ) -> Callable[[ConductorState], None]:
        """Return a mutate fn that adds an AgentRecord and marks task IN_PROGRESS."""

        def _add_agent(state: ConductorState) -> None:
            state.agents.append(
                AgentRecord(
                    id=agent_id,
                    name=agent_id,
                    role=task_spec.role,
                    current_task_id=task_spec.id,
                    status=AgentStatus.WORKING,
                    registered_at=datetime.now(UTC),
                )
            )
            for task in state.tasks:
                if task.id == task_spec.id:
                    task.status = TaskStatus.IN_PROGRESS  # type: ignore[assignment]
                    task.assigned_agent = agent_id
                    break

        return _add_agent

    @staticmethod
    def _make_complete_task_fn(
        task_id: str,
    ) -> Callable[[ConductorState], None]:
        """Return a mutate fn that sets task status to COMPLETED."""

        def _complete(state: ConductorState) -> None:
            for task in state.tasks:
                if task.id == task_id:
                    task.status = TaskStatus.COMPLETED  # type: ignore[assignment]
                    task.updated_at = datetime.now(UTC)
                    break

        return _complete
