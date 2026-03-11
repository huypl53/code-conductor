---
phase: 37
slug: slash-commands
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 37 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_slash_commands.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 37-01-01 | 01 | 1 | APRV-04 | unit/headless | `pytest tests/test_tui_slash_commands.py::test_slash_autocomplete -x` | ❌ W0 | ⬜ pending |
| 37-01-02 | 01 | 1 | APRV-04 | unit/headless | `pytest tests/test_tui_slash_commands.py::test_slash_command_dispatch -x` | ❌ W0 | ⬜ pending |
| 37-01-03 | 01 | 1 | — | unit/headless | `pytest tests/test_tui_slash_commands.py::test_dashboard_coexistence -x` | ❌ W0 | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/test_tui_slash_commands.py` — stubs for APRV-04

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
