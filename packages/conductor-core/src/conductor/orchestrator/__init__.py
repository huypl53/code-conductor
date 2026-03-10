"""Conductor orchestrator agent — public API."""
from conductor.orchestrator.decomposer import TaskDecomposer
from conductor.orchestrator.errors import (
    CycleError,
    DecompositionError,
    EscalationError,
    FileConflictError,
    OrchestratorError,
    ReviewError,
)
from conductor.orchestrator.escalation import DecisionLog, EscalationRouter, HumanQuery
from conductor.orchestrator.identity import AgentIdentity, build_system_prompt
from conductor.orchestrator.models import TaskPlan, TaskSpec
from conductor.orchestrator.monitor import StreamMonitor
from conductor.orchestrator.orchestrator import Orchestrator
from conductor.orchestrator.ownership import validate_file_ownership
from conductor.orchestrator.reviewer import ReviewVerdict, review_output
from conductor.orchestrator.scheduler import DependencyScheduler

__all__ = [
    # errors
    "OrchestratorError",
    "DecompositionError",
    "CycleError",
    "FileConflictError",
    "ReviewError",
    "EscalationError",
    # models
    "TaskSpec",
    "TaskPlan",
    # identity
    "AgentIdentity",
    "build_system_prompt",
    # decomposer
    "TaskDecomposer",
    # orchestrator
    "Orchestrator",
    # scheduling
    "DependencyScheduler",
    # ownership
    "validate_file_ownership",
    # monitor
    "StreamMonitor",
    # reviewer
    "ReviewVerdict",
    "review_output",
    # escalation
    "EscalationRouter",
    "HumanQuery",
    "DecisionLog",
]
