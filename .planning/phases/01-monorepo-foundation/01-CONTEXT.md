# Phase 1: Monorepo Foundation - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Python + Node.js monorepo scaffold with CI, linting, and project structure. A developer can clone the repo, install dependencies, and confirm both sides work. No application logic — pure infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Directory layout
- `packages/` directory pattern: `packages/conductor-core/` (Python) + `packages/conductor-dashboard/` (Node.js)
- Shared config and scripts at repo root: root `pyproject.toml` (uv workspace), root `package.json` (pnpm workspace), `.github/`, `scripts/`
- Root-level Makefile for unified dev commands (`make lint`, `make test`, `make build`) delegating to both packages
- `.conductor/` runtime directory created in the target repo root at runtime (like `.git/`), gitignored

### Python package structure
- Domain-based subpackages: `conductor.state`, `conductor.acp`, `conductor.orchestrator`, `conductor.cli`
- `src/conductor/` layout inside `packages/conductor-core/`
- Python 3.12+ minimum
- uv for package management
- Ruff for both linting and formatting
- Pyright for type checking
- pytest for testing

### Dashboard scaffolding
- Vite + React (SPA, no SSR needed)
- Tailwind CSS for styling
- TypeScript strict mode from day one
- Biome for linting and formatting

### CI and quality gates
- GitHub Actions, single `ci.yml` workflow with parallel jobs for Python and Node.js
- Triggers on push to main + all PRs targeting main
- Python job: Ruff lint, Ruff format check, Pyright type check, pytest
- Dashboard job: Biome check, tsc --noEmit

### Claude's Discretion
- Exact Ruff rule configuration
- Pyright strictness level details
- Biome rule configuration
- Makefile target details beyond lint/test/build
- Python dev dependency versions
- Node.js dev dependency versions

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code

### Established Patterns
- None yet — this phase establishes the patterns

### Integration Points
- `conductor --help` CLI entry point via pyproject.toml `[project.scripts]`
- uv workspace root at repo root linking to `packages/conductor-core`
- pnpm workspace root at repo root linking to `packages/conductor-dashboard`

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches for monorepo scaffolding.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-monorepo-foundation*
*Context gathered: 2026-03-10*
