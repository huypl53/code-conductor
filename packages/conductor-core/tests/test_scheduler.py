"""CORD-04: DependencyScheduler tests — topological ordering, wave readiness, cycle detection."""
from __future__ import annotations

import pytest

from conductor.orchestrator.errors import CycleError
from conductor.orchestrator.scheduler import DependencyScheduler


class TestCord04Ready:
    """Tasks without dependencies are scheduled first (wave 1)."""

    def test_no_deps_tasks_are_immediately_ready(self) -> None:
        graph = {"a": set(), "b": set()}
        sched = DependencyScheduler(graph)
        ready = set(sched.get_ready())
        assert ready == {"a", "b"}

    def test_single_task_no_deps_is_immediately_ready(self) -> None:
        sched = DependencyScheduler({"only": set()})
        assert set(sched.get_ready()) == {"only"}

    def test_task_with_dep_not_in_first_wave(self) -> None:
        graph = {"a": set(), "b": {"a"}}
        sched = DependencyScheduler(graph)
        ready = set(sched.get_ready())
        assert ready == {"a"}
        assert "b" not in ready


class TestCord04Sequencing:
    """Dependent tasks only become ready after done() is called for prerequisites."""

    def test_dependent_becomes_ready_after_prerequisite_done(self) -> None:
        graph = {"a": set(), "b": {"a"}}
        sched = DependencyScheduler(graph)
        # First wave: only "a"
        assert set(sched.get_ready()) == {"a"}
        sched.done("a")
        # After marking "a" done, "b" becomes ready
        assert set(sched.get_ready()) == {"b"}

    def test_chain_a_b_c_sequential(self) -> None:
        graph = {"a": set(), "b": {"a"}, "c": {"b"}}
        sched = DependencyScheduler(graph)
        assert set(sched.get_ready()) == {"a"}
        sched.done("a")
        assert set(sched.get_ready()) == {"b"}
        sched.done("b")
        assert set(sched.get_ready()) == {"c"}
        sched.done("c")
        assert not sched.is_active()

    def test_diamond_dependency(self) -> None:
        """Diamond: A and B have no deps, C depends on both A and B, D depends on C."""
        graph = {
            "a": set(),
            "b": set(),
            "c": {"a", "b"},
            "d": {"c"},
        }
        sched = DependencyScheduler(graph)
        # A and B ready first
        first_ready = set(sched.get_ready())
        assert first_ready == {"a", "b"}
        sched.done("a")
        # C still blocked — B not done yet
        assert "c" not in set(sched.get_ready())
        sched.done("b")
        # Now C is ready
        assert set(sched.get_ready()) == {"c"}
        sched.done("c")
        # D is ready
        assert set(sched.get_ready()) == {"d"}
        sched.done("d")
        assert not sched.is_active()


class TestCord04IsActive:
    """is_active() reflects remaining work correctly."""

    def test_empty_graph_is_not_active(self) -> None:
        sched = DependencyScheduler({})
        assert not sched.is_active()

    def test_active_while_tasks_remain(self) -> None:
        sched = DependencyScheduler({"a": set()})
        assert sched.is_active()

    def test_not_active_after_all_done(self) -> None:
        sched = DependencyScheduler({"a": set()})
        sched.get_ready()  # must call get_ready before done
        sched.done("a")
        assert not sched.is_active()


class TestCord04Cycle:
    """Circular dependency raises CycleError with cycle list."""

    def test_direct_cycle_raises_cycle_error(self) -> None:
        graph = {"a": {"b"}, "b": {"a"}}
        with pytest.raises(CycleError) as exc_info:
            DependencyScheduler(graph)
        assert exc_info.value.cycle  # cycle list is non-empty
        assert isinstance(exc_info.value.cycle, list)

    def test_indirect_cycle_raises_cycle_error(self) -> None:
        graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        with pytest.raises(CycleError):
            DependencyScheduler(graph)

    def test_self_cycle_raises_cycle_error(self) -> None:
        graph = {"a": {"a"}}
        with pytest.raises(CycleError):
            DependencyScheduler(graph)

    def test_cycle_error_has_cycle_attribute(self) -> None:
        graph = {"x": {"y"}, "y": {"x"}}
        with pytest.raises(CycleError) as exc_info:
            DependencyScheduler(graph)
        err = exc_info.value
        assert hasattr(err, "cycle")
        assert len(err.cycle) >= 2


class TestComputeWaves:
    """Tests for DependencyScheduler.compute_waves()."""

    def test_empty_graph_returns_empty_list(self) -> None:
        sched = DependencyScheduler({})
        assert sched.compute_waves() == []

    def test_two_concurrent_tasks_single_wave(self) -> None:
        sched = DependencyScheduler({"a": set(), "b": set()})
        waves = sched.compute_waves()
        assert len(waves) == 1
        assert set(waves[0]) == {"a", "b"}

    def test_sequential_tasks_two_waves(self) -> None:
        sched = DependencyScheduler({"a": set(), "b": {"a"}})
        waves = sched.compute_waves()
        assert len(waves) == 2
        assert set(waves[0]) == {"a"}
        assert set(waves[1]) == {"b"}

    def test_diamond_three_waves(self) -> None:
        """a and b concurrent, then c (depends on both), then d."""
        sched = DependencyScheduler({
            "a": set(),
            "b": set(),
            "c": {"a", "b"},
            "d": {"c"},
        })
        waves = sched.compute_waves()
        assert len(waves) == 3
        assert set(waves[0]) == {"a", "b"}
        assert set(waves[1]) == {"c"}
        assert set(waves[2]) == {"d"}

    def test_compute_waves_does_not_consume_scheduler(self) -> None:
        """compute_waves() should not affect get_ready()/done() functionality."""
        sched = DependencyScheduler({"a": set(), "b": {"a"}})
        # Call compute_waves first
        waves = sched.compute_waves()
        assert len(waves) == 2
        # Scheduler still functional: get_ready returns "a"
        assert set(sched.get_ready()) == {"a"}
        sched.done("a")
        assert set(sched.get_ready()) == {"b"}
        sched.done("b")
        assert not sched.is_active()

    def test_single_task_single_wave(self) -> None:
        sched = DependencyScheduler({"only": set()})
        waves = sched.compute_waves()
        assert len(waves) == 1
        assert set(waves[0]) == {"only"}
