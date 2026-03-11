# Phase 1: Monorepo Foundation - Research

**Researched:** 2026-03-10
**Domain:** Python/Node.js monorepo scaffolding (uv + pnpm), CI infrastructure
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Directory layout
- `packages/` directory pattern: `packages/conductor-core/` (Python) + `packages/conductor-dashboard/` (Node.js)
- Shared config and scripts at repo root: root `pyproject.toml` (uv workspace), root `package.json` (pnpm workspace), `.github/`, `scripts/`
- Root-level Makefile for unified dev commands (`make lint`, `make test`, `make build`) delegating to both packages
- `.conductor/` runtime directory created in the target repo root at runtime (like `.git/`), gitignored

#### Python package structure
- Domain-based subpackages: `conductor.state`, `conductor.acp`, `conductor.orchestrator`, `conductor.cli`
- `src/conductor/` layout inside `packages/conductor-core/`
- Python 3.12+ minimum
- uv for package management
- Ruff for both linting and formatting
- Pyright for type checking
- pytest for testing

#### Dashboard scaffolding
- Vite + React (SPA, no SSR needed)
- Tailwind CSS for styling
- TypeScript strict mode from day one
- Biome for linting and formatting

#### CI and quality gates
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

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PKG-03 | Monorepo structure with Python core + Node.js dashboard | uv workspace (root pyproject.toml) + pnpm workspace (pnpm-workspace.yaml) establishes the dual-runtime monorepo structure |
</phase_requirements>

---

## Summary

This phase establishes a hybrid Python + Node.js monorepo using uv workspaces for the Python side and pnpm workspaces for the Node.js side. Both tools have first-class workspace support and are the current standard for their respective ecosystems in 2026. The two workspace systems are independent — they do not need to know about each other, and a root-level Makefile acts as the unified command surface.

The main technical surface areas are: (1) uv workspace root configuration with a virtual root `pyproject.toml`, (2) pnpm workspace configuration with `pnpm-workspace.yaml`, (3) the src layout for the Python package with `[project.scripts]` CLI entry point, (4) Vite+React+Tailwind v4 scaffolding for the dashboard, and (5) a GitHub Actions workflow with two parallel jobs sharing no dependencies.

The most important pitfall to avoid is the uv workspace naming conflict: the root `pyproject.toml` must have a project name distinct from any member package. A root named `conductor-workspace` and a member named `conductor-core` is fine; naming both `conductor` causes `uv sync` to fail.

**Primary recommendation:** Use a virtual uv workspace root (`package = false`) with `packages/*` member glob, and a `pnpm-workspace.yaml` file pointing to `packages/conductor-dashboard`. Configure all quality tools in the member's own `pyproject.toml` / `biome.json`. The root orchestrates via Makefile.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| uv | latest (0.5+) | Python package/env management, workspace support | Official Astral tool, replaces pip/poetry/pyenv, fastest resolver |
| pnpm | 9+ | Node.js package management with workspaces | 60-80% less disk vs npm, strict dependency isolation, workspace protocol |
| Ruff | 0.9+ | Python linting + formatting (replaces flake8+black+isort) | 100x faster than flake8, single tool for lint+format, Astral ecosystem |
| Pyright | 1.1.390+ | Python static type checking | Fastest Python type checker, strict mode, used by VS Code Pylance |
| pytest | 8+ | Python test runner | De facto standard, uv-native, best ecosystem |
| Biome | 1.9+ | TypeScript/JS linting + formatting (replaces ESLint+Prettier) | Single tool for lint+format, written in Rust, fast |
| Vite | 6+ | Frontend build tool + dev server | Fastest HMR, native ESM, React template maintained by Vite team |
| React | 19+ | UI library | Project decision |
| Tailwind CSS | 4+ | Utility-first CSS | Released Jan 2025, Vite plugin eliminates PostCSS config |
| TypeScript | 5.7+ | Type-safe JavaScript | Bundled with Vite react-ts template |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| @tailwindcss/vite | 4+ | Tailwind v4 Vite plugin | Required for Tailwind v4 with Vite (replaces PostCSS) |
| astral-sh/setup-uv | v7 | GitHub Actions action for uv | All Python CI jobs |
| actions/setup-node | v4 | GitHub Actions action for Node.js | All Node.js CI jobs |
| pnpm/action-setup | v4 | GitHub Actions action for pnpm | All pnpm CI jobs |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Ruff (lint+format) | flake8 + black + isort separately | Ruff is strictly superior — faster, fewer tools to configure, same rules |
| Biome (lint+format) | ESLint + Prettier separately | Biome is faster and simpler; ESLint has larger plugin ecosystem but unnecessary here |
| Tailwind v4 @tailwindcss/vite | Tailwind v3 + PostCSS | v4 has no tailwind.config.js needed, @import "tailwindcss" in CSS is simpler |
| uv workspace | Poetry workspaces or pip + virtualenvs | uv is 10-100x faster, native workspace support, lockfile included |

**Installation:**

```bash
# Python side (inside packages/conductor-core)
uv sync

# Node side (inside packages/conductor-dashboard or repo root)
pnpm install
```

---

## Architecture Patterns

### Recommended Project Structure

```
/                                   # repo root
├── pyproject.toml                  # uv workspace root (virtual, package=false)
├── uv.lock                         # single uv lockfile for all Python packages
├── pnpm-workspace.yaml             # pnpm workspace definition
├── package.json                    # root package.json (private: true, workspace scripts)
├── pnpm-lock.yaml                  # single pnpm lockfile
├── Makefile                        # unified dev commands delegating to both sides
├── .github/
│   └── workflows/
│       └── ci.yml                  # single workflow, parallel Python + Node jobs
├── scripts/                        # shared scripts (e.g., dev setup helpers)
├── packages/
│   ├── conductor-core/             # Python package
│   │   ├── pyproject.toml          # package config (name=conductor-core)
│   │   ├── src/
│   │   │   └── conductor/          # package root
│   │   │       ├── __init__.py
│   │   │       ├── cli/
│   │   │       │   └── __init__.py
│   │   │       ├── state/
│   │   │       │   └── __init__.py
│   │   │       ├── acp/
│   │   │       │   └── __init__.py
│   │   │       └── orchestrator/
│   │   │           └── __init__.py
│   │   └── tests/
│   │       └── test_cli.py
│   └── conductor-dashboard/        # Node.js package
│       ├── package.json            # name=conductor-dashboard
│       ├── biome.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           └── index.css           # @import "tailwindcss";
```

### Pattern 1: uv Virtual Workspace Root

**What:** The repo root has a `pyproject.toml` with `package = false` (virtual root). It defines the workspace members but is not itself an installable package.

**When to use:** When the repo root is just a coordinator and all real packages live in `packages/`.

**Example:**

```toml
# /pyproject.toml  (workspace root - virtual, not installable)
[project]
name = "conductor-workspace"        # MUST differ from all member package names
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv]
package = false                     # virtual root: don't install me

[tool.uv.workspace]
members = ["packages/*"]            # include all packages/ subdirectories

[dependency-groups]                 # PEP 735 - dev deps at workspace level
dev = []
```

```toml
# /packages/conductor-core/pyproject.toml  (actual installable package)
[project]
name = "conductor-core"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
conductor = "conductor.cli:main"    # entry point for `conductor --help`

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/conductor"]

[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]   # E/F=pycodestyle+pyflakes, I=isort, B=bugbear, UP=pyupgrade
ignore = []

[tool.ruff.format]
quote-style = "double"

[tool.pyright]
include = ["src"]
pythonVersion = "3.12"
typeCheckingMode = "standard"       # "strict" available; start standard, escalate as needed

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = ["--import-mode=importlib"]  # prevents name collision in multi-package workspace
```

### Pattern 2: pnpm Workspace Root

**What:** A `pnpm-workspace.yaml` at the repo root defines which directories are workspace packages.

**Example:**

```yaml
# /pnpm-workspace.yaml
packages:
  - "packages/*"
```

```json
// /package.json  (root, private)
{
  "name": "conductor-monorepo",
  "private": true,
  "scripts": {
    "lint": "pnpm --filter conductor-dashboard biome check ./src",
    "typecheck": "pnpm --filter conductor-dashboard tsc --noEmit",
    "build": "pnpm --filter conductor-dashboard build"
  },
  "packageManager": "pnpm@9.x.x"
}
```

### Pattern 3: CLI Entry Point

**What:** A Python function exposed as a command via `[project.scripts]` in pyproject.toml. After `uv sync`, the `conductor` command is available in the virtual environment.

**Example:**

```python
# src/conductor/cli/__init__.py
def main() -> None:
    """Conductor CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(
        prog="conductor",
        description="Conductor: AI agent orchestration"
    )
    # Phase 1: just --help works
    parser.parse_args()
```

### Pattern 4: Tailwind v4 with Vite

**What:** Tailwind v4 uses a first-party Vite plugin. No `tailwind.config.js`, no PostCSS config. Just install and import.

**Example:**

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
});
```

```css
/* src/index.css */
@import "tailwindcss";
```

### Pattern 5: GitHub Actions Parallel CI

**What:** Two jobs with no `needs:` dependency run in parallel by default in GitHub Actions.

**Example:**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  python:
    name: Python checks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - name: Install dependencies
        run: uv sync --locked --all-extras --dev
        working-directory: packages/conductor-core
      - name: Lint (ruff)
        run: uv run ruff check .
        working-directory: packages/conductor-core
      - name: Format check (ruff)
        run: uv run ruff format --check .
        working-directory: packages/conductor-core
      - name: Type check (pyright)
        run: uv run pyright
        working-directory: packages/conductor-core
      - name: Tests (pytest)
        run: uv run pytest
        working-directory: packages/conductor-core

  dashboard:
    name: Dashboard checks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 9
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: "pnpm"
      - name: Install dependencies
        run: pnpm install --frozen-lockfile
      - name: Biome check
        run: pnpm --filter conductor-dashboard exec biome check ./src
      - name: TypeScript check
        run: pnpm --filter conductor-dashboard exec tsc --noEmit
```

### Anti-Patterns to Avoid

- **Root package name matching member package name:** If root `pyproject.toml` has `name = "conductor"` and a member also has `name = "conductor"`, `uv sync` fails with "Two workspace members are both named". Name the root `conductor-workspace`.
- **`__init__.py` in test directories:** In a uv workspace with multiple packages, adding `__init__.py` to `tests/` can cause pytest to silently run wrong tests. Use `--import-mode=importlib` instead.
- **`npm install` instead of `pnpm install`:** In a pnpm workspace, running `npm install` ignores the workspace protocol and can create inconsistent `node_modules`. Always use `pnpm install`.
- **Inter-package dep without `[tool.uv.sources]`:** If a future Python package depends on another workspace member, declaring it in `[project.dependencies]` alone is insufficient — also declare `member = { workspace = true }` in `[tool.uv.sources]`.
- **Tailwind v4 with PostCSS config:** Tailwind v4 uses the `@tailwindcss/vite` plugin, not PostCSS. Creating a `postcss.config.js` is unnecessary and can conflict.
- **Pinning `setup-uv` without a version:** Official docs recommend pinning to a specific uv version in CI to ensure reproducibility: `astral-sh/setup-uv@v7` with `version: "0.5.x"`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Python import sorting | Custom import organizer | Ruff `I` rules (isort-compatible) | Built into ruff, zero overhead, auto-fixable |
| Python formatting | Custom formatter | `ruff format` | Black-compatible, part of existing toolchain |
| TypeScript formatting | Custom prettier rules | Biome formatter | Single tool for lint+format, faster |
| Dependency caching in CI | Custom cache keys | `enable-cache: true` in setup-uv, `cache: pnpm` in setup-node | Official cache integration handles invalidation |
| CLI arg parsing | Custom argv parser | Python stdlib `argparse` (or `click` later) | `argparse` is zero-dep and sufficient for Phase 1 `--help` |

**Key insight:** Both Ruff and Biome replace multiple tools with one binary. Configuring separate tools (flake8, black, isort, ESLint, Prettier) creates version conflicts, slower CI, and multiple config files for no benefit.

---

## Common Pitfalls

### Pitfall 1: uv Workspace Root Name Conflict

**What goes wrong:** `uv sync` fails with "Two workspace members are both named X" even when the root has `package = false`.

**Why it happens:** uv still registers the `[project] name` from the workspace root as a workspace identity, even though it won't be installed. If any member shares that name, uv sees a collision.

**How to avoid:** Name the root distinctly: `conductor-workspace`, not `conductor` or `conductor-core`.

**Warning signs:** Any `uv sync` failure mentioning "Two workspace members".

### Pitfall 2: Pytest Import Mode in Multi-Package Workspace

**What goes wrong:** Running `pytest` across multiple packages causes import errors or silently runs the wrong tests when test files share names (e.g., `test_utils.py` in two packages).

**Why it happens:** pytest's default `prepend` import mode caches the first module by name, then errors on the second.

**How to avoid:** Set `addopts = ["--import-mode=importlib"]` in `[tool.pytest.ini_options]`. Do NOT add `__init__.py` to test directories as a workaround.

**Warning signs:** Import errors during test collection, or tests that pass locally but skip/error in CI.

### Pitfall 3: pnpm Frozen Lockfile in CI

**What goes wrong:** `pnpm install` in CI updates the lockfile, introducing non-determinism.

**Why it happens:** Without `--frozen-lockfile`, pnpm will update `pnpm-lock.yaml` if the current one is stale.

**How to avoid:** Always use `pnpm install --frozen-lockfile` in CI. Locally, use `pnpm install` freely.

**Warning signs:** CI job fails with "ERR_PNPM_OUTDATED_LOCKFILE".

### Pitfall 4: Tailwind v4 Import Path

**What goes wrong:** `@tailwind base/components/utilities` directives don't work in Tailwind v4.

**Why it happens:** Tailwind v4 replaces three `@tailwind` directives with a single `@import "tailwindcss"`.

**How to avoid:** Use `@import "tailwindcss";` in the CSS entry file. Do not use `@tailwind base` etc.

**Warning signs:** CSS classes not applying, PostCSS errors about unknown directives.

### Pitfall 5: uv Sync Working Directory

**What goes wrong:** Running `uv sync` from the repo root installs the workspace root's dev deps but not the member's.

**Why it happens:** `uv sync` by default syncs the package in the current directory. For a virtual root, you may need to target the member explicitly.

**How to avoid:** In CI, run `uv sync --locked --all-extras --dev` from within `packages/conductor-core/`, OR use `uv sync --package conductor-core` from the root.

**Warning signs:** `conductor` CLI command not found after `uv sync` at root.

---

## Code Examples

Verified patterns from official sources:

### uv Workspace Root pyproject.toml

```toml
# Source: https://docs.astral.sh/uv/concepts/projects/workspaces/
[project]
name = "conductor-workspace"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/*"]
```

### Member Package pyproject.toml with CLI Entry Point

```toml
# Source: https://docs.astral.sh/uv/concepts/projects/config/
[project]
name = "conductor-core"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
conductor = "conductor.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/conductor"]
```

### Ruff Configuration (Python 3.12 project)

```toml
# Source: https://docs.astral.sh/ruff/configuration/
[tool.ruff]
target-version = "py312"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
# E = pycodestyle errors, F = pyflakes, I = isort, B = flake8-bugbear, UP = pyupgrade

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

### Pyright Configuration

```toml
# Source: https://github.com/microsoft/pyright/blob/main/docs/configuration.md
[tool.pyright]
include = ["src"]
pythonVersion = "3.12"
typeCheckingMode = "standard"
# Escalate to "strict" once codebase stabilizes
```

### pytest Configuration for src Layout

```toml
# Source: https://docs.pytest.org/en/stable/explanation/goodpractices.html
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = ["--import-mode=importlib"]
```

### biome.json for TypeScript Project

```json
// Source: https://biomejs.dev/reference/configuration/
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100
  },
  "javascript": {
    "formatter": {
      "quoteStyle": "double",
      "semicolons": "always",
      "trailingCommas": "all"
    }
  },
  "organizeImports": {
    "enabled": true
  }
}
```

### Vite Config with Tailwind v4

```typescript
// Source: https://tailwindcss.com/docs (v4 install guide)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
});
```

### Makefile Root Commands

```makefile
# Makefile at repo root
.PHONY: lint test build

lint:
	cd packages/conductor-core && uv run ruff check . && uv run ruff format --check .
	cd packages/conductor-core && uv run pyright
	pnpm --filter conductor-dashboard exec biome check ./src

test:
	cd packages/conductor-core && uv run pytest

build:
	pnpm --filter conductor-dashboard build
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| flake8 + black + isort (3 tools) | Ruff (1 tool, all three) | 2023, mature by 2024 | Single config, 100x faster |
| ESLint + Prettier (2 tools) | Biome (1 tool) | 2024 stable v1 | Single config, written in Rust |
| Tailwind PostCSS config | `@tailwindcss/vite` plugin | Jan 2025 (v4.0) | Zero PostCSS config, `@import "tailwindcss"` in CSS |
| pip + virtualenv | uv | 2024, mature by 2025 | 10-100x faster, lockfiles, workspaces |
| `setup.py` / `setup.cfg` | `pyproject.toml` (PEP 517/621) | 2021-2023, standard by 2024 | Single config file for all Python tools |
| poetry workspaces | uv workspaces | 2024-2025 | Faster, simpler, lockfile included |

**Deprecated/outdated:**
- `setup.py`: Do not create. `pyproject.toml` + `hatchling` is the standard.
- `tailwind.config.js`: Not needed for Tailwind v4. Leave it out.
- `postcss.config.js`: Not needed when using `@tailwindcss/vite`. Leave it out.
- `.eslintrc.js` + `.prettierrc`: Replaced by `biome.json`.
- `requirements.txt`: Replaced by `uv.lock` + `pyproject.toml`.

---

## Open Questions

1. **Pyright strict vs standard mode**
   - What we know: `standard` mode is less strict, `strict` enables all checks including `reportUnknownParameterType`, `reportMissingParameterType`, etc.
   - What's unclear: Starting strict on empty modules is fine, but later phases may hit false positives when integrating with untyped third-party libraries (e.g., ACP SDK).
   - Recommendation: Start with `typeCheckingMode = "standard"`. Escalate to `"strict"` in Phase 2 once we see how ACP types look. This is within Claude's discretion.

2. **Hatchling vs uv_build as build backend**
   - What we know: Both work. `hatchling` is well-established. `uv_build` is newer (0.9.5+) and tightly integrated with uv.
   - What's unclear: `uv_build` is very new; community examples still heavily use `hatchling`.
   - Recommendation: Use `hatchling` for Phase 1. It's the safer choice with more documentation and examples.

3. **pnpm version to pin**
   - What we know: pnpm 9.x is current stable. pnpm 10 may exist by implementation time.
   - Recommendation: Use `packageManager: "pnpm@9"` in root `package.json` and check current pnpm release at implementation time.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8+ |
| Config file | `packages/conductor-core/pyproject.toml` — `[tool.pytest.ini_options]` (Wave 0: create) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/ -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PKG-03 | `uv sync` installs without error | smoke | `cd packages/conductor-core && uv sync --locked` | Wave 0 |
| PKG-03 | `pnpm install` installs without error | smoke | `pnpm install --frozen-lockfile` | Wave 0 |
| PKG-03 | Python linting passes on scaffold | smoke | `cd packages/conductor-core && uv run ruff check .` | Wave 0 |
| PKG-03 | Python type checking passes on scaffold | smoke | `cd packages/conductor-core && uv run pyright` | Wave 0 |
| PKG-03 | `conductor --help` runs without error | smoke | `cd packages/conductor-core && uv run conductor --help` | Wave 0 |
| PKG-03 | CI runs both Python and Node.js checks | integration | GitHub Actions — manual verify on push | Wave 0 |

Note: There is no significant application logic in Phase 1. Most verification is structural (files exist, commands succeed) rather than unit test logic. The CI workflow itself is the key integration test.

### Sampling Rate

- **Per task commit:** `cd packages/conductor-core && uv run ruff check . && uv run conductor --help`
- **Per wave merge:** Full suite — `uv run pytest && uv run pyright && uv run ruff check .`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `packages/conductor-core/tests/__init__.py` — empty, required for pytest discovery
- [ ] `packages/conductor-core/tests/test_cli.py` — covers PKG-03 (conductor --help smoke test)
- [ ] `packages/conductor-core/pyproject.toml` — pytest config section
- [ ] Framework install: `cd packages/conductor-core && uv add --dev pytest` — if not yet in pyproject.toml

---

## Sources

### Primary (HIGH confidence)

- [uv workspaces docs](https://docs.astral.sh/uv/concepts/projects/workspaces/) — workspace root config, member globs, virtual root, cross-member dependencies
- [uv GitHub Actions integration](https://docs.astral.sh/uv/guides/integration/github/) — setup-uv action, caching, uv sync in CI
- [Ruff configuration docs](https://docs.astral.sh/ruff/configuration/) — rule sets, pyproject.toml structure, select vs extend-select
- [pnpm workspaces docs](https://pnpm.io/workspaces) — pnpm-workspace.yaml, workspace protocol, cyclic dep detection
- [Biome configuration reference](https://biomejs.dev/reference/configuration/) — biome.json structure, linter/formatter options
- [Tailwind CSS v4 release blog](https://tailwindcss.com/blog/tailwindcss-v4) — v4 installation changes, @tailwindcss/vite plugin
- [Vite getting started](https://vite.dev/guide/) — react-ts template, pnpm create vite
- [Pyright configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md) — typeCheckingMode, pyproject.toml section
- [pytest good practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html) — src layout, importlib mode, pythonpath

### Secondary (MEDIUM confidence)

- [3 Things I Wish I Knew Before Setting Up a UV Workspace](https://dev.to/aws/3-things-i-wish-i-knew-before-setting-up-a-uv-workspace-30j6) — pitfall 1 (name collision), pitfall 3 (pytest import mode), verified against uv docs
- [How to setup Tailwind CSS v4 with Vite + React](https://dev.to/imamifti056/how-to-setup-tailwind-css-v415-with-vite-react-2025-updated-guide-3koc) — v4 install steps, verified against official docs

### Tertiary (LOW confidence)

None — all key findings were verified against official documentation.

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all tools verified against official docs, all are well-established in their ecosystems
- Architecture: HIGH — uv workspace and pnpm workspace patterns verified against official docs
- Pitfalls: HIGH — uv workspace naming pitfall verified against primary source (dev.to article citing uv error output), pytest importlib mode verified against official pytest docs
- CI configuration: HIGH — astral-sh/setup-uv v7 and pnpm/action-setup v4 are current official actions

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (tools are stable; Tailwind v4 and uv workspaces are mature but fast-moving)
