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
from conductor.orchestrator.models import AgentRole, ModelProfile, OrchestratorConfig, TaskPlan, TaskSpec
from conductor.orchestrator.monitor import StreamMonitor
from conductor.orchestrator.orchestrator import Orchestrator
from conductor.orchestrator.ownership import validate_file_ownership
from conductor.orchestrator.reviewer import QualityVerdict, ReviewVerdict, SpecVerdict, review_code_quality, review_output, review_spec_compliance
from conductor.orchestrator.verifier import DEFAULT_STUB_PATTERNS, TaskVerifier, VerificationResult
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
    "OrchestratorConfig",
    "ModelProfile",
    "AgentRole",
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
    "SpecVerdict",
    "QualityVerdict",
    "review_spec_compliance",
    "review_code_quality",
    # verifier
    "TaskVerifier",
    "VerificationResult",
    "DEFAULT_STUB_PATTERNS",
    # escalation
    "EscalationRouter",
    "HumanQuery",
    "DecisionLog",
]
