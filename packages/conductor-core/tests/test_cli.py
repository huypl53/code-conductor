"""Tests for the Conductor CLI."""

import subprocess

import conductor


def test_conductor_help() -> None:
    """Test that conductor --help runs successfully."""
    result = subprocess.run(
        ["uv", "run", "conductor", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "conductor" in result.stdout.lower()


def test_conductor_version() -> None:
    """Test that the conductor module has a version string."""
    assert isinstance(conductor.__version__, str)
