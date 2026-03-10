---
phase: 05
slug: orchestrator-intelligence
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_monitor.py tests/test_reviewer.py tests/test_orchestrator.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_monitor.py tests/test_reviewer.py tests/test_orchestrator.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | ORCH-03 | unit | `pytest tests/test_monitor.py::TestOrch03ToolUse -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | ORCH-03 | unit | `pytest tests/test_monitor.py::TestOrch03Progress -x` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | ORCH-03 | unit | `pytest tests/test_monitor.py::TestOrch03ResultCapture -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | ORCH-04 | unit | `pytest tests/test_reviewer.py::TestOrch04Approved -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | ORCH-04 | unit | `pytest tests/test_reviewer.py::TestOrch04FileMissing -x` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 1 | ORCH-04 | unit | `pytest tests/test_reviewer.py::TestOrch04ReviewError -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | ORCH-04 | unit | `pytest tests/test_orchestrator.py::TestOrch04CompleteGate -x` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 2 | ORCH-05 | unit | `pytest tests/test_orchestrator.py::TestOrch05RevisionSend -x` | ❌ W0 | ⬜ pending |
| 05-03-03 | 03 | 2 | ORCH-05 | unit | `pytest tests/test_orchestrator.py::TestOrch05MaxRevisions -x` | ❌ W0 | ⬜ pending |
| 05-03-04 | 03 | 2 | ORCH-05 | unit | `pytest tests/test_orchestrator.py::TestOrch05SessionOpenForRevision -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_monitor.py` — stubs for ORCH-03: StreamMonitor message dispatch
- [ ] `tests/test_reviewer.py` — stubs for ORCH-04: ReviewVerdict schema, review pass/fail
- [ ] Extend `tests/test_orchestrator.py` — stubs for ORCH-04 complete gate, ORCH-05 revision loop

*Existing infrastructure covers pytest framework and asyncio configuration.*

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
