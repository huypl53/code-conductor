---
phase: 01-monorepo-foundation
plan: "01"
subsystem: infra
tags: [uv, pnpm, python, hatchling, ruff, pyright, pytest, cli, argparse, monorepo]

# Dependency graph
requires: []
provides:
  - uv virtual workspace root (pyproject.toml with package=false)
  - pnpm workspace definition (pnpm-workspace.yaml)
  - root Makefile with lint/test/build/format targets
  - packages/conductor-core Python package with conductor CLI entry point
  - Python quality toolchain: ruff lint/format, pyright type checking, pytest
  - conductor --help CLI with argparse, version string in __init__.py
  - Domain subpackage scaffolds: state, acp, orchestrator
affects: [02-dashboard-scaffold, 03-acp-layer, 04-orchestrator-core, 05-shared-state, 08-cli-interface]

# Tech tracking
tech-stack:
  added:
    - uv (Python package/workspace manager)
    - pnpm 10.25.0 (Node.js workspace manager)
    - hatchling (Python build backend)
    - ruff 0.15.5 (Python linter and formatter)
    - pyright 1.1.408 (Python type checker)
    - pytest 9.0.2 (Python test framework)
  patterns:
    - uv workspace with explicit member list (not glob) to avoid including Node packages
    - hatchling src-layout build pattern (src/conductor/)
    - CLI entry point via pyproject.toml [project.scripts]
    - Domain subpackages as __init__.py-only scaffolds

key-files:
  created:
    - pyproject.toml
    - pnpm-workspace.yaml
    - package.json
    - Makefile
    - .gitignore
    - uv.lock
    - packages/conductor-core/pyproject.toml
    - packages/conductor-core/src/conductor/__init__.py
    - packages/conductor-core/src/conductor/cli/__init__.py
    - packages/conductor-core/src/conductor/state/__init__.py
    - packages/conductor-core/src/conductor/acp/__init__.py
    - packages/conductor-core/src/conductor/orchestrator/__init__.py
    - packages/conductor-core/tests/test_cli.py
  modified: []

key-decisions:
  - "uv workspace members set to explicit list [packages/conductor-core] instead of glob packages/* to avoid including the Node.js conductor-dashboard package"
  - "ruff added to dev dependency-groups so it is available via uv run ruff from within conductor-core"
  - "pytest cwd fix: test_conductor_help removes cwd arg since tests run from within packages/conductor-core"

patterns-established:
  - "Python src-layout: all Python source under packages/conductor-core/src/conductor/"
  - "CLI entry point: pyproject.toml [project.scripts] conductor = conductor.cli:main"
  - "Domain modules are stub __init__.py files to be filled in later phases"

requirements-completed: [PKG-03]

# Metrics
duration: 2min
completed: 2026-03-10
---

# Phase 1 Plan 01: Monorepo Root Configuration and Python Package Scaffold Summary

**uv+pnpm monorepo workspace with conductor-core Python package, argparse CLI entry point, and passing ruff/pyright/pytest quality gates**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-10T11:43:15Z
- **Completed:** 2026-03-10T11:45:04Z
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments

- Root workspace configured: uv virtual workspace + pnpm workspace + Makefile + .gitignore
- Python package conductor-core with hatchling src-layout and CLI entry point `conductor --help`
- All quality checks pass: ruff lint, ruff format, pyright type checking, pytest (2 tests)
- Domain subpackages scaffolded: state, acp, orchestrator (ready for later phases)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create monorepo root configuration files** - `04059e6` (chore)
2. **Task 2: Create Python package scaffold with CLI entry point and tests** - `d24f2c8` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `pyproject.toml` - uv virtual workspace root, name=conductor-workspace, package=false, members=[packages/conductor-core]
- `pnpm-workspace.yaml` - pnpm workspace packages/*
- `package.json` - private root with pnpm@10.25.0 and dashboard script delegation
- `Makefile` - lint/test/build/format targets for both Python and Node packages
- `.gitignore` - Python, Node, runtime (.conductor/), IDE entries
- `uv.lock` - lockfile for reproducible Python installs
- `packages/conductor-core/pyproject.toml` - full package config: hatchling build, ruff, pyright, pytest, CLI entry point
- `packages/conductor-core/src/conductor/__init__.py` - version string __version__ = "0.1.0"
- `packages/conductor-core/src/conductor/cli/__init__.py` - argparse CLI with main() entry point
- `packages/conductor-core/src/conductor/state/__init__.py` - stub module
- `packages/conductor-core/src/conductor/acp/__init__.py` - stub module
- `packages/conductor-core/src/conductor/orchestrator/__init__.py` - stub module
- `packages/conductor-core/tests/test_cli.py` - test_conductor_help() and test_conductor_version()

## Decisions Made

- **uv workspace glob vs explicit:** Changed root pyproject.toml `members = ["packages/*"]` to `members = ["packages/conductor-core"]` because uv tried to include conductor-dashboard as a Python workspace member (it has no pyproject.toml). Explicit list is the correct approach for mixed-language monorepos.
- **ruff in dev dependencies:** Added ruff to conductor-core's dev dependency-groups so `uv run ruff` works from within the package without a separate global install.
- **pytest cwd fix:** test_conductor_help() had `cwd="packages/conductor-core"` which is a relative path that doesn't exist when tests run from within that directory — removed the cwd argument.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed uv workspace glob to exclude Node.js package**
- **Found during:** Task 2 (uv sync)
- **Issue:** Root pyproject.toml `members = ["packages/*"]` caused uv to try to find pyproject.toml in conductor-dashboard (Node.js package), failing with "Workspace member is missing a pyproject.toml"
- **Fix:** Changed to explicit `members = ["packages/conductor-core"]`
- **Files modified:** pyproject.toml
- **Verification:** uv sync succeeded after change
- **Committed in:** d24f2c8 (Task 2 commit)

**2. [Rule 1 - Bug] Fixed test_conductor_help cwd path**
- **Found during:** Task 2 (pytest)
- **Issue:** `cwd="packages/conductor-core"` is a relative path that resolves from the pytest process cwd (already inside packages/conductor-core), causing FileNotFoundError
- **Fix:** Removed cwd argument — uv run works from current directory which is already the package
- **Files modified:** packages/conductor-core/tests/test_cli.py
- **Verification:** pytest -x passes with 2 tests
- **Committed in:** d24f2c8 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - bug fixes)
**Impact on plan:** Both fixes essential for uv sync and tests to work. No scope creep.

## Issues Encountered

- uv 0.x workspace member discovery requires explicit paths for mixed Python/Node monorepos

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Python monorepo foundation complete, ready for Plan 02 (dashboard scaffold)
- uv sync, conductor --help, ruff, pyright, pytest all passing
- Domain subpackages (state, acp, orchestrator) scaffolded as stubs for later phases
- Root Makefile lint/test targets work for Python; dashboard targets require Plan 02

---
*Phase: 01-monorepo-foundation*
*Completed: 2026-03-10*
