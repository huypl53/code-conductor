---
phase: 13
slug: wire-escalation-pause
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Python) + vitest 4.x (TypeScript) |
| **Config file** | `packages/conductor-core/pyproject.toml` / `packages/conductor-dashboard/vitest.config.ts` |
| **Quick run command (Python)** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -x -q` |
| **Quick run command (TS)** | `pnpm --filter conductor-dashboard test --reporter=verbose` |
| **Full suite command** | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/ -q && pnpm --filter conductor-dashboard test` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick command for relevant stack (Python or TS)
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | COMM-03, COMM-04 | unit | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_orchestrator.py -k "permission_handler" -x -q` | ✅ | ✅ green |
| 13-01-02 | 01 | 1 | COMM-07 | unit | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/test_cli.py -k "pause" -x -q` | ✅ | ✅ green |
| 13-02-01 | 02 | 1 | COMM-07 | unit | `uv run --project packages/conductor-core pytest packages/conductor-core/tests/dashboard/test_server_interventions.py -k "pause" -x -q` | ✅ | ✅ green |
| 13-02-02 | 02 | 1 | COMM-07 | unit | `pnpm --filter conductor-dashboard test -- --reporter=verbose InterventionPanel` | ✅ | ✅ green |

*Status: ✅ green · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `test_orchestrator.py` — add test that `_run_agent_loop` creates PermissionHandler with `answer_fn=escalation_router.resolve`
- [ ] `test_cli.py` — add test for `pause <agent_id> <question>` dispatch
- [ ] `test_server_interventions.py` — add test for `pause` action in handle_intervention
- [ ] `InterventionPanel.test.tsx` — add tests for Pause button render and send

*No new test files or framework installs needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-03-11

## Validation Audit 2026-03-11
| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All COMM-03/04/07 tests green: TestPermissionHandlerWiring (3) + pause dispatch tests (5) + InterventionPanel Pause tests (4).
