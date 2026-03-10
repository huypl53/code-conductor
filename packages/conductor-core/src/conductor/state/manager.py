"""StateManager: file-locked atomic read-modify-write for conductor state."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import filelock
from pydantic import ValidationError

from conductor.state.errors import StateCorrupted, StateLockTimeout
from conductor.state.models import ConductorState, Task, TaskStatus


class StateManager:
    """Atomic read-modify-write access to .conductor/state.json.

    All mutations are serialized through a FileLock so concurrent processes
    can safely update shared state without corruption.

    Usage::

        manager = StateManager(Path(".conductor/state.json"))

        # Read current state (no lock held)
        state = manager.read_state()

        # Atomic mutate
        def assign(state: ConductorState) -> None:
            state.tasks[0].assigned_agent = "agent-001"

        manager.mutate(assign)
    """

    def __init__(self, state_path: Path) -> None:
        """Initialise with the path to the state JSON file.

        Args:
            state_path: Path to the state.json file (may not yet exist).
        """
        self._state_path = state_path
        self._lock_path = state_path.with_suffix(".json.lock")

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    def read_state(self) -> ConductorState:
        """Read and return the current ConductorState (no lock held).

        Returns an empty ConductorState if the file does not exist yet.

        Raises:
            StateCorrupted: If the file exists but cannot be parsed.
        """
        if not self._state_path.exists():
            return ConductorState()
        try:
            return ConductorState.model_validate_json(
                self._state_path.read_text(encoding="utf-8")
            )
        except (ValidationError, ValueError) as exc:
            raise StateCorrupted(
                f"Cannot parse state file {self._state_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public mutation API
    # ------------------------------------------------------------------

    def mutate(
        self,
        fn: Callable[[ConductorState], None],
        timeout: float = 10.0,
    ) -> ConductorState:
        """Acquire lock, read state, apply *fn*, atomically write back.

        Args:
            fn: Callable that receives the current ConductorState and
                modifies it in-place.
            timeout: Seconds to wait for the lock (default 10.0).

        Returns:
            The new ConductorState after mutation.

        Raises:
            StateLockTimeout: If the lock cannot be acquired within *timeout*.
            StateCorrupted: If the state file is invalid before mutation.
        """
        lock = filelock.FileLock(str(self._lock_path), timeout=timeout)
        try:
            with lock:
                state = self.read_state()
                fn(state)
                state.updated_at = datetime.now(UTC)
                self._atomic_write(state.model_dump_json(indent=2))
                return state
        except filelock.Timeout as exc:
            raise StateLockTimeout(
                f"Could not acquire lock on {self._lock_path} "
                f"within {timeout}s"
            ) from exc

    def assign_task(self, task_id: str, agent_id: str) -> None:
        """Assign *task_id* to *agent_id* and mark it IN_PROGRESS.

        Args:
            task_id: ID of the task to assign.
            agent_id: ID of the agent receiving the assignment.
        """

        def _assign(state: ConductorState) -> None:
            for task in state.tasks:
                if task.id == task_id:
                    task.assigned_agent = agent_id
                    task.status = TaskStatus.IN_PROGRESS  # type: ignore[assignment]
                    break

        self.mutate(_assign)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        output: dict | None = None,
    ) -> None:
        """Update a task's status and optionally merge output data.

        Args:
            task_id: ID of the task to update.
            status: New TaskStatus value.
            output: Optional dict to merge into task.outputs.
        """

        def _update(state: ConductorState) -> None:
            for task in state.tasks:
                if task.id == task_id:
                    task.status = status  # type: ignore[assignment]
                    if output is not None:
                        task.outputs.update(output)
                    break

        self.mutate(_update)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _atomic_write(self, data: str) -> None:
        """Write *data* atomically using tempfile + fsync + os.replace.

        The temp file is created in the same directory as state_path to
        guarantee they are on the same filesystem (os.replace requirement).

        Args:
            data: JSON string to write.
        """
        parent = self._state_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(dir=parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self._state_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


# ---------------------------------------------------------------------------
# Module-level helper for multiprocessing spawn compatibility
# ---------------------------------------------------------------------------


def _spawn_write_tasks(state_path_str: str, prefix: str, count: int) -> None:
    """Write `count` tasks to state_path, for use in multiprocessing tests.

    This must be importable from spawned child processes, so it lives here in
    the installed package rather than in the tests directory.

    Args:
        state_path_str: String path to the state.json file.
        prefix: Prefix for generated task IDs (e.g. "alpha", "beta").
        count: Number of tasks to write.
    """
    manager = StateManager(Path(state_path_str))
    for i in range(count):
        task_id = f"{prefix}-task-{i}"

        def _add(state: ConductorState, _id: str = task_id) -> None:
            state.tasks.append(
                Task(
                    id=_id,
                    title=f"Task {_id}",
                    description=f"Description for {_id}",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        manager.mutate(_add)
