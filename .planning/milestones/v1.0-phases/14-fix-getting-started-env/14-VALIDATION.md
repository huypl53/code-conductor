---
phase: 14
slug: fix-getting-started-env
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-11
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | grep-based doc validation (no test framework needed) |
| **Config file** | none |
| **Quick run command** | `grep -n "\.env" docs/GETTING-STARTED.md` |
| **Full suite command** | `grep -rn "automatically reads.*\.env\|auto.*load.*\.env\|reads \.env" docs/` |
| **Estimated runtime** | ~1 second |

---

## Sampling Rate

- **After every task commit:** Run `grep -n "\.env" docs/GETTING-STARTED.md`
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must show no false claims
- **Max feedback latency:** 1 second

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | PKG-04 | grep | `grep -c "automatically reads.*\.env\|auto.*load.*\.env" docs/GETTING-STARTED.md` | ✅ | ✅ green |

*Status: ✅ green · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. No test framework needed — grep-based validation suffices for documentation accuracy.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Guide reads coherently after edits | PKG-04 | Prose quality is subjective | Read Configuration and Troubleshooting sections end-to-end |

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

PKG-04 grep validation: zero .env references remain, export instructions present at correct locations.
