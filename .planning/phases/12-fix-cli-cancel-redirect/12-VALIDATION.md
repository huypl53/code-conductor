---
phase: 12
slug: fix-cli-cancel-redirect
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_cli.py -x -q` |
| **Full suite command** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_cli.py -x -q`
- **After every plan wave:** Run `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | CLI-03, COMM-05 | unit+integration | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_cli.py -x -q` | Yes | ⬜ pending |
| 12-01-02 | 01 | 1 | COMM-05 | integration | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -k cancel -x -q` | ❌ W0 | ⬜ pending |
| 12-01-03 | 01 | 1 | CLI-03, COMM-05 | integration | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -k redirect -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Integration test for `cancel_agent(agent_id)` — validates actual body, not just mock call shape
- [ ] Integration test for `cancel_agent(agent_id, new_instructions="...")` — validates redirect path

*Existing test infrastructure is in place; only new test cases are needed, not new files or framework installs.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
