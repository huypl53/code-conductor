---
phase: 1
slug: monorepo-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8+ |
| **Config file** | `packages/conductor-core/pyproject.toml` — `[tool.pytest.ini_options]` (Wave 0: create) |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/ -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/ -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | PKG-03 | smoke | `cd packages/conductor-core && uv sync --locked` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | PKG-03 | smoke | `pnpm install --frozen-lockfile` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | PKG-03 | smoke | `cd packages/conductor-core && uv run ruff check .` | ❌ W0 | ⬜ pending |
| 01-01-04 | 01 | 1 | PKG-03 | smoke | `cd packages/conductor-core && uv run pyright` | ❌ W0 | ⬜ pending |
| 01-01-05 | 01 | 1 | PKG-03 | smoke | `cd packages/conductor-core && uv run conductor --help` | ❌ W0 | ⬜ pending |
| 01-01-06 | 01 | 1 | PKG-03 | integration | GitHub Actions — manual verify on push | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `packages/conductor-core/tests/test_cli.py` — smoke test for `conductor --help` (PKG-03)
- [ ] `packages/conductor-core/pyproject.toml` — pytest config section with `--import-mode=importlib`
- [ ] Framework install: `cd packages/conductor-core && uv add --dev pytest` — if not yet in pyproject.toml

*Note: Phase 1 is primarily structural. Most verification is "commands succeed" rather than unit test logic.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI runs both Python and Node.js checks on push | PKG-03 | Requires GitHub Actions runner | Push to branch, verify both jobs appear and pass in Actions tab |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
