"""Pydantic v2 data models for conductor shared state schema."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"


class AgentStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    DONE = "done"


class Task(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Orchestrator-injected dependency/ownership fields (backward-compatible defaults)
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    target_file: str = ""
    material_files: list[str] = Field(default_factory=list)
    # Phase 5: review tracking fields (all-default for backward compat)
    review_status: ReviewStatus = ReviewStatus.PENDING
    revision_count: int = 0


class AgentRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    name: str
    role: str
    current_task_id: str | None = None
    status: AgentStatus = AgentStatus.IDLE
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Phase 7: session tracking fields (all-default for backward compat)
    session_id: str | None = None  # SDK session ID for resume
    memory_file: str | None = None  # path to .memory/<agent-id>.md
    started_at: datetime | None = None  # for session ordering on restart


class Dependency(BaseModel):
    task_id: str  # task that depends on another
    depends_on: str  # task ID it depends on


class ConductorState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    version: str = "1"
    tasks: list[Task] = Field(default_factory=list)
    agents: list[AgentRecord] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
