# Milestones

## v2.1 UX Polish (Shipped: 2026-03-12)

**Phases completed:** 4 phases, 4 plans, 9 tasks

**Key accomplishments:**
- Auto-focus input on TUI start with crash-safe terminal cleanup (AUTO_FOCUS class variable)
- Borderless content-first design with subtle accent lines (CSS-only, solid at 40% opacity)
- Smooth opacity fade-in animations with CONDUCTOR_NO_ANIMATIONS env var guard
- Ctrl-G external editor integration — $VISUAL/$EDITOR/vim with suspend/resume

**Stats:**
- 23 files changed, 3,597 insertions, 54 deletions
- 20,155 Python LOC total, 663 tests
- Git range: 67133de..83c0120

---

## v1.0 MVP (Shipped: 2026-03-11)

**Phases completed:** 17 phases, 32 plans, 6 tasks

**Key accomplishments:**
- Shared state infrastructure with file-locked `.conductor/state.json` and Pydantic v2 models
- ACP communication layer with permission handling, timeout safe-defaults, and session lifecycle
- Orchestrator that decomposes features, spawns dynamic agent teams, manages dependencies, and reviews output
- CLI interface with Rich live display, intervention commands (cancel, redirect, feedback, pause)
- Web dashboard with real-time WebSocket updates, layered visibility, and browser-based interventions
- Distributable as `pip install conductor-ai` + `npm install -g conductor-dashboard` with getting-started guide

**Stats:**
- 190 commits, 228 files, 10,946 LOC (8,604 Python + 2,342 TypeScript)
- Timeline: 2 days (2026-03-10 → 2026-03-11)
- Audit: 30/30 requirements passed, 17/17 phases complete

---
