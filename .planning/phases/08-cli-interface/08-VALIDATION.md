---
phase: 08
slug: cli-interface
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 + pytest-asyncio >=0.23 |
| **Config file** | `packages/conductor-core/pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_cli.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_cli.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | CLI-02 | unit | `pytest tests/test_cli.py::test_build_table -x` | ✅ extend | ⬜ pending |
| 08-01-02 | 01 | 1 | CLI-01 | unit | `pytest tests/test_cli.py::test_run_interactive_routes_input -x` | ✅ extend | ⬜ pending |
| 08-02-01 | 02 | 2 | CLI-03 | unit | `pytest tests/test_cli.py::test_dispatch_cancel -x` | ✅ extend | ⬜ pending |
| 08-02-02 | 02 | 2 | CLI-03 | unit | `pytest tests/test_cli.py::test_dispatch_feedback -x` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Extend `tests/test_cli.py` — add build_table, run_interactive, dispatch_cancel, dispatch_feedback tests

*Existing infrastructure covers pytest framework and asyncio configuration.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live terminal display updates | CLI-02 | Requires real terminal | Run `conductor run "test"` and observe live agent table |
| KeyboardInterrupt cleanup | CLI-01 | Requires signal handling | Ctrl+C during active run, verify clean exit |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
