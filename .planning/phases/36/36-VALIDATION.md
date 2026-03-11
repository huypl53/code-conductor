---
phase: 36
slug: approval-modals
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 36 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_approval.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 36-01-01 | 01 | 1 | APRV-01 | unit/headless | `pytest tests/test_tui_approval.py::test_file_approval_modal -x` | ❌ W0 | ⬜ pending |
| 36-01-02 | 01 | 1 | APRV-02 | unit/headless | `pytest tests/test_tui_approval.py::test_command_approval_modal -x` | ❌ W0 | ⬜ pending |
| 36-01-03 | 01 | 1 | APRV-03 | unit/headless | `pytest tests/test_tui_approval.py::test_escalation_reply_modal -x` | ❌ W0 | ⬜ pending |
| 36-01-04 | 01 | 1 | APRV-01 | unit/headless | `pytest tests/test_tui_approval.py::test_modal_dismiss_reactivates -x` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_tui_approval.py` — stubs for APRV-01, APRV-02, APRV-03

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real escalation from delegation | APRV-03 | Requires live orchestrator | Run conductor delegation, trigger escalation |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
