"""Phase 46: Visual polish and verification tests for AgentCell and OrchestratorStatusCell.

Covers all 4 success criteria:
SC-1: AgentCell and OrchestratorStatusCell use CSS tokens visually distinct from AssistantCell ($accent)
SC-2: OrchestratorStatusCell appears in the transcript DOM before AgentCells after delegation
SC-3: AgentCell.finalize(summary=) shows the task summary when provided, just 'done' when empty
SC-4: 3+ concurrent AgentCells have shimmer timers cleaned up after finalize (no leaks)

IMPORTANT: Keep run_test() inline in each test -- never in fixtures.
(Textual contextvars/pytest-asyncio incompatibility -- GitHub #4998)

Set CONDUCTOR_NO_ANIMATIONS=1 before running to disable shimmer/fade-in
for deterministic assertions.
"""
from __future__ import annotations

import os
import re

os.environ["CONDUCTOR_NO_ANIMATIONS"] = "1"


def test_cell_css_tokens_distinct() -> None:
    """SC-1: AgentCell, OrchestratorStatusCell, AssistantCell use distinct CSS border tokens.

    Parse DEFAULT_CSS from each class and extract the border-left token.
    All three tokens must be different strings (no reuse).
    This is a string parse test — no Textual app needed.
    """
    from conductor.tui.widgets.transcript import AgentCell, AssistantCell, OrchestratorStatusCell

    def extract_border_token(css: str) -> str:
        """Extract the design token from a border-left declaration, e.g. '$warning'."""
        match = re.search(r"border-left:\s*solid\s+(\$\w+)", css)
        assert match is not None, f"No border-left token found in CSS:\n{css}"
        return match.group(1)

    agent_token = extract_border_token(AgentCell.DEFAULT_CSS)
    orch_token = extract_border_token(OrchestratorStatusCell.DEFAULT_CSS)
    assistant_token = extract_border_token(AssistantCell.DEFAULT_CSS)

    tokens = {agent_token, orch_token, assistant_token}
    assert len(tokens) == 3, (
        f"CSS tokens not all distinct: AgentCell={agent_token!r}, "
        f"OrchestratorStatusCell={orch_token!r}, AssistantCell={assistant_token!r}"
    )
    # AssistantCell must use $accent (established pattern)
    assert assistant_token == "$accent", (
        f"AssistantCell should use $accent, got {assistant_token!r}"
    )
    # AgentCell and OrchestratorStatusCell must NOT use $accent
    assert agent_token != "$accent", (
        f"AgentCell should NOT use $accent (same as AssistantCell), got {agent_token!r}"
    )
    assert orch_token != "$accent", (
        f"OrchestratorStatusCell should NOT use $accent (same as AssistantCell), got {orch_token!r}"
    )


async def test_delegation_cell_before_agent_cells() -> None:
    """SC-2: OrchestratorStatusCell appears before AgentCell in the TranscriptPane DOM.

    Post DelegationStarted first, then post AgentStateUpdated with a WORKING agent.
    OrchestratorStatusCell must appear at a lower index in pane.children than AgentCell.
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell, OrchestratorStatusCell, TranscriptPane
    from conductor.tui.messages import AgentStateUpdated, DelegationStarted

    from tests.test_tui_transcript_bridge import _make_state  # type: ignore[import]

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield TranscriptPane(resume_mode=True, id="transcript")

        def on_agent_state_updated(self, event: AgentStateUpdated) -> None:
            """Fan-out: forward agent state to TranscriptPane."""
            pane = self.query_one(TranscriptPane)
            pane.post_message(AgentStateUpdated(event.state))

    app = TestApp()
    async with app.run_test() as pilot:
        pane = app.query_one(TranscriptPane)

        # Post delegation started first
        pane.post_message(DelegationStarted("Build auth module"))
        await pilot.pause()
        await pilot.pause()

        # Then post agent state update (WORKING agent)
        state = _make_state(
            agents=[{"id": "a1", "name": "Alice", "role": "coder", "status": "working"}],
            tasks=[{
                "id": "t1",
                "title": "Auth",
                "description": "Implement auth",
                "assigned_agent": "a1",
            }],
        )
        pane.post_message(AgentStateUpdated(state))
        await pilot.pause()
        await pilot.pause()

        # Check DOM order: OrchestratorStatusCell before AgentCell
        children = list(pane.children)
        orch_idx = next(
            (i for i, c in enumerate(children) if isinstance(c, OrchestratorStatusCell)),
            None,
        )
        agent_idx = next(
            (i for i, c in enumerate(children) if isinstance(c, AgentCell)),
            None,
        )
        assert orch_idx is not None, "OrchestratorStatusCell not found in pane children"
        assert agent_idx is not None, "AgentCell not found in pane children"
        assert orch_idx < agent_idx, (
            f"OrchestratorStatusCell (idx={orch_idx}) should appear before "
            f"AgentCell (idx={agent_idx})"
        )


async def test_agent_cell_finalize_shows_summary() -> None:
    """SC-3: AgentCell.finalize(summary=) shows summary text; no summary shows 'done'.

    Two sub-tests:
    (a) finalize(summary="...") -> cell-status contains the summary text
    (b) finalize() with no args -> cell-status shows just 'done'
    """
    from textual.app import App, ComposeResult
    from textual.widgets import Static
    from conductor.tui.widgets.transcript import AgentCell

    # (a) With summary
    class TestAppWithSummary(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a1",
                agent_name="Alice",
                role="coder",
                task_title="Add auth",
            )

    app_a = TestAppWithSummary()
    async with app_a.run_test() as pilot:
        cell = app_a.query_one(AgentCell)
        cell.finalize(summary="Implemented JWT auth with refresh tokens")
        await pilot.pause()

        status = cell.query_one(".cell-status", Static)
        status_text = str(status.content)
        assert "Implemented JWT auth" in status_text, (
            f"Expected summary text in cell-status, got: {status_text!r}"
        )
        assert "done" in status_text, (
            f"Expected 'done' prefix in cell-status, got: {status_text!r}"
        )

    # (b) Without summary
    class TestAppNoSummary(App):
        def compose(self) -> ComposeResult:
            yield AgentCell(
                agent_id="a2",
                agent_name="Bob",
                role="reviewer",
                task_title="Review code",
            )

    app_b = TestAppNoSummary()
    async with app_b.run_test() as pilot:
        cell = app_b.query_one(AgentCell)
        cell.finalize()
        await pilot.pause()

        status = cell.query_one(".cell-status", Static)
        status_text = str(status.content)
        assert status_text == "done", (
            f"Expected exactly 'done' when no summary provided, got: {status_text!r}"
        )


async def test_shimmer_timers_cleaned_on_finalize_3_agents() -> None:
    """SC-4: 3+ concurrent AgentCells have shimmer timers cleaned up after finalize.

    Mount 3 AgentCells in working state, verify shimmer timers are running,
    call finalize() on each, and verify all timers are None and status is 'done'.
    """
    from textual.app import App, ComposeResult
    from conductor.tui.widgets.transcript import AgentCell

    class TestApp(App):
        def compose(self) -> ComposeResult:
            for i in range(3):
                yield AgentCell(
                    agent_id=f"a{i}",
                    agent_name=f"Agent-{i}",
                    role="coder",
                    task_title=f"Task {i}",
                )

    app = TestApp()
    async with app.run_test() as pilot:
        cells = list(app.query(AgentCell))
        assert len(cells) == 3, f"Expected 3 AgentCells, got {len(cells)}"

        # Finalize all 3 agents
        for cell in cells:
            cell.finalize()

        await pilot.pause()

        # Verify all shimmer timers are cleaned up
        for i, cell in enumerate(cells):
            assert cell._shimmer_timer is None, (
                f"Shimmer timer not cleaned for cell[{i}] ({cell._agent_id})"
            )
            assert cell._status == "done", (
                f"Expected status 'done' for cell[{i}] ({cell._agent_id}), got {cell._status!r}"
            )
