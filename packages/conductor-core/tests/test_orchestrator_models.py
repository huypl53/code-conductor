"""Tests for orchestrator error hierarchy, TaskSpec, TaskPlan, and AgentIdentity models."""
from __future__ import annotations

import json

import pytest

from conductor.orchestrator import (
    AgentIdentity,
    CycleError,
    DecompositionError,
    FileConflictError,
    OrchestratorError,
    TaskPlan,
    TaskSpec,
    build_system_prompt,
)


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class TestOrchestratorErrorHierarchy:
    def test_orchestrator_error_is_exception(self) -> None:
        err = OrchestratorError("base")
        assert isinstance(err, Exception)

    def test_decomposition_error_is_orchestrator_error(self) -> None:
        err = DecompositionError("bad decomp")
        assert isinstance(err, OrchestratorError)

    def test_cycle_error_is_orchestrator_error(self) -> None:
        err = CycleError(["t1", "t2", "t1"])
        assert isinstance(err, OrchestratorError)

    def test_file_conflict_error_is_orchestrator_error(self) -> None:
        err = FileConflictError("t1", "t2", {"src/main.py"})
        assert isinstance(err, OrchestratorError)

    def test_decomposition_error_can_be_raised_and_caught(self) -> None:
        with pytest.raises(OrchestratorError):
            raise DecompositionError("failed to decompose")

    def test_cycle_error_stores_cycle_path(self) -> None:
        cycle = ["t1", "t2", "t3", "t1"]
        err = CycleError(cycle)
        assert err.cycle == cycle

    def test_cycle_error_with_single_self_cycle(self) -> None:
        cycle = ["t1", "t1"]
        err = CycleError(cycle)
        assert err.cycle == ["t1", "t1"]

    def test_file_conflict_error_stores_task_ids_and_files(self) -> None:
        files = {"src/api.py", "src/utils.py"}
        err = FileConflictError("task-a", "task-b", files)
        assert err.task_a == "task-a"
        assert err.task_b == "task-b"
        assert err.files == files

    def test_file_conflict_error_can_be_raised_and_caught_as_orchestrator_error(self) -> None:
        with pytest.raises(OrchestratorError):
            raise FileConflictError("t1", "t2", {"src/main.py"})


# ---------------------------------------------------------------------------
# TaskSpec model
# ---------------------------------------------------------------------------


class TestTaskSpec:
    def test_create_with_required_fields(self) -> None:
        spec = TaskSpec(
            id="t1",
            title="Implement auth",
            description="Build JWT auth",
            role="backend-engineer",
            target_file="src/auth.py",
        )
        assert spec.id == "t1"
        assert spec.title == "Implement auth"
        assert spec.description == "Build JWT auth"
        assert spec.role == "backend-engineer"
        assert spec.target_file == "src/auth.py"

    def test_default_material_files_is_empty_list(self) -> None:
        spec = TaskSpec(id="t1", title="T", description="D", role="r", target_file="f.py")
        assert spec.material_files == []

    def test_default_requires_is_empty_list(self) -> None:
        spec = TaskSpec(id="t1", title="T", description="D", role="r", target_file="f.py")
        assert spec.requires == []

    def test_default_produces_is_empty_list(self) -> None:
        spec = TaskSpec(id="t1", title="T", description="D", role="r", target_file="f.py")
        assert spec.produces == []

    def test_material_files_can_be_set(self) -> None:
        spec = TaskSpec(
            id="t1", title="T", description="D", role="r", target_file="f.py",
            material_files=["src/models.py", "src/utils.py"],
        )
        assert spec.material_files == ["src/models.py", "src/utils.py"]

    def test_requires_and_produces_can_be_set(self) -> None:
        spec = TaskSpec(
            id="t2", title="T", description="D", role="r", target_file="f.py",
            requires=["t1"], produces=["auth-token"],
        )
        assert spec.requires == ["t1"]
        assert spec.produces == ["auth-token"]

    def test_json_round_trip(self) -> None:
        spec = TaskSpec(
            id="t1",
            title="Implement auth",
            description="Build JWT auth",
            role="backend-engineer",
            target_file="src/auth.py",
            material_files=["src/models.py"],
            requires=[],
            produces=["jwt-token"],
        )
        json_str = spec.model_dump_json()
        restored = TaskSpec.model_validate_json(json_str)
        assert restored.id == "t1"
        assert restored.title == "Implement auth"
        assert restored.target_file == "src/auth.py"
        assert restored.material_files == ["src/models.py"]
        assert restored.produces == ["jwt-token"]

    def test_missing_required_field_raises_validation_error(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TaskSpec(title="T", description="D", role="r", target_file="f.py")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TaskPlan model
# ---------------------------------------------------------------------------


class TestTaskPlan:
    def test_create_with_feature_name_and_tasks(self) -> None:
        spec = TaskSpec(id="t1", title="T", description="D", role="r", target_file="f.py")
        plan = TaskPlan(feature_name="Auth Feature", tasks=[spec])
        assert plan.feature_name == "Auth Feature"
        assert len(plan.tasks) == 1

    def test_default_max_agents_is_4(self) -> None:
        plan = TaskPlan(feature_name="F", tasks=[])
        assert plan.max_agents == 4

    def test_max_agents_can_be_set(self) -> None:
        plan = TaskPlan(feature_name="F", tasks=[], max_agents=6)
        assert plan.max_agents == 6

    def test_max_agents_minimum_is_1(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TaskPlan(feature_name="F", tasks=[], max_agents=0)

    def test_max_agents_maximum_is_10(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TaskPlan(feature_name="F", tasks=[], max_agents=11)

    def test_model_json_schema_is_valid(self) -> None:
        schema = TaskPlan.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "feature_name" in schema["properties"]
        assert "tasks" in schema["properties"]
        assert "max_agents" in schema["properties"]

    def test_model_json_schema_serializable(self) -> None:
        schema = TaskPlan.model_json_schema()
        # Should be JSON-serializable (for SDK output_format)
        json_str = json.dumps(schema)
        assert len(json_str) > 0

    def test_json_round_trip(self) -> None:
        spec = TaskSpec(id="t1", title="T", description="D", role="r", target_file="f.py")
        plan = TaskPlan(feature_name="Auth Feature", tasks=[spec], max_agents=3)
        json_str = plan.model_dump_json()
        restored = TaskPlan.model_validate_json(json_str)
        assert restored.feature_name == "Auth Feature"
        assert restored.max_agents == 3
        assert len(restored.tasks) == 1
        assert restored.tasks[0].id == "t1"


# ---------------------------------------------------------------------------
# AgentIdentity model
# ---------------------------------------------------------------------------


class TestAgentIdentity:
    def test_create_with_required_fields(self) -> None:
        identity = AgentIdentity(
            name="Alice",
            role="backend-engineer",
            target_file="src/auth.py",
            task_id="t1",
            task_description="Implement JWT auth",
        )
        assert identity.name == "Alice"
        assert identity.role == "backend-engineer"
        assert identity.target_file == "src/auth.py"
        assert identity.task_id == "t1"
        assert identity.task_description == "Implement JWT auth"

    def test_default_material_files_is_empty_list(self) -> None:
        identity = AgentIdentity(
            name="Alice", role="r", target_file="f.py", task_id="t1", task_description="D"
        )
        assert identity.material_files == []

    def test_material_files_can_be_set(self) -> None:
        identity = AgentIdentity(
            name="Alice", role="r", target_file="f.py", task_id="t1", task_description="D",
            material_files=["src/models.py", "src/utils.py"],
        )
        assert identity.material_files == ["src/models.py", "src/utils.py"]


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    def _make_identity(self, **kwargs) -> AgentIdentity:
        defaults = {
            "name": "Alice",
            "role": "backend-engineer",
            "target_file": "src/auth.py",
            "task_id": "t1",
            "task_description": "Implement JWT authentication",
        }
        defaults.update(kwargs)
        return AgentIdentity(**defaults)

    def test_prompt_contains_name(self) -> None:
        prompt = build_system_prompt(self._make_identity(name="Alice"))
        assert "Alice" in prompt

    def test_prompt_contains_role(self) -> None:
        prompt = build_system_prompt(self._make_identity(role="backend-engineer"))
        assert "backend-engineer" in prompt

    def test_prompt_does_not_contain_task_description(self) -> None:
        """Task description is sent as first user message, not in system prompt (LEAN-01)."""
        prompt = build_system_prompt(self._make_identity(task_description="Implement JWT authentication"))
        assert "Implement JWT authentication" not in prompt

    def test_prompt_contains_task_id(self) -> None:
        """Task ID should appear in the lean prompt."""
        prompt = build_system_prompt(self._make_identity(task_id="t1"))
        assert "t1" in prompt

    def test_prompt_contains_target_file(self) -> None:
        prompt = build_system_prompt(self._make_identity(target_file="src/auth.py"))
        assert "src/auth.py" in prompt

    def test_prompt_contains_material_files(self) -> None:
        identity = self._make_identity(material_files=["src/models.py", "src/utils.py"])
        prompt = build_system_prompt(identity)
        assert "src/models.py" in prompt
        assert "src/utils.py" in prompt

    def test_prompt_contains_do_not_modify_constraint(self) -> None:
        prompt = build_system_prompt(self._make_identity())
        assert "Do not modify other files" in prompt

    def test_prompt_is_string(self) -> None:
        prompt = build_system_prompt(self._make_identity())
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_with_empty_material_files(self) -> None:
        identity = self._make_identity(material_files=[])
        prompt = build_system_prompt(identity)
        # Should still contain constraint and target file
        assert "Do not modify other files" in prompt
        assert "src/auth.py" in prompt


# ---------------------------------------------------------------------------
# Extended Task state model
# ---------------------------------------------------------------------------


class TestExtendedTaskModel:
    def test_task_has_requires_field_with_default_empty_list(self) -> None:
        from conductor.state import Task
        task = Task(id="t1", title="T", description="D")
        assert task.requires == []

    def test_task_has_produces_field_with_default_empty_list(self) -> None:
        from conductor.state import Task
        task = Task(id="t1", title="T", description="D")
        assert task.produces == []

    def test_task_has_target_file_field_with_default_empty_string(self) -> None:
        from conductor.state import Task
        task = Task(id="t1", title="T", description="D")
        assert task.target_file == ""

    def test_task_has_material_files_field_with_default_empty_list(self) -> None:
        from conductor.state import Task
        task = Task(id="t1", title="T", description="D")
        assert task.material_files == []

    def test_task_new_fields_can_be_set(self) -> None:
        from conductor.state import Task
        task = Task(
            id="t1", title="T", description="D",
            requires=["t0"], produces=["result"], target_file="src/api.py",
            material_files=["src/models.py"],
        )
        assert task.requires == ["t0"]
        assert task.produces == ["result"]
        assert task.target_file == "src/api.py"
        assert task.material_files == ["src/models.py"]

    def test_task_backward_compat_existing_json_without_new_fields(self) -> None:
        """Existing serialized Task JSON (without new fields) still deserializes correctly."""
        from conductor.state import Task
        old_json = json.dumps({
            "id": "t1",
            "title": "Old Task",
            "description": "Old description",
            "status": "pending",
            "assigned_agent": None,
            "outputs": {},
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        })
        task = Task.model_validate_json(old_json)
        assert task.id == "t1"
        assert task.requires == []
        assert task.produces == []
        assert task.target_file == ""
        assert task.material_files == []

    def test_task_round_trip_with_new_fields(self) -> None:
        from conductor.state import Task
        task = Task(
            id="t1", title="T", description="D",
            requires=["t0"], produces=["output"], target_file="src/api.py",
            material_files=["src/models.py"],
        )
        json_str = task.model_dump_json()
        restored = Task.model_validate_json(json_str)
        assert restored.requires == ["t0"]
        assert restored.produces == ["output"]
        assert restored.target_file == "src/api.py"
        assert restored.material_files == ["src/models.py"]


# ---------------------------------------------------------------------------
# OrchestratorConfig model
# ---------------------------------------------------------------------------


class TestOrchestratorConfig:
    def test_default_values(self) -> None:
        from conductor.orchestrator.models import OrchestratorConfig
        cfg = OrchestratorConfig()
        assert cfg.max_review_iterations == 2
        assert cfg.max_decomposition_retries == 3
        assert cfg.max_agents == 10

    def test_override_max_review_iterations(self) -> None:
        from conductor.orchestrator.models import OrchestratorConfig
        cfg = OrchestratorConfig(max_review_iterations=5)
        assert cfg.max_review_iterations == 5
        assert cfg.max_decomposition_retries == 3  # unchanged
        assert cfg.max_agents == 10  # unchanged

    def test_override_max_decomposition_retries(self) -> None:
        from conductor.orchestrator.models import OrchestratorConfig
        cfg = OrchestratorConfig(max_decomposition_retries=1)
        assert cfg.max_decomposition_retries == 1
        assert cfg.max_review_iterations == 2  # unchanged

    def test_json_round_trip(self) -> None:
        from conductor.orchestrator.models import OrchestratorConfig
        cfg = OrchestratorConfig(max_review_iterations=5, max_decomposition_retries=1, max_agents=4)
        json_str = cfg.model_dump_json()
        restored = OrchestratorConfig.model_validate_json(json_str)
        assert restored.max_review_iterations == 5
        assert restored.max_decomposition_retries == 1
        assert restored.max_agents == 4


# ---------------------------------------------------------------------------
# AgentRole enum and ModelProfile model
# ---------------------------------------------------------------------------


class TestAgentRole:
    def test_role_values_exist(self) -> None:
        from conductor.orchestrator.models import AgentRole
        assert AgentRole.decomposer
        assert AgentRole.reviewer
        assert AgentRole.executor
        assert AgentRole.verifier

    def test_role_is_string(self) -> None:
        from conductor.orchestrator.models import AgentRole
        assert isinstance(AgentRole.executor, str)


class TestModelProfile:
    def test_quality_preset_name(self) -> None:
        from conductor.orchestrator.models import ModelProfile
        profile = ModelProfile.quality()
        assert profile.name == "quality"

    def test_quality_preset_all_sonnet(self) -> None:
        from conductor.orchestrator.models import AgentRole, ModelProfile
        profile = ModelProfile.quality()
        for role in AgentRole:
            assert profile.get_model(role) == "claude-sonnet-4-20250514"

    def test_balanced_preset_name(self) -> None:
        from conductor.orchestrator.models import ModelProfile
        profile = ModelProfile.balanced()
        assert profile.name == "balanced"

    def test_balanced_preset_decomposer_reviewer_sonnet(self) -> None:
        from conductor.orchestrator.models import AgentRole, ModelProfile
        profile = ModelProfile.balanced()
        assert profile.get_model(AgentRole.decomposer) == "claude-sonnet-4-20250514"
        assert profile.get_model(AgentRole.reviewer) == "claude-sonnet-4-20250514"

    def test_balanced_preset_executor_verifier_haiku(self) -> None:
        from conductor.orchestrator.models import AgentRole, ModelProfile
        profile = ModelProfile.balanced()
        assert profile.get_model(AgentRole.executor) == "claude-haiku-35-20241022"
        assert profile.get_model(AgentRole.verifier) == "claude-haiku-35-20241022"

    def test_budget_preset_name(self) -> None:
        from conductor.orchestrator.models import ModelProfile
        profile = ModelProfile.budget()
        assert profile.name == "budget"

    def test_budget_preset_all_haiku(self) -> None:
        from conductor.orchestrator.models import AgentRole, ModelProfile
        profile = ModelProfile.budget()
        for role in AgentRole:
            assert profile.get_model(role) == "claude-haiku-35-20241022"

    def test_get_model_returns_mapped_model(self) -> None:
        from conductor.orchestrator.models import AgentRole, ModelProfile
        profile = ModelProfile(
            name="custom",
            role_models={AgentRole.executor: "my-model"},
        )
        assert profile.get_model(AgentRole.executor) == "my-model"

    def test_get_model_fallback_to_executor_model(self) -> None:
        from conductor.orchestrator.models import AgentRole, ModelProfile
        # Only executor is mapped; querying decomposer should fall back to executor's model
        profile = ModelProfile(
            name="partial",
            role_models={AgentRole.executor: "fallback-model"},
        )
        assert profile.get_model(AgentRole.decomposer) == "fallback-model"

    def test_get_model_ultimate_fallback(self) -> None:
        from conductor.orchestrator.models import AgentRole, ModelProfile
        # Empty role_models — ultimate fallback to hardcoded sonnet
        profile = ModelProfile(name="empty", role_models={})
        assert profile.get_model(AgentRole.executor) == "claude-sonnet-4-20250514"
