---
phase: 35
slug: agent-monitoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 35 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_agent_monitor.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_tui_agent_monitor.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 35-01-01 | 01 | 1 | AGNT-01 | unit/headless | `pytest tests/test_tui_agent_monitor.py::test_agent_panel_appears -x` | ❌ W0 | ⬜ pending |
| 35-01-02 | 01 | 1 | AGNT-02 | unit/headless | `pytest tests/test_tui_agent_monitor.py::test_agent_panel_updates -x` | ❌ W0 | ⬜ pending |
| 35-01-03 | 01 | 1 | AGNT-03 | unit/headless | `pytest tests/test_tui_agent_monitor.py::test_agent_panel_activity -x` | ❌ W0 | ⬜ pending |
| 35-01-04 | 01 | 1 | AGNT-04 | unit/headless | `pytest tests/test_tui_agent_monitor.py::test_agent_panel_archives -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui_agent_monitor.py` — stubs for AGNT-01 through AGNT-04

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live file watcher updates from state.json | AGNT-02 | Requires real file system events + orchestrator | Run conductor with delegation, verify panels update live |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
