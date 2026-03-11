"""Tests for AgentReport model, parse_agent_report function, and system prompt updates."""
from __future__ import annotations

import pytest

from conductor.orchestrator.models import AgentReport, AgentReportStatus
from conductor.orchestrator.monitor import parse_agent_report
from conductor.orchestrator.identity import (
    AgentIdentity,
    build_system_prompt,
    STATUS_BLOCK_INSTRUCTIONS,
    DEVIATION_RULES,
)


# ---------------------------------------------------------------------------
# AgentReportStatus enum tests
# ---------------------------------------------------------------------------


class TestAgentReportStatus:
    """AgentReportStatus enum has all required values."""

    def test_has_done(self):
        assert AgentReportStatus.DONE == "DONE"

    def test_has_done_with_concerns(self):
        assert AgentReportStatus.DONE_WITH_CONCERNS == "DONE_WITH_CONCERNS"

    def test_has_blocked(self):
        assert AgentReportStatus.BLOCKED == "BLOCKED"

    def test_has_needs_context(self):
        assert AgentReportStatus.NEEDS_CONTEXT == "NEEDS_CONTEXT"


# ---------------------------------------------------------------------------
# AgentReport model tests
# ---------------------------------------------------------------------------


class TestAgentReport:
    """AgentReport model parses correctly from dicts."""

    def test_parse_done_with_all_fields(self):
        report = AgentReport.model_validate(
            {
                "status": "DONE",
                "summary": "Implemented the feature",
                "files_changed": ["src/foo.py"],
                "concerns": [],
            }
        )
        assert report.status == AgentReportStatus.DONE
        assert report.summary == "Implemented the feature"
        assert report.files_changed == ["src/foo.py"]
        assert report.concerns == []

    def test_parse_blocked_with_concerns(self):
        report = AgentReport.model_validate(
            {
                "status": "BLOCKED",
                "summary": "Cannot proceed",
                "files_changed": [],
                "concerns": ["Need to add a new database table"],
            }
        )
        assert report.status == AgentReportStatus.BLOCKED
        assert "new database table" in report.concerns[0]

    def test_parse_needs_context(self):
        report = AgentReport.model_validate(
            {
                "status": "NEEDS_CONTEXT",
                "summary": "Need more info",
            }
        )
        assert report.status == AgentReportStatus.NEEDS_CONTEXT
        assert report.files_changed == []  # default
        assert report.concerns == []  # default

    def test_parse_done_with_concerns(self):
        report = AgentReport.model_validate(
            {
                "status": "DONE_WITH_CONCERNS",
                "summary": "Done but with issues",
                "concerns": ["Some edge case not handled"],
            }
        )
        assert report.status == AgentReportStatus.DONE_WITH_CONCERNS
        assert len(report.concerns) == 1


# ---------------------------------------------------------------------------
# parse_agent_report tests
# ---------------------------------------------------------------------------


class TestParseAgentReport:
    """parse_agent_report extracts JSON status blocks from text."""

    def test_extracts_from_fenced_json_block(self):
        text = (
            "I completed the implementation.\n\n"
            "```json\n"
            '{"status": "DONE", "summary": "All done", "files_changed": ["foo.py"]}\n'
            "```\n"
        )
        report = parse_agent_report(text)
        assert report is not None
        assert report.status == AgentReportStatus.DONE
        assert report.summary == "All done"
        assert report.files_changed == ["foo.py"]

    def test_returns_none_when_no_json_block(self):
        text = "I completed the implementation. Everything looks good."
        report = parse_agent_report(text)
        assert report is None

    def test_returns_none_on_malformed_json(self):
        text = (
            "Some text\n"
            "```json\n"
            "{invalid json content here\n"
            "```\n"
        )
        report = parse_agent_report(text)
        assert report is None

    def test_returns_none_on_wrong_schema(self):
        """JSON that is valid but fails AgentReport validation returns None."""
        text = (
            "```json\n"
            '{"foo": "bar", "baz": 42}\n'
            "```\n"
        )
        report = parse_agent_report(text)
        assert report is None

    def test_extracts_from_text_with_surrounding_prose(self):
        """JSON status block embedded in the middle of agent output."""
        text = (
            "Here is my analysis of the codebase.\n"
            "I made several changes to improve the code quality.\n\n"
            "```json\n"
            '{"status": "DONE_WITH_CONCERNS", "summary": "Done", '
            '"files_changed": ["a.py", "b.py"], "concerns": ["Edge case X"]}\n'
            "```\n\n"
            "Let me know if you need any clarification."
        )
        report = parse_agent_report(text)
        assert report is not None
        assert report.status == AgentReportStatus.DONE_WITH_CONCERNS
        assert len(report.files_changed) == 2
        assert "Edge case X" in report.concerns[0]

    def test_extracts_blocked_status(self):
        text = (
            "I cannot proceed without architectural changes.\n\n"
            "```json\n"
            '{"status": "BLOCKED", "summary": "Need new table", '
            '"concerns": ["Requires new DB table for sessions"]}\n'
            "```\n"
        )
        report = parse_agent_report(text)
        assert report is not None
        assert report.status == AgentReportStatus.BLOCKED
        assert len(report.concerns) == 1

    def test_extracts_needs_context_status(self):
        text = (
            "```json\n"
            '{"status": "NEEDS_CONTEXT", "summary": "Need material files"}\n'
            "```\n"
        )
        report = parse_agent_report(text)
        assert report is not None
        assert report.status == AgentReportStatus.NEEDS_CONTEXT

    def test_empty_string_returns_none(self):
        assert parse_agent_report("") is None

    def test_does_not_crash_on_valid_json_without_status_key(self):
        """A valid JSON object without status key should return None, not crash."""
        text = (
            "```json\n"
            '{"result": "ok", "data": [1, 2, 3]}\n'
            "```\n"
        )
        report = parse_agent_report(text)
        assert report is None


# ---------------------------------------------------------------------------
# System prompt instruction tests
# ---------------------------------------------------------------------------


class TestSystemPromptInstructions:
    """build_system_prompt includes status and deviation instructions."""

    def _make_identity(self) -> AgentIdentity:
        return AgentIdentity(
            name="agent-task-001-abc123",
            role="executor",
            target_file="src/foo.py",
            material_files=["src/bar.py"],
            task_id="task-001",
            task_description="Implement feature X",
        )

    def test_status_instructions_in_prompt(self):
        identity = self._make_identity()
        prompt = build_system_prompt(identity)
        # Should mention the status output format
        assert "DONE" in prompt
        assert "BLOCKED" in prompt
        assert "NEEDS_CONTEXT" in prompt

    def test_status_block_format_in_prompt(self):
        identity = self._make_identity()
        prompt = build_system_prompt(identity)
        # Should show JSON format example
        assert "status" in prompt
        assert "summary" in prompt

    def test_deviation_rules_in_prompt(self):
        identity = self._make_identity()
        prompt = build_system_prompt(identity)
        # Should mention auto-fix and escalation/blocked
        assert "BLOCKED" in prompt
        # Should mention fix silently / auto-fix type language
        lower_prompt = prompt.lower()
        assert "fix" in lower_prompt or "auto" in lower_prompt

    def test_status_block_instructions_constant_exists(self):
        assert isinstance(STATUS_BLOCK_INSTRUCTIONS, str)
        assert len(STATUS_BLOCK_INSTRUCTIONS) > 50

    def test_deviation_rules_constant_exists(self):
        assert isinstance(DEVIATION_RULES, str)
        assert len(DEVIATION_RULES) > 50

    def test_prompt_includes_status_block_instructions(self):
        identity = self._make_identity()
        prompt = build_system_prompt(identity)
        # The prompt should contain the STATUS_BLOCK_INSTRUCTIONS content
        assert STATUS_BLOCK_INSTRUCTIONS[:50] in prompt

    def test_prompt_includes_deviation_rules(self):
        identity = self._make_identity()
        prompt = build_system_prompt(identity)
        # The prompt should contain the DEVIATION_RULES content
        assert DEVIATION_RULES[:50] in prompt
