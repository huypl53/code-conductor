"""AgentIdentity model and system prompt builder for orchestrator-spawned agents."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Status block instructions — appended to all agent system prompts
# ---------------------------------------------------------------------------

STATUS_BLOCK_INSTRUCTIONS = """\
## Required Status Report

At the end of your work, output a JSON status block in this exact format:

```json
{
  "status": "DONE|DONE_WITH_CONCERNS|BLOCKED|NEEDS_CONTEXT",
  "summary": "One sentence describing what you did or why you are blocked",
  "files_changed": ["list", "of", "files", "you", "modified"],
  "concerns": ["optional list of concerns or reasons for BLOCKED/DONE_WITH_CONCERNS"]
}
```

Status values:
- DONE: Task completed successfully with no concerns.
- DONE_WITH_CONCERNS: Task completed but there are issues to flag (list them in concerns).
- BLOCKED: You cannot proceed without an architectural decision or human input. Describe the blocker in concerns.
- NEEDS_CONTEXT: You need more information from material files or the orchestrator before you can proceed.
"""

# ---------------------------------------------------------------------------
# Deviation rules — instruct agents how to classify and handle deviations
# ---------------------------------------------------------------------------

DEVIATION_RULES = """\
## Deviation Rules

When you encounter work not in your task description, apply these rules:

Rule 1 — Fix silently: Typos and syntax errors in your target file. Fix them without reporting.
Rule 2 — Fix silently: Missing imports required by your implementation. Add them without reporting.
Rule 3 — Fix silently: Broken tests caused directly by your changes. Fix them without reporting.
Rule 4 — STOP and report BLOCKED: Architectural changes, new dependencies not in your requirements, \
new database tables or schemas, changes to files outside your target file, or scope beyond your \
task description. Set status to BLOCKED and explain the issue in concerns.
"""


class AgentIdentity(BaseModel):
    """Immutable identity record for an agent spawned by the orchestrator."""

    model_config = ConfigDict(use_enum_values=True)

    name: str
    role: str
    target_file: str
    material_files: list[str] = Field(default_factory=list)
    task_id: str
    task_description: str


def build_system_prompt(identity: AgentIdentity) -> str:
    """Build a lean system prompt string from an AgentIdentity.

    The prompt establishes the agent's persona, task scope, and file boundaries.
    It uses file paths only (no file content) to keep the prompt under 500 tokens.
    The task description is sent separately as the first user message.

    Args:
        identity: The AgentIdentity to build a prompt for.

    Returns:
        A concise multi-line system prompt string with file paths only.
    """
    memory_file = f".memory/{identity.name}.md"

    parts = [
        f"You are {identity.name}, a {identity.role}.",
        "",
        f"Task: {identity.task_id}",
        f"Target file: {identity.target_file}",
    ]

    if identity.material_files:
        material_list = "\n".join(f"  - {f}" for f in identity.material_files)
        parts.append("")
        parts.append(f"Read these files for context:\n{material_list}")

    parts.append("")
    parts.append(
        f"Memory: {memory_file} — write decisions here, read other agents' at .memory/."
    )
    parts.append("")
    parts.append("Stay within your target file and memory file. Do not modify other files.")

    parts.append("")
    parts.append(STATUS_BLOCK_INSTRUCTIONS)

    parts.append("")
    parts.append(DEVIATION_RULES)

    return "\n".join(parts)
