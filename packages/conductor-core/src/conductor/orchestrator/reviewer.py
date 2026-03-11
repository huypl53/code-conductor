"""ORCH-04 / RVEW-01: Two-stage review with backward-compatible wrapper.

Stage 1: review_spec_compliance() — checks if output matches the task description.
Stage 2: review_code_quality() — checks code quality (only runs when spec passes).
Wrapper: review_output() — delegates to both stages, returns ReviewVerdict.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from claude_agent_sdk import query as sdk_query
from pydantic import BaseModel, Field

from conductor.orchestrator.errors import ReviewError

# ---------------------------------------------------------------------------
# Verdict models
# ---------------------------------------------------------------------------


class ReviewVerdict(BaseModel):
    """Structured review result from orchestrator quality check (backward-compat)."""

    approved: bool
    quality_issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""


class SpecVerdict(BaseModel):
    """Result from spec compliance review (Stage 1)."""

    spec_compliant: bool
    issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""


class QualityVerdict(BaseModel):
    """Result from code quality review (Stage 2)."""

    quality_passed: bool
    quality_issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SPEC_COMPLIANCE_PROMPT = """\
You are a senior code reviewer checking spec compliance only.

Sub-agent task: {task_description}
Target file: {target_file}

File content:
<file_content>
{file_content}
</file_content>

Agent's completion summary:
<agent_summary>
{agent_summary}
</agent_summary>

Check ONLY:
1. Does the implementation address the task description?
2. Are the required behaviors described in the task present?
3. Are any described requirements missing from the implementation?

Do NOT evaluate code quality, style, or best practices in this review.

If compliant, set spec_compliant=true and leave revision_instructions empty.
If not, set spec_compliant=false, list issues, and provide clear revision_instructions.
"""

CODE_QUALITY_PROMPT = """\
You are a senior code reviewer checking code quality only.

Sub-agent task: {task_description}
Target file: {target_file}

File content:
<file_content>
{file_content}
</file_content>

Agent's completion summary:
<agent_summary>
{agent_summary}
</agent_summary>

Check ONLY:
1. Are there obvious defects (syntax errors, missing logic, wrong file structure)?
2. Is the code well-structured and maintainable?
3. Are there security or performance concerns?

Do NOT re-check spec compliance — assume the spec requirements are already met.

If quality passes, set quality_passed=true and leave revision_instructions empty.
If not, set quality_passed=false, list quality_issues, and provide revision_instructions.
"""

_MAX_TURNS = 2


# ---------------------------------------------------------------------------
# Shared file-reading helper
# ---------------------------------------------------------------------------


async def _read_file_content(repo_path: str, target_file: str) -> str | None:
    """Read and truncate target file. Returns None if file not found."""
    target_path = Path(repo_path) / target_file
    try:
        file_content = await asyncio.to_thread(
            target_path.read_text, encoding="utf-8"
        )
    except FileNotFoundError:
        return None

    # Content truncation — cap at ~8000 chars to avoid context overflow
    if len(file_content) > 8000:
        n_truncated = len(file_content) - 8000
        file_content = (
            file_content[:4000]
            + f"\n[... {n_truncated} characters truncated ...]\n"
            + file_content[-4000:]
        )
    return file_content


async def _run_sdk_query(prompt: str, schema: dict) -> dict:
    """Run sdk_query with a JSON schema and return structured output dict.

    Raises ReviewError if no structured output is returned.
    """
    options = ClaudeAgentOptions(
        output_format={
            "type": "json_schema",
            "schema": schema,
        },
        max_turns=_MAX_TURNS,
    )

    result: ResultMessage | None = None
    async for message in sdk_query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage) and message.structured_output:
            result = message

    if result is None or result.structured_output is None:
        raise ReviewError("Review query returned no structured output")

    return result.structured_output


# ---------------------------------------------------------------------------
# Stage 1: Spec compliance review
# ---------------------------------------------------------------------------


async def review_spec_compliance(
    task_description: str,
    target_file: str,
    agent_summary: str,
    repo_path: str,
) -> SpecVerdict:
    """Check if agent output meets the task spec requirements.

    Returns SpecVerdict(spec_compliant=False) early if file not found.
    Raises ReviewError if SDK returns no structured output.
    """
    file_content = await _read_file_content(repo_path, target_file)
    if file_content is None:
        return SpecVerdict(
            spec_compliant=False,
            issues=["Target file was not created"],
            revision_instructions=f"Create the file at {target_file}",
        )

    prompt = SPEC_COMPLIANCE_PROMPT.format(
        task_description=task_description,
        target_file=target_file,
        file_content=file_content,
        agent_summary=agent_summary or "(no summary provided)",
    )
    data = await _run_sdk_query(prompt, SpecVerdict.model_json_schema())
    return SpecVerdict.model_validate(data)


# ---------------------------------------------------------------------------
# Stage 2: Code quality review
# ---------------------------------------------------------------------------


async def review_code_quality(
    task_description: str,
    target_file: str,
    agent_summary: str,
    repo_path: str,
) -> QualityVerdict:
    """Check code quality of agent output.

    Returns QualityVerdict(quality_passed=False) early if file not found.
    Raises ReviewError if SDK returns no structured output.
    """
    file_content = await _read_file_content(repo_path, target_file)
    if file_content is None:
        return QualityVerdict(
            quality_passed=False,
            quality_issues=["Target file was not created"],
            revision_instructions=f"Create the file at {target_file}",
        )

    prompt = CODE_QUALITY_PROMPT.format(
        task_description=task_description,
        target_file=target_file,
        file_content=file_content,
        agent_summary=agent_summary or "(no summary provided)",
    )
    data = await _run_sdk_query(prompt, QualityVerdict.model_json_schema())
    return QualityVerdict.model_validate(data)


# ---------------------------------------------------------------------------
# Backward-compatible wrapper
# ---------------------------------------------------------------------------


async def review_output(
    task_description: str,
    target_file: str,
    agent_summary: str,
    repo_path: str,
) -> ReviewVerdict:
    """One-shot structured review of a sub-agent's completed work.

    Internally delegates to two-stage review:
    1. review_spec_compliance() — if spec fails, returns immediately (quality skipped)
    2. review_code_quality() — only runs when spec passes

    Args:
        task_description: The original task description given to the sub-agent.
        target_file: Relative path to the file the agent was supposed to produce.
        agent_summary: The agent's own completion summary (ResultMessage.result).
        repo_path: Absolute path to the repository root.

    Returns:
        ReviewVerdict with approved=True/False and optional revision instructions.

    Raises:
        ReviewError: If a review query returns no structured output.
    """
    # File-not-found short circuit (no SDK call needed)
    target_path = Path(repo_path) / target_file
    if not await asyncio.to_thread(target_path.exists):
        return ReviewVerdict(
            approved=False,
            quality_issues=["Target file was not created"],
            revision_instructions=f"Create the file at {target_file}",
        )

    # Stage 1: Spec compliance
    spec = await review_spec_compliance(
        task_description=task_description,
        target_file=target_file,
        agent_summary=agent_summary,
        repo_path=repo_path,
    )
    if not spec.spec_compliant:
        return ReviewVerdict(
            approved=False,
            quality_issues=spec.issues,
            revision_instructions=spec.revision_instructions,
        )

    # Stage 2: Code quality (only reached if spec passes)
    quality = await review_code_quality(
        task_description=task_description,
        target_file=target_file,
        agent_summary=agent_summary,
        repo_path=repo_path,
    )
    return ReviewVerdict(
        approved=quality.quality_passed,
        quality_issues=quality.quality_issues,
        revision_instructions=quality.revision_instructions,
    )
