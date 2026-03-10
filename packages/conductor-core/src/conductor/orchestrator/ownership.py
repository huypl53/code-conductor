"""CORD-05: File ownership validation — prevents concurrent file edit conflicts."""
from __future__ import annotations

from conductor.orchestrator.errors import FileConflictError


def validate_file_ownership(
    tasks: list[tuple[str, str]],
) -> dict[str, set[str]]:
    """Build a file ownership map and detect any conflicts.

    Args:
        tasks: List of (task_id, target_file) tuples. Each task claims one file.

    Returns:
        Mapping of task_id -> set of owned file paths.

    Raises:
        FileConflictError: If any two tasks claim the same target_file.
    """
    ownership: dict[str, set[str]] = {}
    for task_id, target_file in tasks:
        ownership[task_id] = {target_file}

    task_ids = list(ownership.keys())
    for i, a_id in enumerate(task_ids):
        for b_id in task_ids[i + 1 :]:
            overlap = ownership[a_id] & ownership[b_id]
            if overlap:
                raise FileConflictError(
                    task_a=a_id,
                    task_b=b_id,
                    files=overlap,
                )

    return ownership
