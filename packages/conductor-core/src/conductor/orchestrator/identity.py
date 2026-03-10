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
    """Build a system prompt string from an AgentIdentity.

    The prompt establishes the agent's persona, task scope, and file boundaries.
    It is designed to anchor the agent's role throughout a long session.

    Args:
        identity: The AgentIdentity to build a prompt for.

    Returns:
        A multi-line system prompt string.
    """
    material_section: str
    if identity.material_files:
        material_list = "\n".join(f"  - {f}" for f in identity.material_files)
        material_section = f"Reference files (read-only context):\n{material_list}"
    else:
        material_section = "Reference files: none"

    return (
        f"You are {identity.name}, a {identity.role}.\n\n"
        f"Task ID: {identity.task_id}\n"
        f"Task: {identity.task_description}\n\n"
        f"Your assigned file:\n  {identity.target_file}\n\n"
        f"{material_section}\n\n"
        "Do not modify files outside your assignment. "
        "Focus exclusively on your target file and task."
    )
