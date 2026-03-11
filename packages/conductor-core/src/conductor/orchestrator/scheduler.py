"""CORD-04: DependencyScheduler wrapping graphlib.TopologicalSorter."""
from __future__ import annotations

from graphlib import CycleError as GraphCycleError
from graphlib import TopologicalSorter

from conductor.orchestrator.errors import CycleError


class DependencyScheduler:
    """Dependency-aware task scheduler backed by graphlib.TopologicalSorter.

    Args:
        graph: Mapping of task_id -> set of dependency task IDs.
               Example: {"b": {"a"}, "a": set()} means "a" must finish before "b".

    Raises:
        CycleError: If the dependency graph contains a cycle.
    """

    def __init__(self, graph: dict[str, set[str]]) -> None:
        self._graph = {k: set(v) for k, v in graph.items()}
        try:
            self._sorter: TopologicalSorter[str] = TopologicalSorter(graph)
            self._sorter.prepare()
        except GraphCycleError as exc:
            # exc.args[1] is the tuple of nodes forming the cycle
            cycle = list(exc.args[1]) if len(exc.args) > 1 else []
            raise CycleError(cycle) from exc

    def get_ready(self) -> tuple[str, ...]:
        """Return task IDs whose dependencies are all satisfied and can run now."""
        return self._sorter.get_ready()

    def done(self, task_id: str) -> None:
        """Mark a task as complete, unblocking any dependents."""
        self._sorter.done(task_id)

    def is_active(self) -> bool:
        """Return True while tasks remain to be scheduled or completed."""
        return self._sorter.is_active()

    def compute_waves(self) -> list[list[str]]:
        """Return tasks grouped into concurrent execution waves.

        A wave is a set of tasks whose dependencies are all satisfied by
        the tasks in previous waves.  Calling this method does NOT consume
        the scheduler — ``get_ready()`` and ``done()`` still work normally.

        Returns:
            A list of waves, each wave being a list of task IDs that can
            run concurrently.  Returns ``[]`` for an empty graph.
        """
        if not self._graph:
            return []

        # Build a fresh sorter from the stored graph — never touch self._sorter
        scratch: TopologicalSorter[str] = TopologicalSorter(self._graph)
        scratch.prepare()

        waves: list[list[str]] = []
        while scratch.is_active():
            ready = list(scratch.get_ready())
            if not ready:
                break
            waves.append(ready)
            for task_id in ready:
                scratch.done(task_id)

        return waves
