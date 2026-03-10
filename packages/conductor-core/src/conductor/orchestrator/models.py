"""Pydantic v2 models for orchestrator task decomposition output."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
