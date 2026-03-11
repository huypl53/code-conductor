---
phase: 15
slug: fix-dashboard-cancel-type
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/dashboard/test_server_interventions.py -v` |
| **Full suite command** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run --project packages/conductor-core pytest packages/conductor-core/tests/dashboard/test_server_interventions.py -v`
- **After every plan wave:** Run `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 15-01-01 | 01 | 1 | COMM-05 | integration | `pytest tests/dashboard/test_server_interventions.py -k "cancel" -v` | ✅ | ⬜ pending |
| 15-01-02 | 01 | 1 | DASH-06 | integration | `pytest tests/dashboard/test_server_interventions.py -k "redirect" -v` | ✅ | ⬜ pending |
| 15-01-03 | 01 | 1 | COMM-05, DASH-06 | integration | `pytest tests/dashboard/test_server_interventions.py -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files or framework installs needed. Tests 1 and 3 in `test_server_interventions.py` exist but need assertion updates as part of the fix.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
