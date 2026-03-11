---
phase: 33
slug: sdk-streaming
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 33 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + pytest-textual-snapshot |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_streaming.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_tui_streaming.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 33-01-01 | 01 | 1 | TRNS-02 | unit/headless | `pytest tests/test_tui_streaming.py::test_thinking_indicator_appears -x` | ❌ W0 | ⬜ pending |
| 33-01-02 | 01 | 1 | TRNS-02 | unit/headless | `pytest tests/test_tui_streaming.py::test_token_chunk_routes_to_cell -x` | ❌ W0 | ⬜ pending |
| 33-01-03 | 01 | 1 | TRNS-02 | unit/headless | `pytest tests/test_tui_streaming.py::test_stream_done_finalizes -x` | ❌ W0 | ⬜ pending |
| 33-01-04 | 01 | 1 | STAT-01 | unit/headless | `pytest tests/test_tui_streaming.py::test_status_footer_token_update -x` | ❌ W0 | ⬜ pending |
| 33-01-05 | 01 | 1 | STAT-01 | unit/headless | `pytest tests/test_tui_streaming.py::test_status_footer_session_id -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui_streaming.py` — stubs for TRNS-02, STAT-01
- [ ] No new framework config needed — existing pytest setup applies

*Note on SDK mocking: Tests use direct `post_message(TokenChunk(...))` and `post_message(StreamDone())` to simulate SDK output. The `@work` coroutine's SDK integration is covered by manual smoke testing.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real SDK streaming end-to-end | TRNS-02 | Requires API key + subprocess | Run `conductor`, type a prompt, verify tokens stream visibly |
| Model name in footer from live SDK | STAT-01 | Requires live SDK connection | Check footer shows actual model name during streaming |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
