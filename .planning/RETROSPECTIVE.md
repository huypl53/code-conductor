# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-11
**Phases:** 17 | **Plans:** 32 | **Commits:** 190

### What Was Built
- Multi-agent orchestration framework with ACP-based communication (Python core)
- Shared state infrastructure with file-locked `.conductor/state.json` and Pydantic v2 models
- Orchestrator that decomposes features, spawns dynamic agent teams, manages dependencies, reviews output
- CLI interface with Rich live display and intervention commands (cancel, redirect, feedback, pause)
- Web dashboard with real-time WebSocket updates, layered visibility, and browser-based interventions
- Distribution as `pip install conductor-ai` + `npm install -g conductor-dashboard` with getting-started guide

### What Worked
- Bottom-up build order (state → ACP → orchestrator → CLI → dashboard → packaging) — each phase built on solid foundations with no circular dependencies
- TDD approach across core phases — caught contract mismatches early (e.g., StrEnum serialization, async patterns)
- Milestone audit after Phase 11 caught 6 real integration gaps before shipping — phases 12-17 closed all of them
- Phase-per-gap closure approach was efficient — small focused phases with clear success criteria

### What Was Inefficient
- Phase 5 and 9 roadmap status showed "In Progress" even though all plans were complete — stale roadmap metadata not auto-updated
- STATE.md progress metrics fell behind after Phase 2 — manual tracking doesn't scale across 17 phases
- ~10 SUMMARY frontmatter files missing `requirements_completed` fields — inconsistent metadata discipline
- Some phases had extremely high commit counts per plan (Phase 7 P02: 132, Phase 9 P01: 87, Phase 17 P01: 126) — likely excessive iteration on complex async code

### Patterns Established
- StrEnum + ConfigDict(use_enum_values=True) as standard for all Pydantic models with JSON serialization
- asyncio.to_thread for all synchronous I/O inside async callbacks (never block the event loop)
- Watch parent directory (not file directly) for file-system change detection with atomic writes
- Exception hierarchy per subsystem (StateError, ACPError, OrchestratorError) with unified catch patterns
- TYPE_CHECKING guard for circular import prevention while preserving type annotations
- filelock at `path.with_suffix('.json.lock')` as standard pattern for all JSON persistence

### Key Lessons
1. Milestone audit before shipping is invaluable — it caught cancel/redirect signature mismatches, unwired escalation router, and dashboard type errors that unit tests missed
2. Gap closure phases (12-17) were the most efficient phases — focused scope, clear contracts, fast execution
3. Bottom-up architecture worked perfectly for this project — no phase ever needed to refactor a lower layer
4. Session persistence and async patterns (Phase 7) were the hardest to get right — budget extra time for concurrent code

### Cost Observations
- Model mix: balanced profile (opus for planning, sonnet for execution, haiku for research)
- Sessions: ~20+ across 2 days
- Notable: 17 phases in 2 days is high velocity — gap closure phases (12-17) averaged <30 minutes each

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Commits | Phases | Key Change |
|-----------|---------|--------|------------|
| v1.0 | 190 | 17 | Initial build — bottom-up architecture with milestone audit |

### Cumulative Quality

| Milestone | LOC | Languages | Audit Score |
|-----------|-----|-----------|-------------|
| v1.0 | 10,946 | Python + TypeScript | 30/30 requirements |

### Top Lessons (Verified Across Milestones)

1. Milestone audit catches integration gaps that unit tests miss — always audit before shipping
2. Small, focused gap-closure phases are more efficient than large feature phases
