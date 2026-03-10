"""ORCH-04 tests for ReviewVerdict model and review_output() function."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.orchestrator.errors import ReviewError
from conductor.orchestrator.reviewer import ReviewVerdict, review_output


def _make_result_message(structured_output: dict | None) -> MagicMock:
    """Create a mock ResultMessage with controlled structured_output."""
    from claude_agent_sdk import ResultMessage

    msg = MagicMock()
    msg.__class__ = ResultMessage
    msg.structured_output = structured_output
    msg.result = "Task completed."
    return msg


async def _async_gen(*items):
    """Async generator helper for mocking sdk_query."""
    for item in items:
        yield item


class TestOrch04Approved:
    """review_output() returns ReviewVerdict(approved=True) on passing work."""

    async def test_approved_verdict_returned(self, tmp_path: Path) -> None:
        target_file = "src/auth.py"
        (tmp_path / "src").mkdir()
        (tmp_path / target_file).write_text("def authenticate(): pass\n")

        structured = {
            "approved": True,
            "quality_issues": [],
            "revision_instructions": "",
        }
        result_msg = _make_result_message(structured)

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(result_msg),
        ):
            verdict = await review_output(
                task_description="Implement authentication module",
                target_file=target_file,
                agent_summary="Created auth.py with authenticate() function.",
                repo_path=str(tmp_path),
            )

        assert isinstance(verdict, ReviewVerdict)
        assert verdict.approved is True
        assert verdict.quality_issues == []


class TestOrch04FileMissing:
    """review_output() returns ReviewVerdict(approved=False) when target file missing."""

    async def test_missing_file_returns_not_approved(self, tmp_path: Path) -> None:
        verdict = await review_output(
            task_description="Implement authentication module",
            target_file="src/auth.py",  # not created
            agent_summary="Work completed.",
            repo_path=str(tmp_path),
        )

        assert isinstance(verdict, ReviewVerdict)
        assert verdict.approved is False
        assert "Target file was not created" in verdict.quality_issues
        assert "src/auth.py" in verdict.revision_instructions


class TestOrch04ReviewError:
    """review_output() raises ReviewError when query() returns no structured output."""

    async def test_no_structured_output_raises_review_error(
        self, tmp_path: Path
    ) -> None:
        target_file = "src/auth.py"
        (tmp_path / "src").mkdir()
        (tmp_path / target_file).write_text("def authenticate(): pass\n")

        # ResultMessage with structured_output=None
        result_msg = _make_result_message(None)

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(result_msg),
        ):
            with pytest.raises(ReviewError, match="no structured output"):
                await review_output(
                    task_description="Implement authentication module",
                    target_file=target_file,
                    agent_summary="Work completed.",
                    repo_path=str(tmp_path),
                )

    async def test_empty_response_raises_review_error(self, tmp_path: Path) -> None:
        """review_output() raises ReviewError when query() yields nothing."""
        target_file = "src/auth.py"
        (tmp_path / "src").mkdir()
        (tmp_path / target_file).write_text("def authenticate(): pass\n")

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(),  # no messages at all
        ):
            with pytest.raises(ReviewError):
                await review_output(
                    task_description="Implement authentication module",
                    target_file=target_file,
                    agent_summary="Work completed.",
                    repo_path=str(tmp_path),
                )


class TestReviewVerdictSchema:
    """ReviewVerdict.model_json_schema() produces valid JSON schema."""

    def test_schema_has_required_fields(self) -> None:
        schema = ReviewVerdict.model_json_schema()
        assert "approved" in schema["properties"]
        assert "quality_issues" in schema["properties"]
        assert "revision_instructions" in schema["properties"]

    def test_approved_is_boolean(self) -> None:
        schema = ReviewVerdict.model_json_schema()
        assert schema["properties"]["approved"]["type"] == "boolean"

    def test_quality_issues_is_array(self) -> None:
        schema = ReviewVerdict.model_json_schema()
        assert schema["properties"]["quality_issues"]["type"] == "array"

    def test_model_validates_from_dict(self) -> None:
        verdict = ReviewVerdict.model_validate(
            {
                "approved": True,
                "quality_issues": [],
                "revision_instructions": "",
            }
        )
        assert verdict.approved is True

    def test_default_values(self) -> None:
        verdict = ReviewVerdict(approved=False)
        assert verdict.quality_issues == []
        assert verdict.revision_instructions == ""


class TestOrch04ContentTruncation:
    """review_output() truncates files larger than 8000 chars."""

    async def test_large_file_is_truncated(self, tmp_path: Path) -> None:
        target_file = "src/large_module.py"
        (tmp_path / "src").mkdir()
        # Create a file > 8000 chars
        large_content = "x" * 4100 + "\n# middle section\n" + "y" * 4100
        (tmp_path / target_file).write_text(large_content)

        captured_prompt: list[str] = []

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            captured_prompt.append(prompt)
            structured = {
                "approved": True,
                "quality_issues": [],
                "revision_instructions": "",
            }
            result_msg = _make_result_message(structured)
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            await review_output(
                task_description="Implement large module",
                target_file=target_file,
                agent_summary="Created large module.",
                repo_path=str(tmp_path),
            )

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        # Truncation notice must appear in the prompt
        assert "truncated" in prompt.lower()
        # The full original content should NOT be present verbatim
        assert "x" * 4100 not in prompt
        # But first 4000 chars should be present
        assert "x" * 4000 in prompt

    async def test_small_file_not_truncated(self, tmp_path: Path) -> None:
        target_file = "src/small.py"
        (tmp_path / "src").mkdir()
        small_content = "def main(): pass\n"
        (tmp_path / target_file).write_text(small_content)

        captured_prompt: list[str] = []

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            captured_prompt.append(prompt)
            result_msg = _make_result_message(
                {"approved": True, "quality_issues": [], "revision_instructions": ""}
            )
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            await review_output(
                task_description="Implement small module",
                target_file=target_file,
                agent_summary="Done.",
                repo_path=str(tmp_path),
            )

        assert small_content in captured_prompt[0]
        assert "truncated" not in captured_prompt[0].lower()
