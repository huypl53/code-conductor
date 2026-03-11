"""Tests for conductor run command resume flag."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunResume:
    """Tests for --resume flag on conductor run."""

    @pytest.mark.asyncio
    async def test_resume_calls_orchestrator_resume(self, tmp_path):
        """--resume should call orchestrator.resume() instead of run_auto()."""
        from conductor.cli.commands.run import _run_async

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.resume = AsyncMock()
            mock_orch.run_auto = AsyncMock()
            mock_orch.run = AsyncMock()

            await _run_async("ignored", auto=True, repo=tmp_path, resume=True)

            mock_orch.resume.assert_called_once()
            mock_orch.run_auto.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_resume_calls_run_auto(self, tmp_path):
        """Without --resume, should call run_auto() as before."""
        from conductor.cli.commands.run import _run_async

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.resume = AsyncMock()
            mock_orch.run_auto = AsyncMock()
            mock_orch.run = AsyncMock()

            await _run_async("desc", auto=True, repo=tmp_path, resume=False)

            mock_orch.run_auto.assert_called_once_with("desc")
            mock_orch.resume.assert_not_called()


class TestRunBuildCommand:
    """Tests for --build-command flag on conductor run."""

    @pytest.mark.asyncio
    async def test_build_command_passed_to_orchestrator(self, tmp_path):
        """--build-command value should be forwarded to Orchestrator constructor."""
        from conductor.cli.commands.run import _run_async

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.run_auto = AsyncMock()

            await _run_async(
                "desc", auto=True, repo=tmp_path,
                build_command="npx tsc --noEmit",
            )

            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") == "npx tsc --noEmit"

    @pytest.mark.asyncio
    async def test_no_build_command_default(self, tmp_path):
        """Without --build-command, Orchestrator receives build_command=None."""
        from conductor.cli.commands.run import _run_async

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.run_auto = AsyncMock()

            await _run_async("desc", auto=True, repo=tmp_path)

            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") is None


class TestConfigJsonBuildCommand:
    """Tests for config.json build_command loading in conductor run."""

    @pytest.mark.asyncio
    async def test_config_json_provides_build_command(self, tmp_path):
        """config.json build_command is used when no CLI flag is given."""
        import json
        from conductor.cli.commands.run import _run_async

        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        (conductor_dir / "config.json").write_text(
            json.dumps({"build_command": "make test"})
        )

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.run_auto = AsyncMock()

            await _run_async("desc", auto=True, repo=tmp_path)

            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") == "make test"

    @pytest.mark.asyncio
    async def test_cli_flag_overrides_config_json(self, tmp_path):
        """CLI --build-command takes precedence over config.json value."""
        import json
        from conductor.cli.commands.run import _run_async

        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        (conductor_dir / "config.json").write_text(
            json.dumps({"build_command": "make test"})
        )

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.run_auto = AsyncMock()

            await _run_async(
                "desc", auto=True, repo=tmp_path,
                build_command="npx tsc --noEmit",
            )

            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") == "npx tsc --noEmit"

    @pytest.mark.asyncio
    async def test_malformed_config_json_ok(self, tmp_path):
        """Malformed config.json should not crash — build_command falls back to None."""
        from conductor.cli.commands.run import _run_async

        conductor_dir = tmp_path / ".conductor"
        conductor_dir.mkdir()
        (conductor_dir / "config.json").write_text("this is not valid json {{{")

        with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
             patch("conductor.cli.commands.run.Live"), \
             patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
             patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
            mock_orch = MockOrch.return_value
            mock_orch.run_auto = AsyncMock()

            # Should not raise
            await _run_async("desc", auto=True, repo=tmp_path)

            call_kwargs = MockOrch.call_args[1]
            assert call_kwargs.get("build_command") is None
