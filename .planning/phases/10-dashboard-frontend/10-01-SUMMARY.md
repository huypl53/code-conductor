---
phase: 10-dashboard-frontend
plan: 01
subsystem: ui
tags: [vitest, react-testing-library, typescript, websocket, fastapi, vite]

requires:
  - phase: 09-dashboard-backend
    provides: FastAPI server with WebSocket streaming and state watching

provides:
  - Vitest test infrastructure with jsdom and jest-dom matchers for conductor-dashboard
  - TypeScript types mirroring all backend Pydantic models (Task, AgentRecord, ConductorState, DeltaEvent, InterventionCommand, etc.)
  - parseMessage/serializeIntervention utilities for WebSocket message handling
  - Vite dev server proxy for /state and /ws
  - Backend WebSocket endpoint extended to handle cancel/feedback/redirect intervention commands

affects:
  - 10-02, 10-03, 10-04 (all depend on these types and test infra)

tech-stack:
  added:
    - vitest 4.x (test runner)
    - "@testing-library/react 16.x"
    - "@testing-library/jest-dom 6.x"
    - "@testing-library/user-event 14.x"
    - jsdom 28.x
    - sonner 2.x (toast notifications, runtime dep)
  patterns:
    - "defineConfig from vitest/config to support test: {} block in vite.config.ts"
    - "TYPE_CHECKING guard for Orchestrator import in server.py to avoid circular imports"
    - "AsyncMock orchestrator in WebSocket integration tests using Starlette TestClient"

key-files:
  created:
    - packages/conductor-dashboard/src/test/setup.ts
    - packages/conductor-dashboard/src/types/conductor.ts
    - packages/conductor-dashboard/src/types/conductor.test.ts
    - packages/conductor-dashboard/src/lib/messages.ts
    - packages/conductor-dashboard/src/lib/messages.test.ts
    - packages/conductor-core/tests/dashboard/__init__.py
    - packages/conductor-core/tests/dashboard/test_server_interventions.py
  modified:
    - packages/conductor-dashboard/package.json
    - packages/conductor-dashboard/vite.config.ts
    - packages/conductor-core/src/conductor/dashboard/server.py
    - packages/conductor-core/src/conductor/cli/commands/run.py

key-decisions:
  - "Use defineConfig from vitest/config (not vite) to enable test: {} block without TypeScript errors"
  - "TYPE_CHECKING guard for Orchestrator import in server.py avoids circular import while preserving type annotations"
  - "handle_intervention uses try/except around orchestrator calls to prevent WebSocket disconnection on errors"
  - "Detect snapshot vs delta in parseMessage by checking version field (snapshot) vs type field (delta)"

patterns-established:
  - "All TypeScript types use string literal unions not enums — matches StrEnum backend serialization exactly"
  - "InterventionCommand.message is optional — cancel action doesn't require a message"
  - "Backend intervention handler returns silently on malformed JSON or missing required fields"

requirements-completed: [DASH-06]

duration: 5min
completed: 2026-03-10
---

# Phase 10 Plan 01: Foundation — Test Infrastructure, Types, and Backend Interventions Summary

**Vitest jsdom test setup, TypeScript types mirroring all backend Pydantic models, WebSocket message utilities, Vite proxy, and backend cancel/feedback/redirect intervention routing**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-10T19:21:46Z
- **Completed:** 2026-03-10T19:26:59Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Installed vitest, @testing-library/react, jest-dom, jsdom, sonner; configured Vitest with jsdom environment and jest-dom setup file
- Created complete TypeScript type definitions mirroring all backend Pydantic models (TaskStatus, ReviewStatus, AgentStatus, Task, AgentRecord, Dependency, ConductorState, EventType, DeltaEvent, InterventionCommand, ExpansionLevel, DashboardState)
- Implemented parseMessage (snapshot/delta/error discrimination) and serializeIntervention utilities with 22 passing tests
- Extended backend create_app() with optional orchestrator parameter; WebSocket endpoint routes cancel/feedback/redirect commands to orchestrator methods; malformed JSON silently ignored
- Updated run.py to pass orchestrator to create_app; 6 new backend intervention tests + 6 existing tests all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Install deps, configure Vitest, create TypeScript types and message utilities** - `d378f1a` (feat)
2. **Task 2: Extend backend WebSocket to handle intervention commands** - `c89dd1e` (feat)

## Files Created/Modified

- `packages/conductor-dashboard/package.json` - Added sonner dep, vitest/testing-library devDeps, test/test:watch scripts
- `packages/conductor-dashboard/vite.config.ts` - Added test config (jsdom, globals, setup) and /state, /ws proxy
- `packages/conductor-dashboard/src/test/setup.ts` - jest-dom vitest import
- `packages/conductor-dashboard/src/types/conductor.ts` - All TypeScript types mirroring backend Pydantic models
- `packages/conductor-dashboard/src/types/conductor.test.ts` - 12 type shape/compilation tests
- `packages/conductor-dashboard/src/lib/messages.ts` - parseMessage and serializeIntervention utilities
- `packages/conductor-dashboard/src/lib/messages.test.ts` - 10 message parsing/serialization tests
- `packages/conductor-core/src/conductor/dashboard/server.py` - Added orchestrator param, handle_intervention function, WebSocket routing
- `packages/conductor-core/src/conductor/cli/commands/run.py` - Pass orchestrator to create_app
- `packages/conductor-core/tests/dashboard/__init__.py` - Package init
- `packages/conductor-core/tests/dashboard/test_server_interventions.py` - 6 intervention command tests

## Decisions Made

- Used `defineConfig` from `vitest/config` instead of `vite` — only way to add `test: {}` block without TypeScript errors in Vitest 4.x
- Used `TYPE_CHECKING` guard for `Orchestrator` import in server.py — prevents circular import while preserving type annotations
- `handle_intervention` wraps orchestrator calls in try/except — WebSocket connection stays alive even if orchestrator method throws

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed vite.config.ts TypeScript error for `test` property**
- **Found during:** Task 1 (TypeScript compilation verification)
- **Issue:** `defineConfig` from `vite` doesn't include vitest's `test` property in its types, causing TS2769 error
- **Fix:** Changed import to `defineConfig` from `vitest/config` which extends Vite's config with test types
- **Files modified:** packages/conductor-dashboard/vite.config.ts
- **Verification:** `npx tsc -b --noEmit` passes clean
- **Committed in:** d378f1a (Task 1 commit)

**2. [Rule 1 - Bug] Fixed TS2532 possibly undefined index access in messages.test.ts**
- **Found during:** Task 1 (TypeScript compilation verification)
- **Issue:** `result.state.tasks[0].id` flagged as possibly undefined; TypeScript strict mode requires optional chaining
- **Fix:** Changed to `result.state.tasks[0]?.id`
- **Files modified:** packages/conductor-dashboard/src/lib/messages.test.ts
- **Verification:** `npx tsc -b --noEmit` passes clean
- **Committed in:** d378f1a (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2x Rule 1 - Bug)
**Impact on plan:** Both fixes required for TypeScript strictness. No scope creep.

## Issues Encountered

None — all tests passed on first implementation attempt.

## Next Phase Readiness

- Test infrastructure ready for all subsequent dashboard component plans
- TypeScript types are the authoritative frontend source of truth for all backend data shapes
- Backend intervention endpoint ready to receive dashboard user actions
- Vite proxy configured so `npm run dev` works against running backend on :8000

---
*Phase: 10-dashboard-frontend*
*Completed: 2026-03-10*
