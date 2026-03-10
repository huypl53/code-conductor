---
phase: 06
slug: escalation-and-intervention
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_escalation.py tests/test_orchestrator.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_escalation.py tests/test_orchestrator.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | COMM-03 | unit | `pytest tests/test_escalation.py::TestComm03AutoMode -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | COMM-03 | unit | `pytest tests/test_escalation.py::TestComm03DecisionLog -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | COMM-04 | unit | `pytest tests/test_escalation.py::TestComm04HighConfidenceAuto -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | COMM-04 | unit | `pytest tests/test_escalation.py::TestComm04LowConfidenceEscalate -x` | ❌ W0 | ⬜ pending |
| 06-01-05 | 01 | 1 | COMM-04 | unit | `pytest tests/test_escalation.py::TestComm04EscalationTimeout -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 2 | COMM-05 | unit | `pytest tests/test_orchestrator.py::TestComm05CancelTask -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 2 | COMM-05 | unit | `pytest tests/test_orchestrator.py::TestComm05ReassignSpawns -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 2 | COMM-06 | unit | `pytest tests/test_orchestrator.py::TestComm06InjectSend -x` | ❌ W0 | ⬜ pending |
| 06-02-04 | 02 | 2 | COMM-06 | unit | `pytest tests/test_orchestrator.py::TestComm06UnknownAgent -x` | ❌ W0 | ⬜ pending |
| 06-02-05 | 02 | 2 | COMM-07 | unit | `pytest tests/test_orchestrator.py::TestComm07PauseInterrupt -x` | ❌ W0 | ⬜ pending |
| 06-02-06 | 02 | 2 | COMM-07 | unit | `pytest tests/test_orchestrator.py::TestComm07ResumeAfterDecision -x` | ❌ W0 | ⬜ pending |
| 06-02-07 | 02 | 2 | COMM-07 | unit | `pytest tests/test_orchestrator.py::TestComm07PauseTimeout -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_escalation.py` — stubs for COMM-03, COMM-04: EscalationRouter auto/interactive mode
- [ ] Extend `tests/test_orchestrator.py` — stubs for COMM-05, COMM-06, COMM-07: cancel/reassign, inject, pause/resume

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
