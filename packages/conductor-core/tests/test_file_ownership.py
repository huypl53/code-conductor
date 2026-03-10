"""CORD-05: validate_file_ownership tests — conflict detection, clean ownership."""
from __future__ import annotations

import pytest

from conductor.orchestrator.errors import FileConflictError
from conductor.orchestrator.ownership import validate_file_ownership


class TestCord05NoConflict:
    """Tasks with disjoint target_files pass ownership validation."""

    def test_empty_list_returns_empty_dict(self) -> None:
        result = validate_file_ownership([])
        assert result == {}

    def test_single_task_returns_single_entry(self) -> None:
        result = validate_file_ownership([("task-a", "src/foo.py")])
        assert result == {"task-a": {"src/foo.py"}}

    def test_two_tasks_disjoint_files_pass(self) -> None:
        tasks = [("task-a", "src/alpha.py"), ("task-b", "src/beta.py")]
        result = validate_file_ownership(tasks)
        assert result == {
            "task-a": {"src/alpha.py"},
            "task-b": {"src/beta.py"},
        }

    def test_three_tasks_all_unique_pass(self) -> None:
        tasks = [
            ("t1", "src/models.py"),
            ("t2", "src/views.py"),
            ("t3", "src/controllers.py"),
        ]
        result = validate_file_ownership(tasks)
        assert set(result.keys()) == {"t1", "t2", "t3"}
        assert result["t1"] == {"src/models.py"}
        assert result["t2"] == {"src/views.py"}
        assert result["t3"] == {"src/controllers.py"}


class TestCord05Conflict:
    """Two tasks with same target_file raises FileConflictError."""

    def test_two_tasks_same_file_raises(self) -> None:
        tasks = [("task-a", "src/shared.py"), ("task-b", "src/shared.py")]
        with pytest.raises(FileConflictError) as exc_info:
            validate_file_ownership(tasks)
        err = exc_info.value
        assert err.task_a in {"task-a", "task-b"}
        assert err.task_b in {"task-a", "task-b"}
        assert err.task_a != err.task_b
        assert "src/shared.py" in err.files

    def test_conflict_error_has_required_attributes(self) -> None:
        tasks = [("a", "conflict.py"), ("b", "conflict.py")]
        with pytest.raises(FileConflictError) as exc_info:
            validate_file_ownership(tasks)
        err = exc_info.value
        assert hasattr(err, "task_a")
        assert hasattr(err, "task_b")
        assert hasattr(err, "files")
        assert isinstance(err.files, set)

    def test_three_tasks_two_conflict_error_reports_conflicting_pair(self) -> None:
        """Three tasks where two conflict: error reports the conflicting pair."""
        tasks = [
            ("clean-task", "src/unique.py"),
            ("conflicting-a", "src/shared.py"),
            ("conflicting-b", "src/shared.py"),
        ]
        with pytest.raises(FileConflictError) as exc_info:
            validate_file_ownership(tasks)
        err = exc_info.value
        # Must report conflicting pair, not the clean task
        assert "clean-task" not in (err.task_a, err.task_b)
        assert {err.task_a, err.task_b} == {"conflicting-a", "conflicting-b"}
        assert "src/shared.py" in err.files

    def test_conflict_error_message_contains_file(self) -> None:
        tasks = [("x", "src/overlap.py"), ("y", "src/overlap.py")]
        with pytest.raises(FileConflictError) as exc_info:
            validate_file_ownership(tasks)
        assert "src/overlap.py" in str(exc_info.value)
