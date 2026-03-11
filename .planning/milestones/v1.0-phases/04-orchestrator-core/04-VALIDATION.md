---
phase: 04
slug: orchestrator-core
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-10
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_decomposer.py tests/test_scheduler.py tests/test_file_ownership.py tests/test_orchestrator.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_decomposer.py tests/test_scheduler.py tests/test_file_ownership.py tests/test_orchestrator.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | ORCH-01 | unit | `pytest tests/test_decomposer.py::TestOrch01Decompose -x` | ✅ | ✅ green |
| 04-01-02 | 01 | 1 | ORCH-01 | unit | `pytest tests/test_decomposer.py::TestOrch01RetryError -x` | ✅ | ✅ green |
| 04-01-03 | 01 | 1 | ORCH-01 | unit | `pytest tests/test_decomposer.py::TestOrch01Schema -x` | ✅ | ✅ green |
| 04-02-01 | 02 | 1 | CORD-04 | unit | `pytest tests/test_scheduler.py::TestCord04Ready -x` | ✅ | ✅ green |
| 04-02-02 | 02 | 1 | CORD-04 | unit | `pytest tests/test_scheduler.py::TestCord04Sequencing -x` | ✅ | ✅ green |
| 04-02-03 | 02 | 1 | CORD-04 | unit | `pytest tests/test_scheduler.py::TestCord04Cycle -x` | ✅ | ✅ green |
| 04-03-01 | 03 | 1 | CORD-05 | unit | `pytest tests/test_file_ownership.py::TestCord05Conflict -x` | ✅ | ✅ green |
| 04-03-02 | 03 | 1 | CORD-05 | unit | `pytest tests/test_file_ownership.py::TestCord05NoConflict -x` | ✅ | ✅ green |
| 04-04-01 | 04 | 2 | ORCH-02 | unit | `pytest tests/test_orchestrator.py::TestOrch02Spawn -x` | ✅ | ✅ green |
| 04-04-02 | 04 | 2 | ORCH-06 | unit | `pytest tests/test_orchestrator.py::TestOrch06Identity -x` | ✅ | ✅ green |
| 04-04-03 | 04 | 2 | ORCH-06 | unit | `pytest tests/test_orchestrator.py::TestOrch06StateRecord -x` | ✅ | ✅ green |
| 04-04-04 | 04 | 2 | SC-5 | unit | `pytest tests/test_orchestrator.py::TestMaxAgentsCap -x` | ✅ | ✅ green |

*Status: ✅ green · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_decomposer.py` — stubs for ORCH-01: mock `query()`, `TaskPlan` schema, retry error
- [ ] `tests/test_scheduler.py` — stubs for CORD-04: topological ordering, cycle detection, parallel readiness
- [ ] `tests/test_file_ownership.py` — stubs for CORD-05: conflict detection, clean ownership map
- [ ] `tests/test_orchestrator.py` — stubs for ORCH-02, ORCH-06, SC-5: spawn flow, identity injection, `max_agents` cap

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

**Approval:** validated 2026-03-11

## Validation Audit 2026-03-11
| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All ORCH-01/02/06, CORD-04/05 tests green: 78 tests across 5 test files.
