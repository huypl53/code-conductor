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
