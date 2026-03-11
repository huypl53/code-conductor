---
phase: 43
slug: agent-cell-widgets
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 43 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` |
| **Quick run command** | `cd packages/conductor-core && python -m pytest tests/test_tui_agent_cells.py -x` |
| **Full suite command** | `cd packages/conductor-core && python -m pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && python -m pytest tests/test_tui_agent_cells.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 43-01-01 | 01 | 1 | ACELL-04 (SC1) | unit | `pytest tests/test_tui_agent_cells.py::test_agent_cell_header_content -x` | ❌ W0 | ⬜ pending |
| 43-01-02 | 01 | 1 | ACELL-04 (SC2) | unit | `pytest tests/test_tui_agent_cells.py::test_agent_cell_update_status -x` | ❌ W0 | ⬜ pending |
| 43-01-03 | 01 | 1 | ACELL-04 (SC3) | unit | `pytest tests/test_tui_agent_cells.py::test_agent_cell_finalize_defensive -x` | ❌ W0 | ⬜ pending |
| 43-01-04 | 01 | 1 | ACELL-04 (SC4) | unit | `pytest tests/test_tui_agent_cells.py::test_orchestrator_status_cell_lifecycle -x` | ❌ W0 | ⬜ pending |
| 43-01-05 | 01 | 1 | ACELL-04 (SC5) | unit | `pytest tests/test_tui_agent_cells.py::test_multiple_agent_cells_no_id_collision -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui_agent_cells.py` — stubs for ACELL-04 (all 5 success criteria)

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
