---
phase: 11
slug: packaging-and-distribution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8 (Python) + Vitest 4 (Dashboard) |
| **Config file** | `packages/conductor-core/pyproject.toml` + `packages/conductor-dashboard/vite.config.ts` |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/ -x -q` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest tests/ -x && cd ../../packages/conductor-dashboard && npx vitest run` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/ -x -q`
- **After every plan wave:** Run full suite (both packages)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | PKG-01 | integration | `cd packages/conductor-core && uv build && pip install dist/*.whl --dry-run` | ❌ W0 | ⬜ pending |
| 11-01-02 | 01 | 1 | PKG-02 | integration | `cd packages/conductor-dashboard && npm pack --dry-run` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 2 | PKG-04 | manual | Review getting-started guide completeness | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers pytest and vitest frameworks. No new test dependencies needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| pip install in fresh venv works | PKG-01 | Requires fresh environment | `python -m venv /tmp/test-env && pip install dist/*.whl` |
| npm install -g works | PKG-02 | Requires global install | `npm install -g ./packages/conductor-dashboard/` |
| Getting-started guide is followable | PKG-04 | Requires human reading | Follow guide from scratch in new directory |
| Both packages have correct version metadata | PKG-01, PKG-02 | Requires registry check | Inspect `pip show conductor-ai` and `npm info conductor-dashboard` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
