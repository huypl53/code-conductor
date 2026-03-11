"""Tests for AgentIdentity and build_system_prompt — including memory section."""
from __future__ import annotations

import pytest

from conductor.orchestrator.identity import AgentIdentity, build_system_prompt


def _make_identity(
    name: str = "agent-alpha",
    role: str = "backend developer",
    target_file: str = "src/auth.py",
    material_files: list[str] | None = None,
    task_id: str = "task-1",
    task_description: str = "Implement authentication",
) -> AgentIdentity:
    return AgentIdentity(
        name=name,
        role=role,
        target_file=target_file,
        material_files=material_files or [],
        task_id=task_id,
        task_description=task_description,
    )


class TestBuildSystemPromptCore:
    """Existing build_system_prompt behavior must not regress."""

    def test_prompt_contains_agent_name(self) -> None:
        identity = _make_identity(name="agent-alpha")
        prompt = build_system_prompt(identity)
        assert "agent-alpha" in prompt

    def test_prompt_contains_role(self) -> None:
        identity = _make_identity(role="security engineer")
        prompt = build_system_prompt(identity)
        assert "security engineer" in prompt

    def test_prompt_contains_target_file(self) -> None:
        identity = _make_identity(target_file="src/auth.py")
        prompt = build_system_prompt(identity)
        assert "src/auth.py" in prompt

    def test_prompt_does_not_contain_task_description(self) -> None:
        """Task description is sent as first user message, not in system prompt (LEAN-01)."""
        identity = _make_identity(task_description="Implement JWT auth")
        prompt = build_system_prompt(identity)
        assert "Implement JWT auth" not in prompt

    def test_prompt_contains_task_id(self) -> None:
        """Task ID (not full description) should appear in the lean prompt."""
        identity = _make_identity(task_id="task-42")
        prompt = build_system_prompt(identity)
        assert "task-42" in prompt

    def test_prompt_contains_material_files(self) -> None:
        identity = _make_identity(material_files=["src/utils.py", "src/models.py"])
        prompt = build_system_prompt(identity)
        assert "src/utils.py" in prompt
        assert "src/models.py" in prompt

    def test_prompt_no_material_files_omits_context_section(self) -> None:
        """When no material files, the 'Read these files' section is omitted."""
        identity = _make_identity(material_files=[])
        prompt = build_system_prompt(identity)
        assert "Read these files for context" not in prompt


class TestBuildSystemPromptMemorySection:
    """Memory section added in Phase 7."""

    def test_prompt_contains_memory_file_path(self) -> None:
        """Output must include .memory/<identity.name>.md."""
        identity = _make_identity(name="agent-alpha")
        prompt = build_system_prompt(identity)
        assert ".memory/agent-alpha.md" in prompt

    def test_prompt_contains_write_instruction_for_memory(self) -> None:
        """Output must include a 'Write' instruction for the memory file."""
        identity = _make_identity(name="agent-beta")
        prompt = build_system_prompt(identity)
        # Case-insensitive check: instruction to write to memory file
        assert "Write" in prompt or "write" in prompt

    def test_prompt_contains_read_other_agents_instruction(self) -> None:
        """Output must instruct the agent to read other agents' memory files."""
        identity = _make_identity(name="agent-gamma")
        prompt = build_system_prompt(identity)
        assert "other agents" in prompt.lower() or "Read other" in prompt

    def test_prompt_file_boundary_includes_memory_exception(self) -> None:
        """File boundary rule must name .memory/ as an exception."""
        identity = _make_identity(name="agent-delta")
        prompt = build_system_prompt(identity)
        # Must still restrict files outside target
        assert "Do not modify other files" in prompt
        # Must carve out memory file as exception
        assert ".memory/" in prompt

    def test_memory_file_uses_identity_name(self) -> None:
        """Memory file path in prompt must use the actual agent name, not a placeholder."""
        identity = _make_identity(name="agent-zeta")
        prompt = build_system_prompt(identity)
        assert ".memory/agent-zeta.md" in prompt
        # Make sure the generic placeholder isn't there
        assert "<agent-name>" not in prompt


class TestOrchestratorMaxAgentsDefault:
    """Orchestrator default max_agents must be 10 (decomposer-driven sizing)."""

    def test_orchestrator_default_max_agents_is_10(self) -> None:
        from unittest.mock import MagicMock

        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = MagicMock()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo")
        assert orch._max_agents == 10

    def test_orchestrator_explicit_max_agents_override(self) -> None:
        """Explicit max_agents kwarg overrides the default of 10."""
        from unittest.mock import MagicMock

        from conductor.orchestrator.orchestrator import Orchestrator

        state_mgr = MagicMock()
        orch = Orchestrator(state_manager=state_mgr, repo_path="/repo", max_agents=3)
        assert orch._max_agents == 3
