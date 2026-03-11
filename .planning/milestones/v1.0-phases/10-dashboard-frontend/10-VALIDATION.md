---
phase: 10
slug: dashboard-frontend
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Vitest 4.0 + React Testing Library 16.3 |
| **Config file** | `packages/conductor-dashboard/vite.config.ts` `test` section |
| **Quick run command** | `cd packages/conductor-dashboard && npx vitest run` |
| **Full suite command** | `cd packages/conductor-dashboard && npx vitest run` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-dashboard && npx vitest run`
- **After every plan wave:** Run `cd packages/conductor-dashboard && npx vitest run`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 0 | infra | setup | `npx vitest run src/types/conductor.test.ts` | ✅ | ✅ green |
| 10-02-01 | 02 | 1 | DASH-01 | unit | `npx vitest run src/hooks/useConductorSocket.test.ts` | ✅ | ✅ green |
| 10-02-02 | 02 | 1 | DASH-01 | unit | `npx vitest run src/components/AgentCard.test.tsx` | ✅ | ✅ green |
| 10-02-03 | 02 | 1 | DASH-05 | unit | `npx vitest run src/components/AgentCard.test.tsx` | ✅ | ✅ green |
| 10-03-01 | 03 | 2 | DASH-02 | unit | `npx vitest run src/components/AgentCard.test.tsx` | ✅ | ✅ green |
| 10-03-02 | 03 | 2 | DASH-03 | unit | `npx vitest run src/components/LiveStream.test.tsx` | ✅ | ✅ green |
| 10-03-03 | 03 | 2 | DASH-06 | unit | `npx vitest run src/components/InterventionPanel.test.tsx` | ✅ | ✅ green |

*Status: ✅ green · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Install: `cd packages/conductor-dashboard && npm install sonner && npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom`
- [ ] `vite.config.ts` — add test configuration (globals, jsdom, setupFiles)
- [ ] `src/test/setup.ts` — jest-dom matcher import
- [ ] `package.json` — add "test" script
- [ ] `src/types/conductor.ts` — TypeScript types mirroring backend models

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual layout at 5 agents | DASH-01 | Requires visual inspection | Start conductor with 5 agents, open dashboard, verify no scrolling needed |
| Smooth expand/collapse animation | DASH-05 | Requires visual inspection | Click agent cards, verify smooth transitions |
| Toast notifications appear correctly | DASH-04 | Requires running system | Trigger task completion/failure, verify toast appears |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-03-11

## Validation Audit 2026-03-11
| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All DASH-01/02/03/05/06 tests green: 10 frontend test files (81 tests).
