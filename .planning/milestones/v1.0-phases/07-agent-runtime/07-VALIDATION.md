---
phase: 07
slug: agent-runtime
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-10
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/ -x -q` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/ -x -q`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | RUNT-01 | unit | `pytest tests/test_acp_client.py -x -k "setting_sources"` | ✅ extend | ✅ green |
| 07-01-02 | 01 | 1 | RUNT-02 | unit | `pytest tests/test_orchestrator_models.py -x -k "memory"` | ✅ extend | ✅ green |
| 07-01-03 | 01 | 1 | RUNT-02 | unit | `pytest tests/test_orchestrator.py -x -k "memory_dir"` | ✅ extend | ✅ green |
| 07-02-01 | 02 | 1 | RUNT-03 | unit | `pytest tests/test_acp_client.py -x -k "resume"` | ✅ extend | ✅ green |
| 07-02-02 | 02 | 1 | RUNT-03 | unit | `pytest tests/test_orchestrator.py -x -k "restart"` | ✅ extend | ✅ green |
| 07-03-01 | 03 | 2 | RUNT-04 | unit | `pytest tests/test_orchestrator.py -x -k "pre_run_review"` | ✅ extend | ✅ green |
| 07-03-02 | 03 | 2 | RUNT-05 | unit | `pytest tests/test_orchestrator.py -x -k "mode"` | ✅ extend | ✅ green |
| 07-03-03 | 03 | 2 | RUNT-06 | unit | `pytest tests/test_orchestrator.py -x -k "max_agents"` | ✅ extend | ✅ green |

*Status: ✅ green · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Extend `tests/test_acp_client.py` — add setting_sources and resume parameter tests
- [ ] Extend `tests/test_orchestrator_models.py` — add memory path and session_id field tests
- [ ] Extend `tests/test_orchestrator.py` — add memory dir, restart, pre_run_review, mode, max_agents tests

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

All RUNT-01/02/03/04/05/06 tests green: test_identity.py (13) + test_session_registry.py (13) + test_acp_client.py resume tests (5) + test_orchestrator.py runtime classes (21).
