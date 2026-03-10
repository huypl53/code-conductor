"""Orchestrator error hierarchy."""
from __future__ import annotations


class OrchestratorError(Exception):
    """Base class for all orchestrator errors."""


class DecompositionError(OrchestratorError):
    """Raised when task decomposition fails (invalid LLM output, schema mismatch)."""


class CycleError(OrchestratorError):
    """Raised when a dependency cycle is detected among tasks.

    Attributes:
        cycle: Ordered list of task IDs forming the cycle, e.g. ["t1", "t2", "t1"].
    """

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        super().__init__(f"Dependency cycle detected: {' -> '.join(cycle)}")


class FileConflictError(OrchestratorError):
    """Raised when two tasks are assigned overlapping target/material files.

    Attributes:
        task_a: First conflicting task ID.
        task_b: Second conflicting task ID.
        files: Set of file paths that conflict.
    """

    def __init__(self, task_a: str, task_b: str, files: set[str]) -> None:
        self.task_a = task_a
        self.task_b = task_b
        self.files = files
        super().__init__(
            f"File conflict between '{task_a}' and '{task_b}': {sorted(files)}"
        )


class ReviewError(OrchestratorError):
    """Raised when a review query fails to return structured output."""


class EscalationError(OrchestratorError):
    """Raised when the EscalationRouter encounters an unrecoverable routing failure."""
