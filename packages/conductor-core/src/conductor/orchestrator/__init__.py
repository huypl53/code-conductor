"""Conductor orchestrator agent — public API."""
from conductor.orchestrator.errors import (
    CycleError,
    DecompositionError,
    FileConflictError,
    OrchestratorError,
)
from conductor.orchestrator.identity import AgentIdentity, build_system_prompt
from conductor.orchestrator.models import TaskPlan, TaskSpec
from conductor.orchestrator.ownership import validate_file_ownership
from conductor.orchestrator.scheduler import DependencyScheduler

__all__ = [
    # errors
    "OrchestratorError",
    "DecompositionError",
    "CycleError",
    "FileConflictError",
    # models
    "TaskSpec",
    "TaskPlan",
    # identity
    "AgentIdentity",
    "build_system_prompt",
    # scheduling
    "DependencyScheduler",
    # ownership
    "validate_file_ownership",
]
