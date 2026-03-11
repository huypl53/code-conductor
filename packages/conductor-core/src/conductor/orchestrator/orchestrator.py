"""ORCH-02/05: Orchestrator — full decompose-validate-schedule-spawn loop.

Includes observe-review-revise cycle (ORCH-04/05).
COMM-05/06/07: Intervention methods — cancel/reassign, inject guidance, pause/resume.
RUNT-03/04/05: Mode wiring, .memory/ creation, session persistence, spec review.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from pydantic import BaseModel, Field

from conductor.acp import ACPClient
from conductor.acp.permission import PermissionHandler
from conductor.orchestrator.decomposer import TaskDecomposer
from conductor.orchestrator.errors import DecompositionError, EscalationError
from conductor.orchestrator.escalation import EscalationRouter, HumanQuery
from conductor.orchestrator.identity import AgentIdentity, build_system_prompt
from conductor.orchestrator.models import TaskSpec
from conductor.orchestrator.monitor import StreamMonitor
from conductor.orchestrator.ownership import validate_file_ownership
from conductor.orchestrator.reviewer import ReviewVerdict, review_output
from conductor.orchestrator.scheduler import DependencyScheduler
from conductor.orchestrator.session_registry import SessionRegistry
from conductor.state import StateManager
from conductor.state.models import (
    AgentRecord,
    AgentStatus,
    ConductorState,
    ReviewStatus,
    Task,
    TaskStatus,
)

logger = logging.getLogger("conductor.orchestrator")

# ---------------------------------------------------------------------------
# Spec review model and prompt (RUNT-04)
# ---------------------------------------------------------------------------

_SPEC_REVIEW_MAX_TURNS = 2


class SpecReview(BaseModel):
    """Structured output from pre_run_review() spec analysis."""

    is_clear: bool
    issues: list[str] = Field(default_factory=list)
    confirmed_description: str


SPEC_REVIEW_PROMPT_TEMPLATE = """\
You are a technical architect reviewing a feature specification before execution.
Analyse the following feature description for completeness and technical risks.
Identify any ambiguities that could lead to incorrect implementations.

<feature_description>
{feature_description}
</feature_description>

Return a SpecReview JSON object with:
- is_clear: bool — whether the spec is clear enough to proceed without ambiguity
- issues: list[str] — any ambiguities or risks identified (empty list if none)
- confirmed_description: str — the spec as you understand it, filling gaps with
  reasonable best-judgment assumptions
"""


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
        mode: Execution mode — ``"auto"`` (fully autonomous) or
            ``"interactive"`` (escalate low-confidence decisions to human).
        human_out: Queue where :class:`HumanQuery` objects are pushed for
            human review. Only used in ``interactive`` mode.
        human_in: Queue from which the human's text answer is read.
            Only used in ``interactive`` mode.
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
        mode: str = "auto",
        human_out: asyncio.Queue | None = None,
        human_in: asyncio.Queue | None = None,
        max_agents: int = 10,
        max_revisions: int = 2,
    ) -> None:
        self._state = state_manager
        self._repo_path = repo_path
        self._mode = mode
        self._human_out = human_out
        self._human_in = human_in
        self._max_agents = max_agents
        self._max_revisions = max_revisions
        self._decomposer = TaskDecomposer()
        self._escalation_router = EscalationRouter(
            mode=mode,
            human_out=human_out,
            human_in=human_in,
        )
        # Load (or create) session registry from .conductor/sessions.json
        _sessions_path = (
            Path(repo_path) / ".conductor" / "sessions.json"
        )
        self._session_registry = SessionRegistry.load(_sessions_path)
        self._sessions_path = _sessions_path
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
        # 0. Ensure .memory/ directory exists before spawning agents
        memory_dir = Path(self._repo_path) / ".memory"
        memory_dir.mkdir(parents=True, exist_ok=True)

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

    async def pre_run_review(self, feature_description: str) -> str:
        """Analyse *feature_description* before execution and return confirmed spec.

        Runs a single-exchange SDK query (no ClaudeSDKClient, no PermissionHandler,
        no escalation) to surface ambiguities and commit to an interpretation.
        This is the ONLY point in auto mode where issues can be flagged — after
        this call, execution is fully autonomous.

        Args:
            feature_description: Raw feature description from the user.

        Returns:
            The confirmed (possibly refined) feature description string.

        Raises:
            DecompositionError: If the SDK returns no result or no structured output.
        """
        prompt = SPEC_REVIEW_PROMPT_TEMPLATE.format(
            feature_description=feature_description
        )
        options = ClaudeAgentOptions(
            output_format={
                "type": "json_schema",
                "schema": SpecReview.model_json_schema(),
            },
            max_turns=_SPEC_REVIEW_MAX_TURNS,
        )

        result: ResultMessage | None = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result = message
                break

        if result is None:
            raise DecompositionError(
                "Spec review failed: no result received from query"
            )

        if result.structured_output is None:
            raise DecompositionError(
                "Spec review failed: no structured output in result"
            )

        review = SpecReview.model_validate(result.structured_output)

        if not review.is_clear and review.issues:
            logger.warning(
                "Spec review identified issues before execution: %s",
                review.issues,
            )

        return review.confirmed_description

    async def run_auto(self, feature_description: str) -> None:
        """Auto-mode entry point: review spec upfront then run autonomously.

        Calls :meth:`pre_run_review` for upfront spec analysis, then passes
        the confirmed description to :meth:`run`. After ``pre_run_review``
        completes, execution is fully autonomous — no human input is requested.

        Args:
            feature_description: Natural language feature description from user.

        Raises:
            DecompositionError: If spec review fails.
            FileConflictError: If any two tasks claim the same target file.
            CycleError: If task dependencies contain a cycle.
        """
        confirmed = await self.pre_run_review(feature_description)
        await self.run(confirmed)

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

        # Identify completed tasks (handled as immediate done() in spawn loop)
        completed_ids = {
            t.id for t in state.tasks
            if t.status == TaskStatus.COMPLETED
        }

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

            marked_done = False
            for task_id in ready_ids:
                if task_id in completed_ids:
                    scheduler.done(task_id)
                    marked_done = True
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

            # If we only marked completed tasks done, loop again to get
            # newly-unblocked tasks before waiting on pending futures
            if not pending and marked_done:
                continue
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

    # ------------------------------------------------------------------
    # Intervention methods (COMM-05/06/07)
    # ------------------------------------------------------------------

    async def cancel_agent(
        self, agent_id: str, new_instructions: str | None = None
    ) -> None:
        """Cancel a running agent session and re-spawn with original or updated instructions.

        COMM-05: Cancels the asyncio.Task for *agent_id* (if running), awaits
        cancellation, then reconstructs the TaskSpec from state and spawns a new
        ``_run_agent_loop``.  If *new_instructions* is provided the re-spawned
        agent receives the new description; otherwise the original task description
        is used.  If *agent_id* is not in state (unknown agent), returns early
        without raising (safe no-op).

        Args:
            agent_id: ID of the running agent to cancel.
            new_instructions: Optional replacement description for the re-spawned
                agent.  If None, the original task description is preserved.
                Corresponds to the CLI ``redirect`` command's new-instructions arg.
        """
        existing_task = self._active_tasks.pop(agent_id, None)
        if existing_task is not None:
            existing_task.cancel()
            try:
                await existing_task
            except (asyncio.CancelledError, Exception):
                pass

        # Reconstruct TaskSpec from state so the caller need not supply it
        state = await asyncio.to_thread(self._state.read_state)
        agent_rec = next((a for a in state.agents if a.id == agent_id), None)
        task_id = agent_rec.current_task_id if agent_rec else None
        task = next((t for t in state.tasks if t.id == task_id), None)

        if task is None:
            # Unknown agent or no task assigned — safe no-op, nothing to re-spawn
            return

        corrected_spec = TaskSpec(
            id=task.id,
            title=task.title,
            description=new_instructions if new_instructions else task.description,
            role=agent_rec.role if agent_rec else "developer",
            target_file=task.target_file or "",
            material_files=task.material_files,
            requires=task.requires,
            produces=task.produces,
        )

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

        # Set agent status to WAITING before escalating to human
        await asyncio.to_thread(
            self._state.mutate,
            self._make_set_agent_status_fn(agent_id, AgentStatus.WAITING),
        )

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

        # Restore agent status to WORKING after human response received
        await asyncio.to_thread(
            self._state.mutate,
            self._make_set_agent_status_fn(agent_id, AgentStatus.WORKING),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_agent_loop(
        self,
        task_spec: TaskSpec,
        sem: asyncio.Semaphore,
        max_revisions: int | None = None,
        resume_session_id: str | None = None,
        review_only: bool = False,
    ) -> None:
        """Acquire semaphore, run the observe-review-revise cycle for *task_spec*.

        The entire revision loop runs inside a single ``async with ACPClient``
        block — the session stays open between review and revision feedback.
        Task status is only set to COMPLETED after review passes, or after
        ``max_revisions`` exhaustion (best-effort).

        When *review_only* is True, the agent execution is skipped entirely
        and only a review of the existing file on disk is performed (no
        semaphore acquired). This is used during ``resume()`` for in-progress
        tasks whose target file already exists.

        Args:
            task_spec: Task specification for the agent to execute.
            sem: Semaphore limiting concurrent sessions.
            max_revisions: Override for max revision cycles
                (uses instance default if None).
            resume_session_id: SDK session ID to resume an existing conversation.
                If None, a new session is started.
            review_only: If True, skip agent execution and semaphore, run
                review only.
        """
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
                        # Persist session_id BEFORE sending first message (crash safety)
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
                                    "get_server_info() unavailable or failed "
                                    "for agent %s — skipping session_id persist",
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
                    memory_file=f".memory/{agent_id}.md",
                    started_at=datetime.now(UTC),
                )
            )
            for task in state.tasks:
                if task.id == task_spec.id:
                    task.status = TaskStatus.IN_PROGRESS  # type: ignore[assignment]
                    task.assigned_agent = agent_id
                    break

        return _add_agent

    @staticmethod
    def _make_save_session_fn(
        agent_id: str,
        session_id: str,
    ) -> Callable[[ConductorState], None]:
        """Return a mutate fn that saves the session_id to the AgentRecord."""

        def _save_session(state: ConductorState) -> None:
            for agent in state.agents:
                if agent.id == agent_id:
                    agent.session_id = session_id
                    break

        return _save_session

    @staticmethod
    def _make_complete_task_fn(
        task_id: str,
        agent_id: str,
        review_status: ReviewStatus = ReviewStatus.APPROVED,
        revision_count: int = 0,
    ) -> Callable[[ConductorState], None]:
        """Return a mutate fn that sets task COMPLETED with review metadata and agent DONE."""

        def _complete(state: ConductorState) -> None:
            for task in state.tasks:
                if task.id == task_id:
                    task.status = TaskStatus.COMPLETED  # type: ignore[assignment]
                    task.review_status = review_status  # type: ignore[assignment]
                    task.revision_count = revision_count
                    task.updated_at = datetime.now(UTC)
                    break
            for agent in state.agents:
                if agent.id == agent_id:
                    agent.status = AgentStatus.DONE
                    break

        return _complete

    @staticmethod
    def _make_set_agent_status_fn(
        agent_id: str,
        status: AgentStatus,
    ) -> Callable[[ConductorState], None]:
        """Return a mutate fn that sets an agent's status."""

        def _set_status(state: ConductorState) -> None:
            for agent in state.agents:
                if agent.id == agent_id:
                    agent.status = status
                    break

        return _set_status
