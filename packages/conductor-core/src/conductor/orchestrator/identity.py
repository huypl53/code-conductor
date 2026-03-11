"""AgentIdentity model and system prompt builder for orchestrator-spawned agents."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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

    return "\n".join(parts)
