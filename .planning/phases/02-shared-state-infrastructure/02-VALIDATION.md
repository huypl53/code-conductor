---
phase: 2
slug: shared-state-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `packages/conductor-core/pyproject.toml` — `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_state.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_state.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | CORD-01 | unit | `uv run pytest tests/test_state.py::test_task_round_trip -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 0 | CORD-01 | unit | `uv run pytest tests/test_state.py::test_full_state_round_trip -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 0 | CORD-02 | integration | `uv run pytest tests/test_state.py::test_concurrent_writes_no_corruption -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 0 | CORD-02 | unit | `uv run pytest tests/test_state.py::test_assign_task -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 0 | CORD-03 | unit | `uv run pytest tests/test_state.py::test_update_task_status -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 0 | CORD-03 | unit | `uv run pytest tests/test_state.py::test_orchestrator_observes_status -x` | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 0 | CORD-06 | unit | `uv run pytest tests/test_state.py::test_all_tasks_visible -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `packages/conductor-core/tests/test_state.py` — stubs for CORD-01, CORD-02, CORD-03, CORD-06
- [ ] `packages/conductor-core/tests/conftest.py` — shared fixtures (tmp_path state dir)
- [ ] `packages/conductor-core/src/conductor/state/models.py` — Pydantic models
- [ ] `packages/conductor-core/src/conductor/state/manager.py` — StateManager class
- [ ] `packages/conductor-core/src/conductor/state/errors.py` — StateError, StateLockTimeout

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
