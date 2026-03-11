---
phase: 16
slug: fix-agent-status-lifecycle
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 16 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_orchestrator.py -v -k "status"` |
| **Full suite command** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_orchestrator.py -v -k "status"`
- **After every plan wave:** Run `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 16-01-01 | 01 | 1 | DASH-01 | unit | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_orchestrator.py -v -k "complete_task_sets_agent_done"` | ✅ | ⬜ pending |
| 16-01-02 | 01 | 1 | DASH-04 | unit | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_orchestrator.py -v -k "pause_sets_waiting"` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files or fixtures needed — tests are added to `packages/conductor-core/tests/test_orchestrator.py`.

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
