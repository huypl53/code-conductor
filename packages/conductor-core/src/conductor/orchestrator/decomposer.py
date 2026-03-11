"""ORCH-01: TaskDecomposer — structured decomposition via SDK query()."""
from __future__ import annotations

import logging

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from conductor.orchestrator.errors import DecompositionError
from conductor.orchestrator.models import (
    ComplexityAnalysis,
    ComplexityAnalysisResult,
    ExpansionResult,
    TaskPlan,
    TaskSpec,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Decomposition prompt template
# ---------------------------------------------------------------------------

DECOMPOSE_PROMPT_TEMPLATE = """\
You are a software architect and project coordinator. \
You do not write code. Your only job is to decompose a feature description \
into a structured task plan that can be assigned to coding agents.

Analyse the feature description below and produce a TaskPlan JSON object.
Each task must specify exactly one target_file that the agent will modify.
Tasks may declare file dependencies using the requires field (list of other task IDs).

<feature_description>
{feature_description}
</feature_description>

Return a valid TaskPlan JSON object according to the provided schema.
"""

# ---------------------------------------------------------------------------
# Complexity analysis prompt template
# ---------------------------------------------------------------------------

COMPLEXITY_PROMPT_TEMPLATE = """\
You are a software architect. Analyse the complexity of each task below and \
score each on a 1-10 scale where 1 is trivial and 10 is highly complex.

For each task, provide:
- A complexity_score (1-10)
- reasoning explaining why this score was given
- An expansion_prompt: specific AI guidance for how to expand this task into sub-tasks \
  (include file names, interfaces, and specific steps)
- recommended_subtasks: how many sub-tasks this should be broken into (2-5)

Tasks to analyse:
{task_list}

Return a ComplexityAnalysisResult JSON object with all analyses.
"""

# ---------------------------------------------------------------------------
# Expansion prompt template
# ---------------------------------------------------------------------------

EXPANSION_PROMPT_TEMPLATE = """\
You are a software architect. Expand the following task into {recommended_subtasks} \
specific sub-tasks. Each sub-task must target a specific file and have a clear, \
actionable description.

Parent task:
- ID: {task_id}
- Title: {task_title}
- Description: {task_description}
- Role: {task_role}
- Target file: {task_target_file}

Expansion guidance (follow this carefully):
{expansion_prompt}

Rules:
- Sub-tasks should form a natural sequential dependency chain
- Each sub-task should have a specific, different target_file where possible
- Sub-task descriptions must be specific and actionable
- Do NOT include requires or produces in sub-tasks — these will be set automatically

Return an ExpansionResult JSON object with the subtasks list.
"""

_MAX_TURNS = 3


class TaskDecomposer:
    """Decomposes a feature description into a TaskPlan via SDK structured output.

    Uses a three-phase pipeline:
    1. Decompose: Initial decomposition via SDK structured output
    2. Analyze complexity: Score each task for complexity (1-10)
    3. Selective expansion: Expand tasks above complexity_threshold into sub-tasks

    Raises:
        DecompositionError: If the initial SDK decomposition fails.
            Complexity analysis and expansion failures are handled gracefully
            (fallback to original plan).
    """

    def __init__(self, complexity_threshold: int = 5) -> None:
        """Initialize TaskDecomposer.

        Args:
            complexity_threshold: Tasks with complexity_score > threshold are expanded.
                Defaults to 5. Must be an integer between 1 and 10.
        """
        self._complexity_threshold = complexity_threshold

    async def decompose(self, feature_description: str) -> TaskPlan:
        """Decompose *feature_description* into a TaskPlan.

        Three-phase pipeline:
        1. Initial decomposition (SDK call 1)
        2. Complexity analysis (SDK call 2)
        3. Selective expansion for complex tasks (SDK call 3+ per task)

        Args:
            feature_description: Natural language description of the feature
                to be implemented.

        Returns:
            A validated TaskPlan containing task specs for the feature.
            Tasks above the complexity threshold are expanded into sub-tasks.

        Raises:
            DecompositionError: On schema retry exhaustion, empty response,
                or None structured output during initial decomposition.
        """
        # Phase 1: Initial decomposition
        prompt = DECOMPOSE_PROMPT_TEMPLATE.format(
            feature_description=feature_description
        )
        options = ClaudeAgentOptions(
            output_format={
                "type": "json_schema",
                "schema": TaskPlan.model_json_schema(),
            },
            max_turns=_MAX_TURNS,
        )

        result: ResultMessage | None = None

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                if message.subtype == "error_max_structured_output_retries":
                    raise DecompositionError(
                        "Decomposition failed: max structured output "
                        "retry limit reached"
                    )
                result = message
                # Don't break — consume entire stream to avoid anyio
                # cancel scope cleanup issues

        if result is None:
            raise DecompositionError(
                "No result received from decomposition query"
            )

        if result.structured_output is None:
            raise DecompositionError(
                "No structured output in decomposition result"
            )

        plan = TaskPlan.model_validate(result.structured_output)

        # Phase 2: Complexity analysis
        analyses = await self._analyze_complexity(plan)

        if analyses is None:
            # Analysis failed — return original plan unchanged (backward compat)
            return plan

        # Populate complexity_score and reasoning on each task
        analysis_map = {a.task_id: a for a in analyses}
        for task in plan.tasks:
            if task.id in analysis_map:
                a = analysis_map[task.id]
                task.complexity_score = a.complexity_score
                task.reasoning = a.reasoning

        # Phase 3: Selective expansion of complex tasks
        plan = await self._expand_complex_tasks(plan, analyses)

        return plan

    async def _analyze_complexity(
        self, plan: TaskPlan
    ) -> list[ComplexityAnalysis] | None:
        """Analyze complexity of all tasks in the plan.

        Args:
            plan: The initial TaskPlan from decomposition.

        Returns:
            List of ComplexityAnalysis objects on success, None on any failure.
        """
        try:
            task_list = "\n".join(
                f"- ID: {t.id}, Title: {t.title}, Description: {t.description}, "
                f"Target file: {t.target_file}"
                for t in plan.tasks
            )
            prompt = COMPLEXITY_PROMPT_TEMPLATE.format(task_list=task_list)
            options = ClaudeAgentOptions(
                output_format={
                    "type": "json_schema",
                    "schema": ComplexityAnalysisResult.model_json_schema(),
                },
                max_turns=_MAX_TURNS,
            )

            result: ResultMessage | None = None

            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    result = message

            if result is None or result.structured_output is None:
                logger.warning("Complexity analysis returned no result — falling back")
                return None

            analysis_result = ComplexityAnalysisResult.model_validate(
                result.structured_output
            )
            return analysis_result.analyses

        except Exception as exc:
            logger.warning("Complexity analysis failed: %s — falling back", exc)
            return None

    async def _expand_task(
        self, task: TaskSpec, analysis: ComplexityAnalysis
    ) -> list[TaskSpec] | None:
        """Expand a single complex task into sub-tasks via SDK call.

        Args:
            task: The task to expand.
            analysis: The complexity analysis for this task.

        Returns:
            List of sub-TaskSpec objects on success, None on failure.
            The caller will keep the original task if None is returned.
        """
        try:
            prompt = EXPANSION_PROMPT_TEMPLATE.format(
                recommended_subtasks=analysis.recommended_subtasks,
                task_id=task.id,
                task_title=task.title,
                task_description=task.description,
                task_role=task.role,
                task_target_file=task.target_file,
                expansion_prompt=analysis.expansion_prompt,
            )
            options = ClaudeAgentOptions(
                output_format={
                    "type": "json_schema",
                    "schema": ExpansionResult.model_json_schema(),
                },
                max_turns=_MAX_TURNS,
            )

            result: ResultMessage | None = None

            async for message in query(prompt=prompt, options=options):
                if isinstance(message, ResultMessage):
                    result = message

            if result is None or result.structured_output is None:
                logger.warning(
                    "Expansion of task %s returned no result — keeping original",
                    task.id,
                )
                return None

            expansion = ExpansionResult.model_validate(result.structured_output)
            subtasks = expansion.subtasks

            if not subtasks:
                logger.warning(
                    "Expansion of task %s produced no subtasks — keeping original",
                    task.id,
                )
                return None

            # Assign sequential IDs and dependency chain
            numbered: list[TaskSpec] = []
            for i, subtask in enumerate(subtasks):
                new_id = f"{task.id}.{i + 1}"
                # Build requires chain: first subtask is independent, rest depend on previous
                requires: list[str] = [] if i == 0 else [f"{task.id}.{i}"]
                numbered.append(
                    TaskSpec(
                        id=new_id,
                        title=subtask.title,
                        description=subtask.description,
                        role=task.role,  # inherit parent role
                        target_file=subtask.target_file,
                        material_files=subtask.material_files,
                        requires=requires,
                        produces=subtask.produces,
                    )
                )

            return numbered

        except Exception as exc:
            logger.warning(
                "Expansion of task %s failed: %s — keeping original", task.id, exc
            )
            return None

    async def _expand_complex_tasks(
        self, plan: TaskPlan, analyses: list[ComplexityAnalysis]
    ) -> TaskPlan:
        """Expand tasks above the complexity threshold into sub-tasks.

        For each task in the plan:
        - If complexity_score > threshold: attempt expansion via SDK call
        - If expansion succeeds: replace task with sub-tasks
        - If expansion fails: keep original task

        After all expansions, dependency rewiring is performed: any task whose
        `requires` references an expanded task is updated to reference that
        task's last sub-task instead.

        Args:
            plan: The TaskPlan with complexity scores populated.
            analyses: The list of ComplexityAnalysis objects from analysis phase.

        Returns:
            A new TaskPlan with expanded tasks and rewired dependencies.
        """
        analysis_map = {a.task_id: a for a in analyses}
        # Track which original task IDs were expanded and their last subtask ID
        expansion_map: dict[str, str] = {}  # original_id -> last_subtask_id

        new_tasks: list[TaskSpec] = []

        for task in plan.tasks:
            analysis = analysis_map.get(task.id)
            should_expand = (
                analysis is not None
                and task.complexity_score is not None
                and task.complexity_score > self._complexity_threshold
            )

            if should_expand:
                subtasks = await self._expand_task(task, analysis)  # type: ignore[arg-type]
                if subtasks:
                    new_tasks.extend(subtasks)
                    # Record the last subtask ID for dependency rewiring
                    expansion_map[task.id] = subtasks[-1].id
                else:
                    # Expansion failed — keep original task
                    new_tasks.append(task)
            else:
                new_tasks.append(task)

        # Dependency rewiring: update requires fields to point to last subtask
        if expansion_map:
            for task in new_tasks:
                if task.requires:
                    task.requires = [
                        expansion_map.get(req, req) for req in task.requires
                    ]

        return TaskPlan(
            feature_name=plan.feature_name,
            tasks=new_tasks,
            max_agents=plan.max_agents,
        )
