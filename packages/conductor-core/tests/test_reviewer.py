"""ORCH-04 / RVEW-01 tests: two-stage review and backward-compatible review_output()."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from conductor.orchestrator.errors import ReviewError
from conductor.orchestrator.reviewer import (
    QualityVerdict,
    ReviewVerdict,
    SpecVerdict,
    review_code_quality,
    review_output,
    review_spec_compliance,
)


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


def _spec_pass() -> dict:
    return {"spec_compliant": True, "issues": [], "revision_instructions": ""}


def _spec_fail(issues=None, instructions="Fix spec") -> dict:
    return {
        "spec_compliant": False,
        "issues": issues or ["Missing required function"],
        "revision_instructions": instructions,
    }


def _quality_pass() -> dict:
    return {"quality_passed": True, "quality_issues": [], "revision_instructions": ""}


def _quality_fail(issues=None, instructions="Fix quality") -> dict:
    return {
        "quality_passed": False,
        "quality_issues": issues or ["Missing error handling"],
        "revision_instructions": instructions,
    }


# ---------------------------------------------------------------------------
# New model tests: SpecVerdict and QualityVerdict
# ---------------------------------------------------------------------------


class TestSpecVerdict:
    """SpecVerdict model has correct fields."""

    def test_spec_compliant_field(self) -> None:
        v = SpecVerdict(spec_compliant=True, issues=[], revision_instructions="")
        assert v.spec_compliant is True

    def test_issues_field(self) -> None:
        v = SpecVerdict(spec_compliant=False, issues=["Missing method"], revision_instructions="Add method")
        assert v.issues == ["Missing method"]

    def test_revision_instructions_default_empty(self) -> None:
        v = SpecVerdict(spec_compliant=True, issues=[])
        assert v.revision_instructions == ""

    def test_model_validate_from_dict(self) -> None:
        v = SpecVerdict.model_validate(_spec_pass())
        assert v.spec_compliant is True


class TestQualityVerdict:
    """QualityVerdict model has correct fields."""

    def test_quality_passed_field(self) -> None:
        v = QualityVerdict(quality_passed=True, quality_issues=[], revision_instructions="")
        assert v.quality_passed is True

    def test_quality_issues_field(self) -> None:
        v = QualityVerdict(quality_passed=False, quality_issues=["Bad style"], revision_instructions="Improve")
        assert v.quality_issues == ["Bad style"]

    def test_revision_instructions_default_empty(self) -> None:
        v = QualityVerdict(quality_passed=True, quality_issues=[])
        assert v.revision_instructions == ""

    def test_model_validate_from_dict(self) -> None:
        v = QualityVerdict.model_validate(_quality_pass())
        assert v.quality_passed is True


# ---------------------------------------------------------------------------
# review_spec_compliance() tests
# ---------------------------------------------------------------------------


class TestReviewSpecCompliance:
    """review_spec_compliance() returns SpecVerdict for spec checking."""

    @pytest.mark.asyncio
    async def test_returns_spec_verdict(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def authenticate(): return True\n")
        result_msg = _make_result_message(_spec_pass())

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(result_msg),
        ):
            verdict = await review_spec_compliance(
                task_description="Add auth",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        assert isinstance(verdict, SpecVerdict)
        assert verdict.spec_compliant is True

    @pytest.mark.asyncio
    async def test_missing_file_returns_non_compliant(self, tmp_path: Path) -> None:
        verdict = await review_spec_compliance(
            task_description="Add auth",
            target_file="src/missing.py",
            agent_summary="Done",
            repo_path=str(tmp_path),
        )
        assert isinstance(verdict, SpecVerdict)
        assert verdict.spec_compliant is False

    @pytest.mark.asyncio
    async def test_raises_review_error_on_no_output(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def f(): return 1\n")
        result_msg = _make_result_message(None)

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(result_msg),
        ):
            with pytest.raises(ReviewError):
                await review_spec_compliance(
                    task_description="Add auth",
                    target_file="src/auth.py",
                    agent_summary="Done",
                    repo_path=str(tmp_path),
                )

    @pytest.mark.asyncio
    async def test_spec_fail_verdict(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def authenticate(): return True\n")
        result_msg = _make_result_message(_spec_fail())

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(result_msg),
        ):
            verdict = await review_spec_compliance(
                task_description="Add auth with MFA",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        assert verdict.spec_compliant is False
        assert len(verdict.issues) > 0


# ---------------------------------------------------------------------------
# review_code_quality() tests
# ---------------------------------------------------------------------------


class TestReviewCodeQuality:
    """review_code_quality() returns QualityVerdict for quality checking."""

    @pytest.mark.asyncio
    async def test_returns_quality_verdict(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def authenticate(): return True\n")
        result_msg = _make_result_message(_quality_pass())

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(result_msg),
        ):
            verdict = await review_code_quality(
                task_description="Add auth",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        assert isinstance(verdict, QualityVerdict)
        assert verdict.quality_passed is True

    @pytest.mark.asyncio
    async def test_missing_file_returns_not_passed(self, tmp_path: Path) -> None:
        verdict = await review_code_quality(
            task_description="Add auth",
            target_file="src/missing.py",
            agent_summary="Done",
            repo_path=str(tmp_path),
        )
        assert isinstance(verdict, QualityVerdict)
        assert verdict.quality_passed is False

    @pytest.mark.asyncio
    async def test_quality_fail_verdict(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def authenticate(): return True\n")
        result_msg = _make_result_message(_quality_fail())

        with patch(
            "conductor.orchestrator.reviewer.sdk_query",
            return_value=_async_gen(result_msg),
        ):
            verdict = await review_code_quality(
                task_description="Add auth",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        assert verdict.quality_passed is False
        assert len(verdict.quality_issues) > 0


# ---------------------------------------------------------------------------
# Two-stage short-circuit behavior
# ---------------------------------------------------------------------------


class TestTwoStageShortCircuit:
    """review_output() short-circuits: spec fail skips quality review."""

    @pytest.mark.asyncio
    async def test_spec_fail_skips_quality(self, tmp_path: Path) -> None:
        """When spec compliance fails, quality review must not be called."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def f(): return 1\n")

        call_count = 0

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            nonlocal call_count
            call_count += 1
            # Spec compliance call — returns spec failure
            result_msg = _make_result_message(_spec_fail())
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            verdict = await review_output(
                task_description="Add auth",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        # Only one SDK call made (spec), quality skipped
        assert call_count == 1
        assert verdict.approved is False

    @pytest.mark.asyncio
    async def test_spec_pass_triggers_quality(self, tmp_path: Path) -> None:
        """When spec compliance passes, quality review must be called."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def f(): return 1\n")

        call_count = 0

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: spec compliance passes
                result_msg = _make_result_message(_spec_pass())
            else:
                # Second call: quality passes
                result_msg = _make_result_message(_quality_pass())
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            verdict = await review_output(
                task_description="Add auth",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        # Two SDK calls: spec then quality
        assert call_count == 2
        assert verdict.approved is True

    @pytest.mark.asyncio
    async def test_both_pass_approved_true(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def f(): return 1\n")

        call_count = 0

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                result_msg = _make_result_message(_spec_pass())
            else:
                result_msg = _make_result_message(_quality_pass())
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            verdict = await review_output(
                task_description="Add auth",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        assert verdict.approved is True
        assert verdict.quality_issues == []

    @pytest.mark.asyncio
    async def test_spec_pass_quality_fail_approved_false(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/auth.py").write_text("def f(): return 1\n")

        call_count = 0

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                result_msg = _make_result_message(_spec_pass())
            else:
                result_msg = _make_result_message(_quality_fail(["Missing error handling"]))
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            verdict = await review_output(
                task_description="Add auth",
                target_file="src/auth.py",
                agent_summary="Done",
                repo_path=str(tmp_path),
            )

        assert verdict.approved is False
        assert "Missing error handling" in verdict.quality_issues


# ---------------------------------------------------------------------------
# Backward-compat: review_output() still works
# ---------------------------------------------------------------------------


class TestOrch04FileMissing:
    """review_output() returns ReviewVerdict(approved=False) when target file missing."""

    @pytest.mark.asyncio
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
    """review_output() truncates files larger than 8000 chars via spec compliance stage."""

    @pytest.mark.asyncio
    async def test_large_file_is_truncated(self, tmp_path: Path) -> None:
        target_file = "src/large_module.py"
        (tmp_path / "src").mkdir()
        # Create a file > 8000 chars
        large_content = "x" * 4100 + "\n# middle section\n" + "y" * 4100
        (tmp_path / target_file).write_text(large_content)

        captured_prompts: list[str] = []

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            captured_prompts.append(prompt)
            # First call is spec compliance, second is quality
            if len(captured_prompts) == 1:
                result_msg = _make_result_message(_spec_pass())
            else:
                result_msg = _make_result_message(_quality_pass())
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            await review_output(
                task_description="Implement large module",
                target_file=target_file,
                agent_summary="Created large module.",
                repo_path=str(tmp_path),
            )

        # At least one prompt should contain truncation notice
        assert len(captured_prompts) >= 1
        prompt = captured_prompts[0]
        # Truncation notice must appear in the spec compliance prompt
        assert "truncated" in prompt.lower()
        # The full original content should NOT be present verbatim
        assert "x" * 4100 not in prompt
        # But first 4000 chars should be present
        assert "x" * 4000 in prompt

    @pytest.mark.asyncio
    async def test_small_file_not_truncated(self, tmp_path: Path) -> None:
        target_file = "src/small.py"
        (tmp_path / "src").mkdir()
        small_content = "def main(): pass\n"
        (tmp_path / target_file).write_text(small_content)

        captured_prompts: list[str] = []

        async def mock_query(prompt: str, options=None):  # noqa: ANN001
            captured_prompts.append(prompt)
            if len(captured_prompts) == 1:
                result_msg = _make_result_message(_spec_pass())
            else:
                result_msg = _make_result_message(_quality_pass())
            yield result_msg

        with patch("conductor.orchestrator.reviewer.sdk_query", side_effect=mock_query):
            await review_output(
                task_description="Implement small module",
                target_file=target_file,
                agent_summary="Done.",
                repo_path=str(tmp_path),
            )

        assert small_content in captured_prompts[0]
        assert "truncated" not in captured_prompts[0].lower()
