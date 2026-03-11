---
phase: 38
slug: session-persistence-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 38 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_session_polish.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 38-01-01 | 01 | 1 | STAT-03 | unit/headless | `pytest tests/test_tui_session_polish.py::test_session_replay -x` | ❌ W0 | ⬜ pending |
| 38-01-02 | 01 | 1 | STAT-02 | unit/headless | `pytest tests/test_tui_session_polish.py::test_shimmer_animation -x` | ❌ W0 | ⬜ pending |
| 38-01-03 | 01 | 1 | STAT-03 | unit/headless | `pytest tests/test_tui_session_polish.py::test_input_disabled_during_replay -x` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_tui_session_polish.py` — stubs for STAT-02, STAT-03

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual shimmer animation appearance | STAT-02 | Headless tests verify CSS class, not visual effect | Run conductor, send prompt, observe streaming cell shimmer |
| Full E2E smoke test | — | Requires live SDK + orchestrator | Launch, prompt, stream, agent monitor, modal, slash cmd, resume |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
