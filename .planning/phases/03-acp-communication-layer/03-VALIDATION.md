---
phase: 3
slug: acp-communication-layer
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_acp_client.py tests/test_acp_permission.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_acp_client.py tests/test_acp_permission.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 0 | COMM-01 | unit | `pytest tests/test_acp_client.py::TestComm01Streaming -x` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 0 | COMM-01 | unit | `pytest tests/test_acp_permission.py::TestComm01PermissionCallback -x` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 0 | COMM-01 | unit | `pytest tests/test_acp_permission.py::TestComm01Timeout -x` | ❌ W0 | ⬜ pending |
| 3-01-04 | 01 | 0 | COMM-02 | unit | `pytest tests/test_acp_permission.py::TestComm02AnswerQuestion -x` | ❌ W0 | ⬜ pending |
| 3-01-05 | 01 | 0 | COMM-01 | unit | `pytest tests/test_acp_client.py::TestComm01SessionLifecycle -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_acp_client.py` — stubs for COMM-01 streaming and session lifecycle
- [ ] `tests/test_acp_permission.py` — stubs for COMM-01 permission callback, timeout, and COMM-02 answer routing
- [ ] `pytest-asyncio` install: `uv add --dev pytest-asyncio`
- [ ] `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Resource leak detection under real subprocess | COMM-01 | Requires real Claude CLI process; unit tests mock SDK | Run integration test with real sub-agent; verify no zombie processes after session close |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
