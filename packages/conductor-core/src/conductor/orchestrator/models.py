"""Pydantic v2 models for orchestrator task decomposition output."""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(StrEnum):
    """Roles that agents can play in the orchestration pipeline."""

    decomposer = "decomposer"
    reviewer = "reviewer"
    executor = "executor"
    verifier = "verifier"


class OrchestratorConfig(BaseModel):
    """Configuration for orchestrator behaviour — used to avoid hardcoded defaults."""

    max_review_iterations: int = 2
    max_decomposition_retries: int = 3
    max_agents: int = 10


class ModelProfile(BaseModel):
    """Maps agent roles to model names with preset profiles."""

    name: str
    role_models: dict[AgentRole, str] = Field(default_factory=dict)

    def get_model(self, role: AgentRole) -> str:
        """Return the model string for *role*, falling back to executor or a hardcoded default."""
        return self.role_models.get(
            role,
            self.role_models.get(AgentRole.executor, "claude-sonnet-4-20250514"),
        )

    @classmethod
    def quality(cls) -> ModelProfile:
        """All roles use claude-sonnet-4-20250514."""
        return cls(
            name="quality",
            role_models={role: "claude-sonnet-4-20250514" for role in AgentRole},
        )

    @classmethod
    def balanced(cls) -> ModelProfile:
        """Decomposer/reviewer use Sonnet; executor/verifier use Haiku."""
        return cls(
            name="balanced",
            role_models={
                AgentRole.decomposer: "claude-sonnet-4-20250514",
                AgentRole.reviewer: "claude-sonnet-4-20250514",
                AgentRole.executor: "claude-haiku-35-20241022",
                AgentRole.verifier: "claude-haiku-35-20241022",
            },
        )

    @classmethod
    def budget(cls) -> ModelProfile:
        """All roles use claude-haiku-35-20241022."""
        return cls(
            name="budget",
            role_models={role: "claude-haiku-35-20241022" for role in AgentRole},
        )


class AgentReportStatus(StrEnum):
    """Status values an agent can report at the end of its work."""

    DONE = "DONE"
    DONE_WITH_CONCERNS = "DONE_WITH_CONCERNS"
    BLOCKED = "BLOCKED"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"


class AgentReport(BaseModel):
    """Structured status report emitted by an agent at end of task execution."""

    status: AgentReportStatus
    summary: str
    files_changed: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)


class TaskSpec(BaseModel):
    """Specification for a single agent task produced by decomposition."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    title: str
    description: str
    role: str
    target_file: str
    material_files: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    """Full decomposition plan containing all task specs for a feature.

    Designed so that ``TaskPlan.model_json_schema()`` can be passed directly
    to the Claude SDK as ``output_format`` for structured output.
    """

    model_config = ConfigDict(use_enum_values=True)

    feature_name: str
    tasks: list[TaskSpec]
    max_agents: int = Field(default=4, ge=1, le=10)
