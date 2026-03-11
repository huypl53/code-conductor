---
phase: 45
slug: sdk-stream-interception-and-orchestrator-status
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 45 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_stream_interception.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_tui_stream_interception.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 45-01-01 | 01 | 1 | STRM-01 | unit | `pytest tests/test_tui_stream_interception.py::test_content_block_start_triggers_label_change -x` | ❌ W0 | ⬜ pending |
| 45-01-02 | 01 | 1 | STRM-02 | unit | `pytest tests/test_tui_stream_interception.py::test_input_json_delta_accumulation -x` | ❌ W0 | ⬜ pending |
| 45-01-03 | 01 | 1 | ORCH-01 | unit | `pytest tests/test_tui_stream_interception.py::test_active_cell_label_becomes_orchestrator -x` | ❌ W0 | ⬜ pending |
| 45-01-04 | 01 | 1 | ORCH-02 | unit | `pytest tests/test_tui_stream_interception.py::test_orch_status_cell_shows_task_description -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui_stream_interception.py` — new file covering all 4 requirements

*Existing infrastructure covers framework setup — no new fixtures or config needed.*

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

**Approval:** pending
