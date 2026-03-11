"""ORCH-01 tests: TaskDecomposer with mocked SDK query()."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.orchestrator.errors import DecompositionError
from conductor.orchestrator.models import TaskPlan, TaskSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task_spec_dict(task_id: str = "t1", target_file: str = "src/foo.py") -> dict:
    return {
        "id": task_id,
        "title": f"Task {task_id}",
        "description": f"Description for {task_id}",
        "role": "backend developer",
        "target_file": target_file,
        "material_files": [],
        "requires": [],
        "produces": [],
    }


def _make_task_plan_dict(feature_name: str = "MyFeature", task_count: int = 2) -> dict:
    return {
        "feature_name": feature_name,
        "tasks": [_make_task_spec_dict(f"t{i+1}", f"src/file{i+1}.py") for i in range(task_count)],
        "max_agents": 4,
    }


async def _async_gen(*messages):
    """Helper that yields messages from an async generator."""
    for msg in messages:
        yield msg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTaskDecomposer:
    """ORCH-01: TaskDecomposer produces TaskPlan via SDK query() structured output."""

    @pytest.mark.asyncio
    async def test_decompose_returns_valid_taskplan(self):
        """Mock query() to yield a ResultMessage with valid structured output."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        plan_dict = _make_task_plan_dict("LoginFeature", task_count=2)
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="sess-001",
            structured_output=plan_dict,
        )

        async def _mock_query(**kwargs):
            yield result_msg

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            plan = await decomposer.decompose("Build a login feature")

        assert isinstance(plan, TaskPlan)
        assert plan.feature_name == "LoginFeature"
        assert len(plan.tasks) == 2

    @pytest.mark.asyncio
    async def test_decompose_retry_error(self):
        """Mock query() to yield a ResultMessage with error_max_structured_output_retries."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        error_msg = ResultMessage(
            subtype="error_max_structured_output_retries",
            duration_ms=100,
            duration_api_ms=80,
            is_error=True,
            num_turns=3,
            session_id="sess-002",
            structured_output=None,
        )

        async def _mock_query(**kwargs):
            yield error_msg

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            with pytest.raises(DecompositionError, match="retry"):
                await decomposer.decompose("Build a feature")

    @pytest.mark.asyncio
    async def test_decompose_no_result(self):
        """Mock query() to yield nothing — no ResultMessage at all."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        async def _mock_query(**kwargs):
            return
            yield  # make it an async generator

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            with pytest.raises(DecompositionError, match="[Nn]o result"):
                await decomposer.decompose("Build a feature")

    @pytest.mark.asyncio
    async def test_decompose_none_structured_output(self):
        """Mock query() to yield ResultMessage with structured_output=None."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="sess-003",
            structured_output=None,
        )

        async def _mock_query(**kwargs):
            yield result_msg

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            with pytest.raises(DecompositionError, match="[Nn]o structured"):
                await decomposer.decompose("Build a feature")

    @pytest.mark.asyncio
    async def test_prompt_contains_xml_boundary(self):
        """Verify the prompt passed to query() wraps the feature description in XML tags."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        captured_kwargs: list[dict] = []

        plan_dict = _make_task_plan_dict("XmlTest", 1)
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="sess-004",
            structured_output=plan_dict,
        )

        async def _mock_query(**kwargs):
            captured_kwargs.append(kwargs)
            yield result_msg

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            await decomposer.decompose("Add XML boundary feature")

        assert captured_kwargs, "query() was not called"
        prompt = captured_kwargs[0]["prompt"]
        assert "<feature_description>" in prompt
        assert "</feature_description>" in prompt
        assert "Add XML boundary feature" in prompt

    @pytest.mark.asyncio
    async def test_prompt_contains_role_anchoring(self):
        """Verify prompt includes role anchoring and 'do not write code' constraint."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        captured_kwargs: list[dict] = []

        plan_dict = _make_task_plan_dict("RoleAnchorTest", 1)
        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="sess-005",
            structured_output=plan_dict,
        )

        async def _mock_query(**kwargs):
            captured_kwargs.append(kwargs)
            yield result_msg

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            await decomposer.decompose("Build role anchored feature")

        assert captured_kwargs, "query() was not called"
        prompt = captured_kwargs[0]["prompt"]
        prompt_lower = prompt.lower()
        # Must contain "coordinator" or "architect"
        assert "coordinator" in prompt_lower or "architect" in prompt_lower
        # Must contain "do not write code"
        assert "do not write code" in prompt_lower


# ---------------------------------------------------------------------------
# Tests: ComplexityAnalysis model (Task 1 — TDD RED)
# ---------------------------------------------------------------------------


class TestComplexityAnalysisModel:
    """Tests for the ComplexityAnalysis and ComplexityAnalysisResult models."""

    def test_complexity_analysis_validates(self):
        """ComplexityAnalysis model validates with required fields."""
        from conductor.orchestrator.models import ComplexityAnalysis

        analysis = ComplexityAnalysis(
            task_id="t1",
            complexity_score=7,
            reasoning="This task requires multiple system interactions",
            expansion_prompt="Break down into: data layer, service layer, API layer",
            recommended_subtasks=3,
        )
        assert analysis.task_id == "t1"
        assert analysis.complexity_score == 7
        assert analysis.recommended_subtasks == 3

    def test_complexity_analysis_score_bounds(self):
        """ComplexityAnalysis rejects scores outside 1-10."""
        from pydantic import ValidationError

        from conductor.orchestrator.models import ComplexityAnalysis

        with pytest.raises(ValidationError):
            ComplexityAnalysis(
                task_id="t1",
                complexity_score=0,
                reasoning="Too low",
                expansion_prompt="n/a",
            )
        with pytest.raises(ValidationError):
            ComplexityAnalysis(
                task_id="t1",
                complexity_score=11,
                reasoning="Too high",
                expansion_prompt="n/a",
            )

    def test_complexity_analysis_recommended_subtasks_bounds(self):
        """recommended_subtasks is bounded to 2-5."""
        from pydantic import ValidationError

        from conductor.orchestrator.models import ComplexityAnalysis

        with pytest.raises(ValidationError):
            ComplexityAnalysis(
                task_id="t1",
                complexity_score=5,
                reasoning="ok",
                expansion_prompt="n/a",
                recommended_subtasks=1,
            )
        with pytest.raises(ValidationError):
            ComplexityAnalysis(
                task_id="t1",
                complexity_score=5,
                reasoning="ok",
                expansion_prompt="n/a",
                recommended_subtasks=6,
            )

    def test_complexity_analysis_result_wraps_list(self):
        """ComplexityAnalysisResult wraps a list of ComplexityAnalysis objects."""
        from conductor.orchestrator.models import (
            ComplexityAnalysis,
            ComplexityAnalysisResult,
        )

        result = ComplexityAnalysisResult(
            analyses=[
                ComplexityAnalysis(
                    task_id="t1",
                    complexity_score=3,
                    reasoning="Simple task",
                    expansion_prompt="n/a",
                ),
                ComplexityAnalysis(
                    task_id="t2",
                    complexity_score=8,
                    reasoning="Complex task",
                    expansion_prompt="Break into multiple steps",
                ),
            ]
        )
        assert len(result.analyses) == 2

    def test_taskspec_has_optional_complexity_fields(self):
        """TaskSpec accepts optional complexity_score and reasoning fields."""
        from conductor.orchestrator.models import TaskSpec

        # Existing construction still works without new fields
        task = TaskSpec(
            id="t1",
            title="A task",
            description="Description",
            role="executor",
            target_file="src/foo.py",
        )
        assert task.complexity_score is None
        assert task.reasoning is None

    def test_taskspec_with_complexity_fields(self):
        """TaskSpec accepts complexity_score and reasoning when provided."""
        from conductor.orchestrator.models import TaskSpec

        task = TaskSpec(
            id="t1",
            title="A task",
            description="Description",
            role="executor",
            target_file="src/foo.py",
            complexity_score=6,
            reasoning="This touches three subsystems",
        )
        assert task.complexity_score == 6
        assert task.reasoning == "This touches three subsystems"


# ---------------------------------------------------------------------------
# Tests: _analyze_complexity() method (Task 1 — TDD RED)
# ---------------------------------------------------------------------------


class TestAnalyzeComplexity:
    """Tests for _analyze_complexity() method on TaskDecomposer."""

    def _make_plan_with_tasks(self, count: int = 2) -> TaskPlan:
        tasks = [
            TaskSpec(
                id=f"t{i+1}",
                title=f"Task {i+1}",
                description=f"Description for task {i+1}",
                role="executor",
                target_file=f"src/file{i+1}.py",
            )
            for i in range(count)
        ]
        return TaskPlan(feature_name="TestFeature", tasks=tasks, max_agents=4)

    def _make_complexity_result_dict(self, task_ids: list[str]) -> dict:
        return {
            "analyses": [
                {
                    "task_id": tid,
                    "complexity_score": 7,
                    "reasoning": f"Complex task {tid}",
                    "expansion_prompt": f"Break down {tid} into sub-steps",
                    "recommended_subtasks": 3,
                }
                for tid in task_ids
            ]
        }

    @pytest.mark.asyncio
    async def test_analyze_complexity_returns_list(self):
        """_analyze_complexity() returns a list of ComplexityAnalysis objects on success."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        plan = self._make_plan_with_tasks(2)
        result_dict = self._make_complexity_result_dict(["t1", "t2"])

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="sess-cplx-001",
            structured_output=result_dict,
        )

        async def _mock_query(**kwargs):
            yield result_msg

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            result = await decomposer._analyze_complexity(plan)

        assert result is not None
        assert len(result) == 2
        assert result[0].task_id == "t1"
        assert result[1].task_id == "t2"

    @pytest.mark.asyncio
    async def test_analyze_complexity_prompt_contains_task_info(self):
        """_analyze_complexity() prompt contains all task IDs and descriptions."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        plan = self._make_plan_with_tasks(2)
        result_dict = self._make_complexity_result_dict(["t1", "t2"])

        result_msg = ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="sess-cplx-002",
            structured_output=result_dict,
        )

        captured_kwargs: list[dict] = []

        async def _mock_query(**kwargs):
            captured_kwargs.append(kwargs)
            yield result_msg

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            await decomposer._analyze_complexity(plan)

        assert captured_kwargs, "query() was not called"
        prompt = captured_kwargs[0]["prompt"]
        # Must include task IDs and descriptions
        assert "t1" in prompt
        assert "t2" in prompt
        assert "Description for task 1" in prompt
        assert "Description for task 2" in prompt

    @pytest.mark.asyncio
    async def test_analyze_complexity_returns_none_on_failure(self):
        """_analyze_complexity() returns None when SDK call fails (no result)."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        plan = self._make_plan_with_tasks(2)

        async def _mock_query(**kwargs):
            return
            yield  # make it an async generator

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            result = await decomposer._analyze_complexity(plan)

        assert result is None

    @pytest.mark.asyncio
    async def test_analyze_complexity_returns_none_on_sdk_error(self):
        """_analyze_complexity() returns None when SDK raises an exception."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        plan = self._make_plan_with_tasks(2)

        async def _mock_query(**kwargs):
            raise RuntimeError("SDK error")
            yield  # make it an async generator

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            result = await decomposer._analyze_complexity(plan)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: decompose() with complexity pipeline (Task 1 — TDD RED)
# ---------------------------------------------------------------------------


class TestDecomposeWithComplexity:
    """Tests for decompose() integrating the complexity analysis pipeline."""

    def _make_task_plan_dict(self, feature_name: str = "MyFeature", count: int = 2) -> dict:
        return {
            "feature_name": feature_name,
            "tasks": [
                {
                    "id": f"t{i+1}",
                    "title": f"Task {i+1}",
                    "description": f"Description {i+1}",
                    "role": "executor",
                    "target_file": f"src/file{i+1}.py",
                    "material_files": [],
                    "requires": [],
                    "produces": [],
                }
                for i in range(count)
            ],
            "max_agents": 4,
        }

    def _make_complexity_result_dict(self, task_ids: list[str], scores: list[int] | None = None) -> dict:
        if scores is None:
            scores = [7] * len(task_ids)
        return {
            "analyses": [
                {
                    "task_id": tid,
                    "complexity_score": score,
                    "reasoning": f"Reasoning for {tid}",
                    "expansion_prompt": f"Expand {tid}",
                    "recommended_subtasks": 3,
                }
                for tid, score in zip(task_ids, scores)
            ]
        }

    @pytest.mark.asyncio
    async def test_decompose_populates_complexity_scores(self):
        """decompose() populates complexity_score and reasoning on each TaskSpec."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        plan_dict = self._make_task_plan_dict("ScoreTest", count=2)
        complexity_dict = self._make_complexity_result_dict(["t1", "t2"], scores=[3, 8])

        # We need two separate SDK calls. We'll track call count to return different results.
        call_count = 0

        async def _mock_query(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: decompose
                yield ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-score-001",
                    structured_output=plan_dict,
                )
            else:
                # Second call: complexity analysis
                yield ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-score-002",
                    structured_output=complexity_dict,
                )

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            plan = await decomposer.decompose("Build scored feature")

        # complexity_score and reasoning should be populated
        t1 = next(t for t in plan.tasks if t.id == "t1")
        t2 = next(t for t in plan.tasks if t.id == "t2")
        assert t1.complexity_score == 3
        assert t1.reasoning == "Reasoning for t1"
        assert t2.complexity_score == 8
        assert t2.reasoning == "Reasoning for t2"

    @pytest.mark.asyncio
    async def test_decompose_falls_back_when_complexity_fails(self):
        """decompose() returns original plan unchanged when complexity analysis fails."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        plan_dict = self._make_task_plan_dict("FallbackTest", count=2)

        call_count = 0

        async def _mock_query(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: decompose — succeeds
                yield ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="sess-fallback-001",
                    structured_output=plan_dict,
                )
            else:
                # Second call: complexity analysis — yields nothing (fails)
                return
                yield  # make it an async generator

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            plan = await decomposer.decompose("Build fallback feature")

        # Original plan returned unchanged — no complexity scores
        assert plan.feature_name == "FallbackTest"
        assert len(plan.tasks) == 2
        for task in plan.tasks:
            assert task.complexity_score is None
            assert task.reasoning is None

    def test_decomposer_has_complexity_threshold_param(self):
        """TaskDecomposer.__init__ accepts complexity_threshold parameter."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        # Default threshold
        d1 = TaskDecomposer()
        assert d1._complexity_threshold == 5

        # Custom threshold
        d2 = TaskDecomposer(complexity_threshold=7)
        assert d2._complexity_threshold == 7


# ---------------------------------------------------------------------------
# Tests: _expand_task() and _expand_complex_tasks() (Task 2 — TDD RED)
# ---------------------------------------------------------------------------


def _make_result_msg(structured_output: dict, session_id: str = "sess-exp-001"):
    """Helper to create a ResultMessage with given structured output."""
    from claude_agent_sdk import ResultMessage

    return ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=1,
        session_id=session_id,
        structured_output=structured_output,
    )


def _make_task_spec(
    task_id: str,
    target_file: str,
    requires: list[str] | None = None,
    complexity_score: int | None = None,
    role: str = "executor",
) -> TaskSpec:
    return TaskSpec(
        id=task_id,
        title=f"Task {task_id}",
        description=f"Description for {task_id}",
        role=role,
        target_file=target_file,
        requires=requires or [],
        complexity_score=complexity_score,
    )


def _make_complexity_analysis(
    task_id: str,
    score: int = 7,
    recommended_subtasks: int = 3,
) -> "ComplexityAnalysis":
    from conductor.orchestrator.models import ComplexityAnalysis

    return ComplexityAnalysis(
        task_id=task_id,
        complexity_score=score,
        reasoning=f"Reasoning for {task_id}",
        expansion_prompt=f"Expand {task_id} into service, model, and API layers",
        recommended_subtasks=recommended_subtasks,
    )


class TestExpandTask:
    """Tests for _expand_task() method."""

    def _make_expansion_dict(self, parent_id: str, count: int = 3) -> dict:
        """Build an ExpansionResult dict with count subtasks."""
        return {
            "subtasks": [
                {
                    "id": f"{parent_id}.{i + 1}",  # SDK might or might not set this
                    "title": f"Subtask {i + 1} of {parent_id}",
                    "description": f"Detailed step {i + 1} for {parent_id}",
                    "role": "executor",
                    "target_file": f"src/layer{i + 1}.py",
                    "material_files": [],
                    "requires": [],
                    "produces": [],
                }
                for i in range(count)
            ]
        }

    @pytest.mark.asyncio
    async def test_expand_task_returns_subtasks(self):
        """_expand_task() returns list of sub-TaskSpec objects on success."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        task = _make_task_spec("A", "src/main.py", complexity_score=8)
        analysis = _make_complexity_analysis("A", score=8, recommended_subtasks=3)
        expansion_dict = self._make_expansion_dict("A", count=3)

        async def _mock_query(**kwargs):
            yield _make_result_msg(expansion_dict, session_id="exp-001")

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            subtasks = await decomposer._expand_task(task, analysis)

        assert subtasks is not None
        assert len(subtasks) == 3

    @pytest.mark.asyncio
    async def test_expand_task_ids_are_namespaced(self):
        """Sub-task IDs are namespaced as '{parent_id}.1', '{parent_id}.2', etc."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        task = _make_task_spec("myTask", "src/main.py", complexity_score=8)
        analysis = _make_complexity_analysis("myTask", score=8, recommended_subtasks=2)
        expansion_dict = self._make_expansion_dict("myTask", count=2)

        async def _mock_query(**kwargs):
            yield _make_result_msg(expansion_dict, session_id="exp-002")

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            subtasks = await decomposer._expand_task(task, analysis)

        assert subtasks is not None
        assert subtasks[0].id == "myTask.1"
        assert subtasks[1].id == "myTask.2"

    @pytest.mark.asyncio
    async def test_expand_task_subtasks_inherit_parent_role(self):
        """Sub-tasks inherit the parent task's role."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        task = _make_task_spec("R", "src/main.py", complexity_score=8, role="backend developer")
        analysis = _make_complexity_analysis("R", score=8, recommended_subtasks=2)
        expansion_dict = self._make_expansion_dict("R", count=2)

        async def _mock_query(**kwargs):
            yield _make_result_msg(expansion_dict, session_id="exp-003")

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            subtasks = await decomposer._expand_task(task, analysis)

        assert subtasks is not None
        for st in subtasks:
            assert st.role == "backend developer"

    @pytest.mark.asyncio
    async def test_expand_task_requires_chain(self):
        """Sub-tasks form a sequential dependency chain: first is independent, rest depend on previous."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        task = _make_task_spec("X", "src/main.py", complexity_score=9)
        analysis = _make_complexity_analysis("X", score=9, recommended_subtasks=3)
        expansion_dict = self._make_expansion_dict("X", count=3)

        async def _mock_query(**kwargs):
            yield _make_result_msg(expansion_dict, session_id="exp-004")

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            subtasks = await decomposer._expand_task(task, analysis)

        assert subtasks is not None
        assert subtasks[0].requires == []          # first: independent
        assert subtasks[1].requires == ["X.1"]     # second: depends on first
        assert subtasks[2].requires == ["X.2"]     # third: depends on second

    @pytest.mark.asyncio
    async def test_expand_task_returns_none_on_failure(self):
        """_expand_task() returns None when SDK call fails (no result)."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        task = _make_task_spec("Y", "src/main.py", complexity_score=8)
        analysis = _make_complexity_analysis("Y", score=8)

        async def _mock_query(**kwargs):
            return
            yield  # make it an async generator

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            result = await decomposer._expand_task(task, analysis)

        assert result is None

    @pytest.mark.asyncio
    async def test_expand_task_returns_none_on_sdk_exception(self):
        """_expand_task() returns None when SDK raises exception."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        task = _make_task_spec("Z", "src/main.py", complexity_score=8)
        analysis = _make_complexity_analysis("Z", score=8)

        async def _mock_query(**kwargs):
            raise RuntimeError("SDK connection error")
            yield  # make it an async generator

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            result = await decomposer._expand_task(task, analysis)

        assert result is None


class TestExpandComplexTasks:
    """Tests for _expand_complex_tasks() and the full pipeline integration."""

    def _make_expansion_dict(self, parent_id: str, count: int = 3) -> dict:
        return {
            "subtasks": [
                {
                    "id": f"{parent_id}.{i + 1}",
                    "title": f"Subtask {i + 1} of {parent_id}",
                    "description": f"Detailed step {i + 1} for {parent_id}",
                    "role": "executor",
                    "target_file": f"src/layer{i + 1}_{parent_id}.py",
                    "material_files": [],
                    "requires": [],
                    "produces": [],
                }
                for i in range(count)
            ]
        }

    @pytest.mark.asyncio
    async def test_only_above_threshold_expanded(self):
        """Only tasks with complexity_score > threshold are expanded."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        # Task A: score 3 (low), Task B: score 8 (high, above default threshold 5)
        tasks = [
            _make_task_spec("A", "src/a.py", complexity_score=3),
            _make_task_spec("B", "src/b.py", complexity_score=8),
        ]
        plan = TaskPlan(feature_name="TestFeature", tasks=tasks, max_agents=4)
        analyses = [
            _make_complexity_analysis("A", score=3),
            _make_complexity_analysis("B", score=8, recommended_subtasks=2),
        ]

        expansion_dict = self._make_expansion_dict("B", count=2)

        async def _mock_query(**kwargs):
            yield _make_result_msg(expansion_dict, session_id="exp-threshold-001")

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer(complexity_threshold=5)
            result = await decomposer._expand_complex_tasks(plan, analyses)

        task_ids = [t.id for t in result.tasks]
        # A should be unchanged; B should be expanded into B.1, B.2
        assert "A" in task_ids
        assert "B" not in task_ids  # replaced by subtasks
        assert "B.1" in task_ids
        assert "B.2" in task_ids

    @pytest.mark.asyncio
    async def test_dependency_rewiring(self):
        """If task B required task A, and A is expanded to A.1/A.2/A.3, then B now requires A.3."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        # Task A (high complexity), Task B depends on A (low complexity)
        tasks = [
            _make_task_spec("A", "src/a.py", complexity_score=8),
            _make_task_spec("B", "src/b.py", requires=["A"], complexity_score=2),
        ]
        plan = TaskPlan(feature_name="TestFeature", tasks=tasks, max_agents=4)
        analyses = [
            _make_complexity_analysis("A", score=8, recommended_subtasks=3),
            _make_complexity_analysis("B", score=2),
        ]

        expansion_dict = self._make_expansion_dict("A", count=3)

        async def _mock_query(**kwargs):
            yield _make_result_msg(expansion_dict, session_id="exp-rewire-001")

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer(complexity_threshold=5)
            result = await decomposer._expand_complex_tasks(plan, analyses)

        task_map = {t.id: t for t in result.tasks}
        # B should now require A.3 (the last subtask of A)
        assert "B" in task_map
        assert task_map["B"].requires == ["A.3"]

    @pytest.mark.asyncio
    async def test_expansion_failure_keeps_original_task(self):
        """If expansion fails for one task, that task passes through unchanged."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        tasks = [
            _make_task_spec("A", "src/a.py", complexity_score=9),
        ]
        plan = TaskPlan(feature_name="TestFeature", tasks=tasks, max_agents=4)
        analyses = [_make_complexity_analysis("A", score=9)]

        # Expansion call returns nothing (failure)
        async def _mock_query(**kwargs):
            return
            yield  # make it an async generator

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer(complexity_threshold=5)
            result = await decomposer._expand_complex_tasks(plan, analyses)

        # Original task should be kept
        assert len(result.tasks) == 1
        assert result.tasks[0].id == "A"

    @pytest.mark.asyncio
    async def test_feature_name_preserved(self):
        """Expanded plan preserves the feature_name from original plan."""
        from conductor.orchestrator.decomposer import TaskDecomposer

        tasks = [_make_task_spec("A", "src/a.py", complexity_score=8)]
        plan = TaskPlan(feature_name="MySpecialFeature", tasks=tasks, max_agents=4)
        analyses = [_make_complexity_analysis("A", score=8, recommended_subtasks=2)]

        expansion_dict = self._make_expansion_dict("A", count=2)

        async def _mock_query(**kwargs):
            yield _make_result_msg(expansion_dict, session_id="exp-name-001")

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer()
            result = await decomposer._expand_complex_tasks(plan, analyses)

        assert result.feature_name == "MySpecialFeature"

    @pytest.mark.asyncio
    async def test_full_pipeline_integration(self):
        """Full decompose() pipeline with mix of high and low complexity tasks."""
        from claude_agent_sdk import ResultMessage

        from conductor.orchestrator.decomposer import TaskDecomposer

        # Initial decomposition result: 3 tasks
        plan_dict = {
            "feature_name": "IntegrationFeature",
            "tasks": [
                {
                    "id": "t1",
                    "title": "Simple task",
                    "description": "A simple task",
                    "role": "executor",
                    "target_file": "src/simple.py",
                    "material_files": [],
                    "requires": [],
                    "produces": [],
                },
                {
                    "id": "t2",
                    "title": "Complex task",
                    "description": "A very complex task",
                    "role": "executor",
                    "target_file": "src/complex.py",
                    "material_files": [],
                    "requires": ["t1"],
                    "produces": [],
                },
                {
                    "id": "t3",
                    "title": "Dependent task",
                    "description": "Depends on t2",
                    "role": "executor",
                    "target_file": "src/dependent.py",
                    "material_files": [],
                    "requires": ["t2"],
                    "produces": [],
                },
            ],
            "max_agents": 4,
        }

        # Complexity analysis: t1=3 (low), t2=8 (high), t3=2 (low)
        complexity_dict = {
            "analyses": [
                {
                    "task_id": "t1",
                    "complexity_score": 3,
                    "reasoning": "Simple task",
                    "expansion_prompt": "n/a",
                    "recommended_subtasks": 2,
                },
                {
                    "task_id": "t2",
                    "complexity_score": 8,
                    "reasoning": "Very complex",
                    "expansion_prompt": "Break into data, service, API layers",
                    "recommended_subtasks": 3,
                },
                {
                    "task_id": "t3",
                    "complexity_score": 2,
                    "reasoning": "Simple dependent",
                    "expansion_prompt": "n/a",
                    "recommended_subtasks": 2,
                },
            ]
        }

        # Expansion of t2 into 3 subtasks
        expansion_dict = {
            "subtasks": [
                {
                    "id": "t2.1",
                    "title": "Data layer",
                    "description": "Implement data layer",
                    "role": "executor",
                    "target_file": "src/data.py",
                    "material_files": [],
                    "requires": [],
                    "produces": [],
                },
                {
                    "id": "t2.2",
                    "title": "Service layer",
                    "description": "Implement service layer",
                    "role": "executor",
                    "target_file": "src/service.py",
                    "material_files": [],
                    "requires": [],
                    "produces": [],
                },
                {
                    "id": "t2.3",
                    "title": "API layer",
                    "description": "Implement API layer",
                    "role": "executor",
                    "target_file": "src/api.py",
                    "material_files": [],
                    "requires": [],
                    "produces": [],
                },
            ]
        }

        call_count = 0

        async def _mock_query(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Phase 1: decompose
                yield ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="int-001",
                    structured_output=plan_dict,
                )
            elif call_count == 2:
                # Phase 2: complexity analysis
                yield ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="int-002",
                    structured_output=complexity_dict,
                )
            else:
                # Phase 3: expand t2 (only this task is complex)
                yield ResultMessage(
                    subtype="success",
                    duration_ms=100,
                    duration_api_ms=80,
                    is_error=False,
                    num_turns=1,
                    session_id="int-003",
                    structured_output=expansion_dict,
                )

        with patch("conductor.orchestrator.decomposer.query", side_effect=_mock_query):
            decomposer = TaskDecomposer(complexity_threshold=5)
            plan = await decomposer.decompose("Build integration feature")

        # Feature name preserved
        assert plan.feature_name == "IntegrationFeature"

        # t1 unchanged, t2 expanded to t2.1/t2.2/t2.3, t3 unchanged
        task_ids = [t.id for t in plan.tasks]
        assert "t1" in task_ids
        assert "t2" not in task_ids
        assert "t2.1" in task_ids
        assert "t2.2" in task_ids
        assert "t2.3" in task_ids
        assert "t3" in task_ids

        task_map = {t.id: t for t in plan.tasks}

        # t2 subtask chain: t2.1 independent, t2.2 requires t2.1, t2.3 requires t2.2
        assert task_map["t2.1"].requires == []
        assert task_map["t2.2"].requires == ["t2.1"]
        assert task_map["t2.3"].requires == ["t2.2"]

        # Dependency rewiring: t3 originally required t2, now must require t2.3
        assert task_map["t3"].requires == ["t2.3"]

        # t1 and t3 have complexity scores set
        assert task_map["t1"].complexity_score == 3
        assert task_map["t3"].complexity_score == 2

        # 3 SDK calls total (decompose, analyze, expand-t2)
        assert call_count == 3
