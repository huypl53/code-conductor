---
phase: 34
slug: rich-output
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 34 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio |
| **Config file** | packages/conductor-core/pyproject.toml |
| **Quick run command** | `cd packages/conductor-core && uv run pytest tests/test_tui_rich_output.py -x` |
| **Full suite command** | `cd packages/conductor-core && uv run pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd packages/conductor-core && uv run pytest tests/test_tui_rich_output.py -x`
- **After every plan wave:** Run `cd packages/conductor-core && uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 34-01-01 | 01 | 1 | TRNS-03 | unit/headless | `pytest tests/test_tui_rich_output.py::test_code_fence_has_spans -x` | ❌ W0 | ⬜ pending |
| 34-01-02 | 01 | 1 | TRNS-04 | unit/headless | `pytest tests/test_tui_rich_output.py::test_markdown_elements -x` | ❌ W0 | ⬜ pending |
| 34-01-03 | 01 | 1 | TRNS-05 | unit/headless | `pytest tests/test_tui_rich_output.py::test_diff_fence_colors -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tui_rich_output.py` — stubs for TRNS-03, TRNS-04, TRNS-05
- [ ] `packages/conductor-core/src/conductor/tui/widgets/rich_markdown.py` — DiffHighlightTheme, DiffAwareFence, RichMarkdown

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Visual appearance of syntax colors | TRNS-03 | Headless tests verify spans exist, not visual color | Run conductor, ask for Python code, verify colorized |
| Visual diff colors (green/red) | TRNS-05 | Headless tests verify styles exist, not rendered color | Run conductor, trigger diff output, verify colors |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
