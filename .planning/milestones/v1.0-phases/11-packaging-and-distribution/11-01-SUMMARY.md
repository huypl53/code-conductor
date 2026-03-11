---
phase: 11-packaging-and-distribution
plan: 01
subsystem: infra
tags: [pypi, npm, packaging, distribution, sirv, hatchling, uv]

requires:
  - phase: 10-dashboard-frontend
    provides: Built dist/ assets for conductor-dashboard to serve via sirv bin script
  - phase: 08-cli-interface
    provides: conductor CLI entry point registered in pyproject.toml [project.scripts]

provides:
  - conductor-ai Python package with full PyPI metadata (name, description, classifiers, license, readme)
  - MIT LICENSE file at repo root
  - packages/conductor-core/README.md with install/usage documentation
  - conductor-dashboard npm package without private flag, with bin/files/prepublishOnly/sirv
  - bin/conductor-dashboard.js executable that serves dist/ via sirv with SPA fallback
  - packages/conductor-dashboard/README.md with install/usage documentation

affects: [publishing workflow, CI/CD release pipeline]

tech-stack:
  added: [sirv ^3.0.0 (production dep for conductor-dashboard)]
  patterns:
    - "uv build to produce wheel named conductor_ai-0.1.0-py3-none-any.whl"
    - "npm pack --dry-run to verify tarball includes bin/ and dist/ entries"
    - "sirv(distDir, { single: true }) for SPA fallback in Node HTTP server"
    - "ES module bin script using import.meta.url for __dirname resolution"

key-files:
  created:
    - LICENSE
    - packages/conductor-core/README.md
    - packages/conductor-dashboard/README.md
    - packages/conductor-dashboard/bin/conductor-dashboard.js
  modified:
    - packages/conductor-core/pyproject.toml
    - packages/conductor-dashboard/package.json

key-decisions:
  - "Package name is conductor-ai (PyPI) but import path remains conductor — documented in README"
  - "sirv (not sirv-cli) used as production dep — bin script uses Node HTTP server API directly"
  - "bin script uses ES module syntax (import.meta.url) matching package.json type: module"
  - "LICENSE holder is 'Conductor Contributors', year 2026"

patterns-established:
  - "Python package: pyproject.toml name field is the PyPI distribution name, packages path in hatch.build.targets.wheel is the import name"
  - "npm bin script: ES module with import.meta.url pattern for __dirname in type:module packages"

requirements-completed: [PKG-01, PKG-02]

duration: 2min
completed: 2026-03-11
---

# Phase 11 Plan 01: Packaging and Distribution — PyPI + npm Metadata Summary

**conductor-ai Python package and conductor-dashboard npm package both configured for public distribution with PyPI classifiers, MIT license, READMEs, and a sirv-based bin CLI script**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-11T19:57:26Z
- **Completed:** 2026-03-11T19:59:29Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Updated `packages/conductor-core/pyproject.toml` with full PyPI metadata: `name = "conductor-ai"`, description, readme, license, authors, classifiers — `uv build` produces `conductor_ai-0.1.0-py3-none-any.whl`
- Created MIT `LICENSE` at repo root (2026, Conductor Contributors) and `packages/conductor-core/README.md` with pip install and CLI usage
- Updated `packages/conductor-dashboard/package.json` (removed `private: true`, added bin/files/prepublishOnly/sirv), created executable `bin/conductor-dashboard.js` and `README.md` — `npm pack --dry-run` confirms bin/ and dist/ included

## Task Commits

Each task was committed atomically:

1. **Task 1: Python package PyPI metadata + LICENSE + README** - `0586383` (feat)
2. **Task 2: npm package distribution config + bin script + README** - `4809d7c` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `packages/conductor-core/pyproject.toml` - Renamed to conductor-ai, added PyPI metadata fields
- `LICENSE` - MIT license, 2026, Conductor Contributors
- `packages/conductor-core/README.md` - PyPI long description with pip install, CLI usage, import path note
- `packages/conductor-dashboard/package.json` - Removed private flag, added bin/files/prepublishOnly/sirv dependency
- `packages/conductor-dashboard/bin/conductor-dashboard.js` - Executable ES module serving dist/ via sirv with SPA fallback
- `packages/conductor-dashboard/README.md` - npm package page with npx usage and backend requirement note

## Decisions Made

- Package import path is still `conductor` (not `conductor-ai`) — documented clearly in the PyPI README to avoid confusion
- Used `sirv` (not `sirv-cli`) as a production dependency; bin script creates a Node HTTP server directly, giving full control over port argument parsing
- bin script uses ES module syntax (`import.meta.url`) to resolve `__dirname`, consistent with `"type": "module"` in package.json

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Both packages are ready to publish:
- `cd packages/conductor-core && uv build && uv publish` — publishes conductor-ai to PyPI
- `cd packages/conductor-dashboard && npm publish` — publishes conductor-dashboard to npm

No blockers. Phase 11 Plan 01 completes the packaging and distribution phase.

---
*Phase: 11-packaging-and-distribution*
*Completed: 2026-03-11*
