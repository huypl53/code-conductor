# Phase 11: Packaging and Distribution - Research

**Researched:** 2026-03-11
**Domain:** Python packaging (PyPI), Node.js packaging (npm), getting-started documentation
**Confidence:** HIGH

## Summary

Phase 11 transforms the existing monorepo into two distributable packages: `conductor-ai` on PyPI and `conductor-dashboard` on npm. The Python core already has a well-configured hatchling build system with a CLI entry point (`conductor = "conductor.cli:main"`), so the main work is adding PyPI metadata, adjusting the package name, and verifying clean installs. The dashboard needs to be converted from a private Vite dev project into a publishable npm package with a `bin` entry that serves the built static files.

The getting-started guide must walk a new developer through: installing both packages, configuring Anthropic API credentials, and running their first multi-agent session. Since the dashboard is a companion to the Python core (the FastAPI server runs inside `conductor run --dashboard-port`), the npm package only needs to serve static assets that connect to the backend.

**Primary recommendation:** Keep the Python package as the primary distribution (it contains the orchestrator, ACP layer, state management, CLI, and dashboard backend). The npm package is a thin wrapper around `sirv-cli` serving the Vite build output with a bin script.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PKG-01 | Python core distributed as pip package (orchestration, ACP communication, state management) | Hatchling build system already configured; needs PyPI metadata, package rename to `conductor-ai`, classifiers, README |
| PKG-02 | Node.js dashboard distributed as npm package (web UI) | Remove `"private": true`, add `bin` entry with serve script, include Vite build output in `files` |
| PKG-04 | Installation instructions and getting-started guide | Write docs/GETTING-STARTED.md covering install, API key setup, first session |
</phase_requirements>

## Standard Stack

### Core (Already in Place)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| hatchling | latest | Python build backend | Already configured in conductor-core/pyproject.toml |
| uv | latest | Python package manager / build tool | Already used in monorepo; `uv build` produces wheels |
| pnpm | 10.x | Node.js package manager | Already used in monorepo |
| vite | 7.x | Dashboard build tool | Already configured for dashboard |

### Supporting (New for This Phase)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| twine | latest | PyPI upload tool | Publishing to PyPI |
| sirv-cli | latest | Static file server | Dashboard npm bin script serves built Vite output |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| sirv-cli | express + sirv middleware | More flexible but heavier; sirv-cli is zero-config for static SPAs |
| sirv-cli | vite preview | Not intended for production; lacks --single SPA fallback |
| twine | `uv publish` | uv publish exists but twine is the established standard with better error messages |

## Architecture Patterns

### Package Naming and Structure

**Python package:** Rename from `conductor-core` to `conductor-ai` for PyPI distribution (avoid name collision with existing `conductor` packages on PyPI). The import path stays `conductor.*` -- only the distribution name changes.

**npm package:** Rename from private `conductor-dashboard` to `conductor-dashboard` (public). The `bin` field provides a `conductor-dashboard` CLI command.

### Python Package Layout (Already Correct)
```
packages/conductor-core/
  pyproject.toml          # Build config, metadata, dependencies
  src/
    conductor/            # Import package
      __init__.py         # __version__ = "0.1.0"
      cli/                # Entry point: conductor CLI
      acp/                # ACP communication
      state/              # State management
      orchestrator/       # Core orchestrator
      dashboard/          # FastAPI backend (server.py, watcher.py, events.py)
```

### npm Package Layout (Needs Changes)
```
packages/conductor-dashboard/
  package.json            # Remove "private", add "bin", add "files"
  bin/
    conductor-dashboard.js  # NEW: Node.js bin script that serves dist/
  dist/                   # Vite build output (committed or built at prepublish)
  src/                    # Source (excluded from npm package via "files")
```

### Pattern 1: Python Package Metadata for PyPI
**What:** Complete pyproject.toml with all required PyPI metadata
**When to use:** Before publishing to PyPI

```toml
[project]
name = "conductor-ai"
version = "0.1.0"
description = "AI agent orchestration - a self-organizing team of coding agents"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
authors = [
    { name = "Conductor Team" }
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries",
]
# dependencies already defined
```

### Pattern 2: npm Package with bin Script
**What:** A bin entry in package.json that lets `npm install -g conductor-dashboard` provide a CLI command
**When to use:** For the dashboard npm distribution

```json
{
  "name": "conductor-dashboard",
  "version": "0.1.0",
  "bin": {
    "conductor-dashboard": "bin/conductor-dashboard.js"
  },
  "files": [
    "dist/",
    "bin/"
  ]
}
```

The bin script (`bin/conductor-dashboard.js`):
```javascript
#!/usr/bin/env node
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distDir = join(__dirname, '..', 'dist');
const port = process.argv[2] || '4173';

// Use sirv-cli to serve the built dashboard
const sirv = spawn('npx', ['sirv-cli', distDir, '--single', '--port', port], {
  stdio: 'inherit',
});
sirv.on('exit', (code) => process.exit(code ?? 0));
```

**Alternative (avoid npx at runtime):** Bundle sirv-cli as a dependency and import sirv directly:
```javascript
#!/usr/bin/env node
import sirv from 'sirv';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distDir = join(__dirname, '..', 'dist');
const port = parseInt(process.argv[2] || '4173', 10);

const handler = sirv(distDir, { single: true });
createServer(handler).listen(port, () => {
  console.log(`Conductor Dashboard: http://localhost:${port}`);
});
```

### Pattern 3: Dashboard Static Assets with Python Backend
**What:** The Python `conductor run --dashboard-port` already serves the dashboard via FastAPI. The dashboard static files can be served from the npm-installed location or bundled into the Python package.
**Recommendation:** Keep them separate. The Python package serves the API (WebSocket + REST). The npm package serves the frontend. This matches the existing architecture where `vite dev` proxies to the Python backend.

### Anti-Patterns to Avoid
- **Bundling dashboard assets into the Python wheel:** Adds 1-5 MB of JS/CSS/HTML to the pip package. The dashboard is optional -- not all users want the web UI. Keep packages independent.
- **Using `npm link` instead of proper `files` field:** `npm link` works for development only; published packages need explicit `files` to control what ships.
- **Forgetting `"type": "module"` in npm package:** Already set in package.json. The bin script must use ESM imports if type is module, or use `.mjs` extension.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Static file serving for dashboard | Custom Node.js HTTP server | sirv (library) | Handles MIME types, SPA fallback, caching headers, security headers |
| Python package building | Manual dist/ creation | `uv build` or `python -m build` | Handles METADATA, wheel format, sdist correctly |
| PyPI upload | Custom HTTP upload | twine | Handles auth, retries, checksums, GPG signing |
| Version management | Manual version bumping | Single source of truth in `__init__.py` + hatch-vcs or manual | Prevents version drift between pyproject.toml and code |

## Common Pitfalls

### Pitfall 1: Package Name vs Import Name Confusion
**What goes wrong:** PyPI package is `conductor-ai` but import is `import conductor`. Users get confused.
**Why it happens:** Python allows distribution name to differ from import package name.
**How to avoid:** Document clearly in README: `pip install conductor-ai` then `import conductor`. The `[project.scripts]` entry handles the CLI name.
**Warning signs:** Import errors after install, user confusion in issues.

### Pitfall 2: Missing Dependencies in Production Install
**What goes wrong:** Package installs fine in dev (where dev dependencies are present) but fails in clean venv.
**Why it happens:** Dependency used at runtime is listed in `[dependency-groups] dev` instead of `[project] dependencies`.
**How to avoid:** Test in a fresh virtual environment: `uv venv /tmp/test-env && uv pip install .` then run `conductor --help`.
**Warning signs:** ImportError on first use in clean environment.

### Pitfall 3: Dashboard dist/ Not Included in npm Package
**What goes wrong:** `npm install -g conductor-dashboard` installs but `conductor-dashboard` command fails because `dist/` is empty or missing.
**Why it happens:** dist/ is often in .gitignore and not built before publish. The `files` field in package.json may not include it.
**How to avoid:** Add `"prepublishOnly": "npm run build"` script to ensure dist/ is built before every `npm publish`. Add `dist/` to `files` array.
**Warning signs:** `ENOENT` errors when running the bin command after global install.

### Pitfall 4: Hatchling packages Config Mismatch
**What goes wrong:** `pip install conductor-ai` installs but `conductor` command not found, or imports fail.
**Why it happens:** `[tool.hatch.build.targets.wheel] packages = ["src/conductor"]` must exactly match the source layout.
**How to avoid:** Already correctly configured. Verify with `uv build && uv pip install dist/*.whl` in a clean venv.
**Warning signs:** Empty wheel, missing modules after install.

### Pitfall 5: Version Mismatch Between Python and npm Packages
**What goes wrong:** Python package says 0.1.0 but npm package says 0.2.0 or vice versa.
**Why it happens:** Two separate version fields in two separate config files.
**How to avoid:** Document that both versions must be bumped together. Consider a root-level script or Makefile target for version bumping.
**Warning signs:** Compatibility issues reported by users.

## Code Examples

### Building and Testing Python Package Locally
```bash
# Build the wheel
cd packages/conductor-core
uv build

# Test in a fresh venv
uv venv /tmp/conductor-test
source /tmp/conductor-test/bin/activate
uv pip install dist/conductor_ai-0.1.0-py3-none-any.whl

# Verify CLI works
conductor --help

# Verify imports work
python -c "from conductor.orchestrator.orchestrator import Orchestrator; print('OK')"

# Clean up
deactivate
rm -rf /tmp/conductor-test
```

### Publishing to PyPI
```bash
# Build
cd packages/conductor-core
uv build

# Upload to TestPyPI first
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

### Building and Testing npm Package Locally
```bash
# Build dashboard
cd packages/conductor-dashboard
pnpm build

# Pack locally (creates .tgz without publishing)
npm pack

# Test global install from tarball
npm install -g conductor-dashboard-0.1.0.tgz

# Verify CLI works
conductor-dashboard 4173

# Clean up
npm uninstall -g conductor-dashboard
```

### Getting-Started Guide Structure
```markdown
# Getting Started with Conductor

## Prerequisites
- Python 3.12+
- Node.js 22+ (for dashboard, optional)
- Anthropic API key

## Install
pip install conductor-ai
npm install -g conductor-dashboard  # optional, for web dashboard

## Configure
export ANTHROPIC_API_KEY=sk-ant-...

## Run Your First Session
cd your-project
conductor run "Add a hello world endpoint to the API" --auto

## With Dashboard (optional)
conductor run "Add a hello world endpoint" --auto --dashboard-port 8000
# In another terminal:
conductor-dashboard 4173
# Open http://localhost:4173
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| setup.py + setuptools | pyproject.toml + hatchling | 2023+ | Already using current approach |
| `python setup.py sdist bdist_wheel` | `python -m build` or `uv build` | 2023+ | Already using current approach |
| Manual MANIFEST.in | hatchling include/exclude | 2023+ | Already using current approach |

**Deprecated/outdated:**
- `setup.py`: Replaced by pyproject.toml declarative config. Project already uses pyproject.toml.
- `setup.cfg`: Superseded by pyproject.toml. Not used in this project.

## Open Questions

1. **Package name `conductor-ai` availability on PyPI**
   - What we know: The name `conductor` is already taken on PyPI. `conductor-ai` is the intended alternative.
   - What's unclear: Whether `conductor-ai` is available (needs PyPI check before publish).
   - Recommendation: Verify availability with `pip index versions conductor-ai`. If taken, consider `conductor-agents` or `conductor-orchestrator`.

2. **Dashboard npm package name availability**
   - What we know: `conductor-dashboard` may or may not be taken on npm.
   - What's unclear: Availability on npm registry.
   - Recommendation: Check with `npm view conductor-dashboard`. If taken, use scoped package like `@conductor-ai/dashboard`.

3. **License file**
   - What we know: The pyproject.toml references `license = "MIT"` but no LICENSE file was observed in the repo root.
   - What's unclear: Whether a LICENSE file exists and where.
   - Recommendation: Add a LICENSE file to the repo root and reference it in both packages.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x (Python) / vitest 4.x (Node.js) |
| Config file | packages/conductor-core/pyproject.toml / packages/conductor-dashboard/vite.config.ts |
| Quick run command | `cd packages/conductor-core && uv run pytest -x` |
| Full suite command | `make test && cd packages/conductor-dashboard && pnpm test` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PKG-01 | pip install conductor-ai works in clean venv | integration | `cd packages/conductor-core && uv build && uv venv /tmp/pkg-test && /tmp/pkg-test/bin/pip install dist/*.whl && /tmp/pkg-test/bin/conductor --help` | No -- Wave 0 |
| PKG-02 | npm install -g conductor-dashboard works | integration | `cd packages/conductor-dashboard && pnpm build && npm pack && npm install -g conductor-dashboard-*.tgz && conductor-dashboard --help` | No -- Wave 0 |
| PKG-04 | Getting-started guide exists and is complete | manual-only | Manual review of docs/GETTING-STARTED.md | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest -x`
- **Per wave merge:** `make lint && make test`
- **Phase gate:** Full build + clean install test for both packages

### Wave 0 Gaps
- [ ] `tests/test_packaging.py` -- smoke test that verifies wheel builds and CLI entry point resolves (PKG-01)
- [ ] `bin/conductor-dashboard.js` -- the npm bin script does not exist yet (PKG-02)
- [ ] `docs/GETTING-STARTED.md` -- the getting-started guide does not exist yet (PKG-04)
- [ ] `packages/conductor-core/README.md` -- PyPI long description requires a README
- [ ] `packages/conductor-dashboard/README.md` -- npm package page requires a README
- [ ] License file -- neither package currently includes one

## Sources

### Primary (HIGH confidence)
- [Python Packaging User Guide - Writing pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/) -- pyproject.toml metadata fields, classifiers, README handling
- [Hatch Build Configuration](https://hatch.pypa.io/1.16/config/build/) -- hatchling wheel targets, packages config, shared-data
- [npm package.json docs](https://docs.npmjs.com/cli/v8/configuring-npm/package-json/) -- bin field, files field, scripts
- [Vite Static Deploy Guide](https://vite.dev/guide/static-deploy) -- build output and preview

### Secondary (MEDIUM confidence)
- [sirv-cli on npm](https://www.npmjs.com/package/sirv-cli) -- static file server with SPA fallback
- [Python Packaging Tutorial](https://packaging.python.org/en/latest/tutorials/packaging-projects/) -- twine upload workflow

### Tertiary (LOW confidence)
- Package name availability on PyPI and npm -- needs runtime verification

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - existing build system already configured, well-documented tools
- Architecture: HIGH - straightforward packaging of existing code, no architectural changes needed
- Pitfalls: HIGH - common packaging issues are well-documented in the ecosystem

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable domain, packaging standards change slowly)
