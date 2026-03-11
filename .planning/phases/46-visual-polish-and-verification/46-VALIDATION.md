---
phase: 46
slug: visual-polish-and-verification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 46 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_visual_polish.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_tui_visual_polish.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 46-01-01 | 01 | 1 | SC-1 | unit | `pytest tests/test_tui_visual_polish.py::test_cell_css_tokens_distinct -x` | ❌ W0 | ⬜ pending |
| 46-01-02 | 01 | 1 | SC-2 | unit | `pytest tests/test_tui_visual_polish.py::test_delegation_cell_before_agent_cells -x` | ❌ W0 | ⬜ pending |
| 46-01-03 | 01 | 1 | SC-3 | unit | `pytest tests/test_tui_visual_polish.py::test_agent_cell_finalize_shows_summary -x` | ❌ W0 | ⬜ pending |
| 46-01-04 | 01 | 1 | SC-4 | unit | `pytest tests/test_tui_visual_polish.py::test_shimmer_timers_cleaned_on_finalize_3_agents -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui_visual_polish.py` — new file covering all 4 success criteria

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
