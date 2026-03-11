"""Phase 31: TUI Foundation tests.

Tests for ConductorApp headless launch, prompt_toolkit isolation,
and delegation.py ANSI cleanup.

IMPORTANT: Keep run_test() inline in each test function — never in fixtures.
This avoids Textual's contextvars/pytest-asyncio incompatibility (GitHub #4998).
"""
import importlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Test 1: App starts in headless mode without error
# ---------------------------------------------------------------------------

async def test_conductor_app_starts_headless():
    """ConductorApp must start without RuntimeError or NoActiveAppError."""
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    async with app.run_test() as pilot:
        assert pilot.app is not None
        assert not pilot.app._closed


# ---------------------------------------------------------------------------
# Test 2: App exits cleanly
# ---------------------------------------------------------------------------

async def test_conductor_app_exits_cleanly():
    """App.exit() must not raise or leave terminal in broken state."""
    from conductor.tui.app import ConductorApp

    app = ConductorApp()
    async with app.run_test() as pilot:
        await pilot.app.action_quit()
    # No exception = pass


# ---------------------------------------------------------------------------
# Test 3: prompt_toolkit not imported in tui code path
# ---------------------------------------------------------------------------

def test_no_prompt_toolkit_in_tui_imports():
    """Importing conductor.tui.app must not trigger any prompt_toolkit import."""
    # Unload any cached module to get a clean import trace
    mods_before = set(sys.modules.keys())

    # Force reimport
    if "conductor.tui.app" in sys.modules:
        del sys.modules["conductor.tui.app"]

    import conductor.tui.app  # noqa: F401

    new_mods = set(sys.modules.keys()) - mods_before
    pt_mods = [m for m in new_mods if "prompt_toolkit" in m]
    assert pt_mods == [], f"prompt_toolkit imported via tui.app: {pt_mods}"


# ---------------------------------------------------------------------------
# Test 4 & 5: DelegationManager cleanup
# ---------------------------------------------------------------------------

def test_delegation_manager_no_status_updater():
    """DelegationManager must not have _status_updater or _clear_status_lines."""
    from conductor.cli.delegation import DelegationManager

    dm = DelegationManager(repo_path="/tmp")
    assert not hasattr(dm, "_status_updater"), "_status_updater was not removed"
    assert not hasattr(dm, "_clear_status_lines"), "_clear_status_lines was not removed"
    assert not hasattr(dm, "_print_live_status"), "_print_live_status was not removed"


def test_delegation_manager_no_console_required():
    """DelegationManager must be constructable without a Rich Console argument."""
    from conductor.cli.delegation import DelegationManager

    # Must not raise even without console
    dm = DelegationManager(repo_path="/tmp")
    assert dm is not None
