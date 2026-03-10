---
phase: 09
slug: dashboard-backend
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_dashboard_events.py tests/test_dashboard.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_dashboard_events.py tests/test_dashboard.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | DASH-04 | unit | `pytest tests/test_dashboard_events.py::test_classify_task_failed -x` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 1 | DASH-04 | unit | `pytest tests/test_dashboard_events.py::test_classify_task_completed -x` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 1 | DASH-04 | unit | `pytest tests/test_dashboard_events.py::test_classify_intervention_needed -x` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 2 | DASH-04 | integration | `pytest tests/test_dashboard.py::test_get_state -x` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 2 | DASH-04 | integration | `pytest tests/test_dashboard.py::test_ws_delta_on_state_change -x` | ❌ W0 | ⬜ pending |
| 09-02-03 | 02 | 2 | DASH-04 | integration | `pytest tests/test_dashboard.py::test_ws_initial_state_on_connect -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_dashboard_events.py` — unit tests for classify_delta, DeltaEvent, smart notification flags
- [ ] `tests/test_dashboard.py` — integration tests for REST and WebSocket endpoints
- [ ] Install: `uv add --package conductor-core "fastapi>=0.135" "uvicorn>=0.41" "watchfiles>=1.1"`

*Existing infrastructure covers pytest framework and asyncio configuration.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dashboard accessible at localhost URL | DASH-04 | Requires running server | Start conductor with --dashboard, open browser |
| Delta latency < 1 second | DASH-04 | Timing-sensitive | Monitor WS messages during active orchestration |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
