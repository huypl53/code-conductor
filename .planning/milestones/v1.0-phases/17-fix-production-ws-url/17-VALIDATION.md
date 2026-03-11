---
phase: 17
slug: fix-production-ws-url
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | vitest 4.x |
| **Config file** | `packages/conductor-dashboard/vite.config.ts` |
| **Quick run command** | `cd packages/conductor-dashboard && pnpm test` |
| **Full suite command** | `cd packages/conductor-dashboard && pnpm test` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-dashboard && pnpm test`
- **After every plan wave:** Run `cd packages/conductor-dashboard && pnpm test`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 17-01-01 | 01 | 1 | PKG-02 | unit | `cd packages/conductor-dashboard && pnpm test -- --testPathPattern App.test` | ✅ | ⬜ pending |
| 17-01-02 | 01 | 1 | PKG-02 | unit | `cd packages/conductor-dashboard && pnpm test -- --testPathPattern App.test` | ✅ | ⬜ pending |
| 17-01-03 | 01 | 2 | PKG-02 | integration | Manual: start bin with --backend-url, verify HTML injection | N/A | ⬜ pending |

*Status: ⬜ pending / ✅ green / ❌ red / ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. vitest and test setup already exist in `packages/conductor-dashboard/src/test/setup.ts`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Production WebSocket connects to FastAPI port | PKG-02 | Requires two running servers | 1. Start FastAPI backend: `conductor run --dashboard-port 8000` 2. Start dashboard: `conductor-dashboard --backend-url http://127.0.0.1:8000` 3. Open browser, verify WebSocket connection in Network tab |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
