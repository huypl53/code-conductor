"""ORCH-02/05: Orchestrator — full decompose-validate-schedule-spawn loop.

Includes observe-review-revise cycle (ORCH-04/05).
COMM-05/06/07: Intervention methods — cancel/reassign, inject guidance, pause/resume.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from conductor.acp import ACPClient
from conductor.orchestrator.decomposer import TaskDecomposer
from conductor.orchestrator.errors import EscalationError
from conductor.orchestrator.escalation import HumanQuery
from conductor.orchestrator.identity import AgentIdentity, build_system_prompt
from conductor.orchestrator.models import TaskSpec
from conductor.orchestrator.monitor import StreamMonitor
from conductor.orchestrator.ownership import validate_file_ownership
from conductor.orchestrator.reviewer import ReviewVerdict, review_output
from conductor.orchestrator.scheduler import DependencyScheduler
from conductor.state import StateManager
from conductor.state.models import (
    AgentRecord,
    AgentStatus,
    ConductorState,
    ReviewStatus,
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
        6. Run observe-review-revise cycle for each agent
        7. Update task status to COMPLETED after review passes or max_revisions hit

    Args:
        state_manager: StateManager for atomic state mutations.
        repo_path: Absolute path to the repository root (agent cwd).
        max_agents: Hard cap on concurrent agent sessions (default 10).
            The decomposer's TaskPlan.max_agents (1-10 per schema) is the
            binding constraint when <= self._max_agents.
        max_revisions: Maximum revision cycles before best-effort
            completion (default 2).
    """

    def __init__(
        self,
        state_manager: StateManager,
        repo_path: str,
        max_agents: int = 10,
        max_revisions: int = 2,
    ) -> None:
        self._state = state_manager
        self._repo_path = repo_path
        self._max_agents = max_agents
        self._max_revisions = max_revisions
        self._decomposer = TaskDecomposer()
        # COMM-05/06/07: active session registries for intervention methods
        self._active_clients: dict[str, ACPClient] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._semaphore: asyncio.Semaphore | None = None

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
        self._semaphore = sem

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
                    t = asyncio.create_task(
                        self._run_agent_loop(task_spec, sem)
                    )
                    pending[task_id] = t
                    self._active_tasks[task_id] = t

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
                self._active_tasks.pop(completed_id, None)
                scheduler.done(completed_id)

        # Wait for any stragglers (shouldn't normally happen)
        if pending:
            await asyncio.gather(*pending.values())

    # ------------------------------------------------------------------
    # Intervention methods (COMM-05/06/07)
    # ------------------------------------------------------------------

    async def cancel_agent(
        self, agent_id: str, corrected_spec: TaskSpec
    ) -> None:
        """Cancel a running agent session and reassign with corrected instructions.

        COMM-05: Cancels the asyncio.Task for *agent_id* (if running), awaits
        cancellation, then spawns a new ``_run_agent_loop`` with *corrected_spec*
        in a fresh session.  If *agent_id* is not in ``_active_tasks``, the cancel
        is a no-op and a new session is still spawned (idempotent).

        Args:
            agent_id: ID of the running agent to cancel.
            corrected_spec: TaskSpec with corrected instructions for the new session.
        """
        existing_task = self._active_tasks.pop(agent_id, None)
        if existing_task is not None:
            existing_task.cancel()
            try:
                await existing_task
            except (asyncio.CancelledError, Exception):
                pass

        sem = self._semaphore or asyncio.Semaphore(self._max_agents)
        new_task = asyncio.create_task(
            self._run_agent_loop(corrected_spec, sem)
        )
        self._active_tasks[corrected_spec.id] = new_task

    async def inject_guidance(self, agent_id: str, guidance: str) -> None:
        """Send a guidance message to a running agent without interrupting its session.

        COMM-06: Calls ``client.send(guidance)`` on the active client for *agent_id*.
        The agent's stream continues — no interrupt is issued.

        Args:
            agent_id: ID of the running agent.
            guidance: Guidance message to inject into the agent's context.

        Raises:
            EscalationError: If *agent_id* is not in ``_active_clients``.
        """
        client = self._active_clients.get(agent_id)
        if client is None:
            raise EscalationError(
                f"inject_guidance: agent '{agent_id}' is not active"
            )
        await client.send(guidance)

    async def pause_for_human_decision(
        self,
        agent_id: str,
        question: str,
        human_out: asyncio.Queue,
        human_in: asyncio.Queue,
        timeout: float = 120.0,
    ) -> None:
        """Interrupt an agent, escalate a question to a human, then resume.

        COMM-07: Calls ``client.interrupt()``, drains ``stream_response()`` to
        avoid stale message corruption, pushes a :class:`HumanQuery` to
        *human_out*, waits for an answer from *human_in* (with *timeout* fallback),
        then resumes the agent via ``client.send()``.

        Args:
            agent_id: ID of the running agent to pause.
            question: Question to present to the human.
            human_out: Queue where :class:`HumanQuery` objects are pushed.
            human_in: Queue from which the human's text answer is read.
            timeout: Seconds to wait for a human response (default 120s).
                On timeout, falls back to ``"proceed with best judgment"``.

        Raises:
            EscalationError: If *agent_id* is not in ``_active_clients``.
        """
        client = self._active_clients.get(agent_id)
        if client is None:
            raise EscalationError(
                f"pause_for_human_decision: agent '{agent_id}' is not active"
            )

        await client.interrupt()

        # Drain any in-flight stream messages to prevent stale message corruption
        async for _ in client.stream_response():
            pass

        # Push question to human
        query = HumanQuery(question=question, context={})
        await human_out.put(query)

        # Wait for human answer with timeout fallback
        try:
            decision = await asyncio.wait_for(human_in.get(), timeout=timeout)
        except TimeoutError:
            decision = "proceed with best judgment"

        await client.send(
            f"Human decision: {decision}. Continue your work with this guidance."
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_agent_loop(
        self,
        task_spec: TaskSpec,
        sem: asyncio.Semaphore,
        max_revisions: int | None = None,
    ) -> None:
        """Acquire semaphore, run the observe-review-revise cycle for *task_spec*.

        The entire revision loop runs inside a single ``async with ACPClient``
        block — the session stays open between review and revision feedback.
        Task status is only set to COMPLETED after review passes, or after
        ``max_revisions`` exhaustion (best-effort).

        Args:
            task_spec: Task specification for the agent to execute.
            sem: Semaphore limiting concurrent sessions.
            max_revisions: Override for max revision cycles
                (uses instance default if None).
        """
        if max_revisions is None:
            max_revisions = self._max_revisions

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

            final_verdict: ReviewVerdict | None = None
            revision_num = 0

            async with ACPClient(
                cwd=self._repo_path,
                system_prompt=system_prompt,
            ) as client:
                self._active_clients[agent_id] = client
                try:
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

            # After session closes, update state with review result
            review_status = (
                ReviewStatus.APPROVED
                if final_verdict and final_verdict.approved
                else ReviewStatus.NEEDS_REVISION
            )

            await asyncio.to_thread(
                self._state.mutate,
                self._make_complete_task_fn(
                    task_spec.id,
                    review_status=review_status,
                    revision_count=revision_num,
                ),
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
        review_status: ReviewStatus = ReviewStatus.APPROVED,
        revision_count: int = 0,
    ) -> Callable[[ConductorState], None]:
        """Return a mutate fn that sets task COMPLETED with review metadata."""

        def _complete(state: ConductorState) -> None:
            for task in state.tasks:
                if task.id == task_id:
                    task.status = TaskStatus.COMPLETED  # type: ignore[assignment]
                    task.review_status = review_status  # type: ignore[assignment]
                    task.revision_count = revision_count
                    task.updated_at = datetime.now(UTC)
                    break

        return _complete
