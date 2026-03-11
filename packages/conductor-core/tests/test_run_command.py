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
