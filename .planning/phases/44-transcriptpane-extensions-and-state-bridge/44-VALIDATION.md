---
phase: 44
slug: transcriptpane-extensions-and-state-bridge
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 44 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_transcript_bridge.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_tui_transcript_bridge.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 44-01-01 | 01 | 1 | BRDG-01 | unit | `pytest tests/test_tui_transcript_bridge.py::test_state_update_forwarded_to_transcript -x` | ❌ W0 | ⬜ pending |
| 44-01-02 | 01 | 1 | BRDG-02 | unit | `pytest tests/test_tui_transcript_bridge.py::test_agent_cells_registry_no_duplicates -x` | ❌ W0 | ⬜ pending |
| 44-01-03 | 01 | 1 | ACELL-01 | unit | `pytest tests/test_tui_transcript_bridge.py::test_working_agent_mounts_cell -x` | ❌ W0 | ⬜ pending |
| 44-01-04 | 01 | 1 | ACELL-02 | unit | `pytest tests/test_tui_transcript_bridge.py::test_status_transition_updates_cell -x` | ❌ W0 | ⬜ pending |
| 44-01-05 | 01 | 1 | ACELL-03 | unit | `pytest tests/test_tui_transcript_bridge.py::test_done_agent_finalizes_cell -x` | ❌ W0 | ⬜ pending |
| 44-01-06 | 01 | 1 | SC-5 | unit | `pytest tests/test_tui_transcript_bridge.py::test_scroll_preserved_when_scrolled_up -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui_transcript_bridge.py` — new file covering all 5 requirements + scroll preservation

*Existing infrastructure covers framework setup — no new fixtures or config needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
