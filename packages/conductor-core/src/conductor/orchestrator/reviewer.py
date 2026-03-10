"""ORCH-04: ReviewVerdict model and review_output() function.

Uses a lightweight one-shot query() to review sub-agent output quality.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage
from claude_agent_sdk import query as sdk_query
from pydantic import BaseModel, Field

from conductor.orchestrator.errors import ReviewError

# ---------------------------------------------------------------------------
# Review verdict model
# ---------------------------------------------------------------------------


class ReviewVerdict(BaseModel):
    """Structured review result from orchestrator quality check."""

    approved: bool
    quality_issues: list[str] = Field(default_factory=list)
    revision_instructions: str = ""


# ---------------------------------------------------------------------------
# Review prompt template
# ---------------------------------------------------------------------------

REVIEW_PROMPT_TEMPLATE = """\
You are a senior code reviewer and project orchestrator.

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

Review the file and determine:
1. Does the implementation address the task description?
2. Are there obvious defects (syntax errors, missing logic, wrong file structure)?
3. Is the output coherent and complete?

If approved, set approved=true and leave revision_instructions empty.
If not, set approved=false and provide clear revision_instructions the agent can act on.
"""

_MAX_TURNS = 2


# ---------------------------------------------------------------------------
# Review function
# ---------------------------------------------------------------------------


async def review_output(
    task_description: str,
    target_file: str,
    agent_summary: str,
    repo_path: str,
) -> ReviewVerdict:
    """One-shot structured review of a sub-agent's completed work.

    Args:
        task_description: The original task description given to the sub-agent.
        target_file: Relative path to the file the agent was supposed to produce.
        agent_summary: The agent's own completion summary (ResultMessage.result).
        repo_path: Absolute path to the repository root.

    Returns:
        ReviewVerdict with approved=True/False and optional revision instructions.

    Raises:
        ReviewError: If the review query returns no structured output.
    """
    target_path = Path(repo_path) / target_file

    # File existence check — return early without calling the SDK
    try:
        file_content = await asyncio.to_thread(
            target_path.read_text, encoding="utf-8"
        )
    except FileNotFoundError:
        return ReviewVerdict(
            approved=False,
            quality_issues=["Target file was not created"],
            revision_instructions=f"Create the file at {target_file}",
        )

    # Content truncation — cap at ~8000 chars to avoid context overflow
    if len(file_content) > 8000:
        n_truncated = len(file_content) - 8000
        file_content = (
            file_content[:4000]
            + f"\n[... {n_truncated} characters truncated ...]\n"
            + file_content[-4000:]
        )

    prompt = REVIEW_PROMPT_TEMPLATE.format(
        task_description=task_description,
        target_file=target_file,
        file_content=file_content,
        agent_summary=agent_summary or "(no summary provided)",
    )
    options = ClaudeAgentOptions(
        output_format={
            "type": "json_schema",
            "schema": ReviewVerdict.model_json_schema(),
        },
        max_turns=_MAX_TURNS,
    )

    async for message in sdk_query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            if message.structured_output:
                return ReviewVerdict.model_validate(message.structured_output)

    raise ReviewError("Review query returned no structured output")
