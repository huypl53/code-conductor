# Contributing to Conductor

Thanks for your interest in contributing. This guide covers the development setup, project structure, testing, and how to submit changes.

---

## Development Setup

### Prerequisites

- **Python 3.12+** and [uv](https://docs.astral.sh/uv/) for the Python core
- **Node.js 22+** and [pnpm](https://pnpm.io/) for the dashboard frontend
- **An Anthropic API key** for integration testing (optional for unit tests)

### Clone and install

```bash
git clone https://github.com/your-org/conductor.git
cd conductor

# Python dependencies (orchestrator core)
uv sync

# Node.js dependencies (dashboard)
pnpm install
```

### Verify the setup

```bash
# Python tests
cd packages/conductor-core && uv run pytest

# Dashboard tests
cd packages/conductor-dashboard && pnpm test

# Type checking
cd packages/conductor-core && uv run pyright src/
cd packages/conductor-dashboard && pnpm typecheck
```

---

## Project Structure

```
conductor/
├── packages/
│   ├── conductor-core/          # Python — orchestrator, CLI, ACP client
│   │   ├── src/conductor/
│   │   │   ├── acp/            # ACP protocol client
│   │   │   ├── cli/            # CLI entry point, chat TUI, commands
│   │   │   │   ├── __init__.py     # Typer app, entry point
│   │   │   │   ├── chat.py         # Interactive chat session
│   │   │   │   ├── delegation.py   # Smart delegation manager
│   │   │   │   ├── commands/
│   │   │   │   │   ├── run.py      # `conductor run` command
│   │   │   │   │   └── status.py   # `conductor status` command
│   │   │   │   └── ...
│   │   │   ├── orchestrator/   # Core orchestration logic
│   │   │   │   ├── orchestrator.py # Spawn loop, verification, resume
│   │   │   │   ├── decomposer.py   # Task decomposition
│   │   │   │   ├── reviewer.py     # Code review + structured feedback
│   │   │   │   ├── scheduler.py    # Dependency-aware scheduling
│   │   │   │   ├── escalation.py   # Human escalation routing
│   │   │   │   └── ownership.py    # File-level locks
│   │   │   ├── state/          # Shared state management
│   │   │   │   ├── manager.py      # File-locked state read/write
│   │   │   │   └── models.py       # Pydantic v2 models
│   │   │   └── dashboard/      # FastAPI backend for web dashboard
│   │   └── tests/              # pytest test suite
│   └── conductor-dashboard/     # TypeScript — React web dashboard
│       ├── src/
│       │   ├── components/     # React components
│       │   ├── hooks/          # WebSocket hooks, state hooks
│       │   └── types/          # TypeScript type definitions
│       └── ...
├── docs/
│   ├── GETTING-STARTED.md      # User-facing usage guide
│   └── plans/                  # Design docs and implementation plans
├── README.md
├── CONTRIBUTING.md             # This file
└── LICENSE                     # MIT
```

---

## Key Concepts

### Orchestrator lifecycle

The orchestrator follows this flow:

1. **Decompose** — break the feature description into `TaskSpec` objects with dependencies
2. **Schedule** — `DependencyScheduler` (wraps `graphlib.TopologicalSorter`) determines execution order
3. **Spawn** — `asyncio.wait(FIRST_COMPLETED)` loop launches agents as dependencies resolve
4. **Review** — `review_output()` checks each agent's work, returns `ReviewVerdict` with structured feedback
5. **Verify** — file existence gate checks `target_file` on disk; missing file triggers revision
6. **Build check** — optional `_post_run_build_check()` runs the configured build command
7. **Resume** — `resume()` reconstructs the scheduler from state, re-runs tasks with missing files

### State model

All coordination happens through `.conductor/state.json`, managed by `StateManager` with file locking (`filelock`). The state uses Pydantic v2 models:

- `ConductorState` — top-level container
- `Task` — id, title, description, status, target_file, requires, produces
- `AgentRecord` — id, name, role, current_task_id, status
- `TaskStatus` — PENDING, IN_PROGRESS, COMPLETED
- `ReviewStatus` — APPROVED, NEEDS_REVISION

### ACP communication

Agents communicate via the Agent Communication Protocol. The orchestrator is an ACP client that spawns ACP-compatible agents (Claude Code instances) as subprocesses.

---

## Running Tests

### Python (conductor-core)

```bash
cd packages/conductor-core

# Full suite
uv run pytest

# Verbose output
uv run pytest -v

# Specific test class
uv run pytest tests/test_orchestrator.py::TestFileExistenceGate -v

# With coverage
uv run pytest --cov=conductor --cov-report=term-missing
```

Test categories:

| Test class | What it covers |
|------------|---------------|
| `TestDecomposer` | Task decomposition from feature descriptions |
| `TestOrchestratorRun` | Full orchestrator spawn loop |
| `TestResumeScheduler` | Resume with completed/in-progress/pending tasks |
| `TestReviewOnlyFallback` | Review exception handling during resume |
| `TestResumeSpawnLoop` | Spawn loop edge cases (marked_done, exceptions) |
| `TestFileExistenceGate` | Target file verification before marking complete |
| `TestPostRunBuild` / `TestBuildVerification` | Build command execution |
| `TestRunResume` / `TestRunBuildCommand` | CLI flag wiring |
| `TestConfigJsonBuildCommand` | Config.json loading and precedence |

### TypeScript (conductor-dashboard)

```bash
cd packages/conductor-dashboard

# Full suite
pnpm test

# Watch mode
pnpm test -- --watch
```

---

## Code Style

### Python

- **Formatter:** [ruff](https://docs.astral.sh/ruff/) — line length 88, double quotes
- **Linter:** ruff — rules: E, F, I, B, UP
- **Type checker:** [pyright](https://github.com/microsoft/pyright) — standard mode
- **Target:** Python 3.12+

```bash
cd packages/conductor-core
uv run ruff check src/
uv run ruff format src/
uv run pyright src/
```

### TypeScript

- **Formatter/Linter:** [Biome](https://biomejs.dev/)
- **Type checker:** TypeScript strict mode

```bash
cd packages/conductor-dashboard
pnpm lint
pnpm typecheck
```

---

## Making Changes

### Before you start

1. Create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature main
   ```

2. Ensure tests pass before making changes:
   ```bash
   cd packages/conductor-core && uv run pytest
   ```

### Writing code

- **Test first** — write a failing test, then implement the fix
- **Keep changes focused** — one feature or fix per branch
- **Match existing patterns** — look at nearby code for conventions
- **No unnecessary abstractions** — prefer simple, direct code over clever indirection

### Key files you'll likely touch

| Area | Files |
|------|-------|
| Orchestrator logic | `packages/conductor-core/src/conductor/orchestrator/orchestrator.py` |
| Task decomposition | `packages/conductor-core/src/conductor/orchestrator/decomposer.py` |
| Code review | `packages/conductor-core/src/conductor/orchestrator/reviewer.py` |
| State models | `packages/conductor-core/src/conductor/state/models.py` |
| CLI commands | `packages/conductor-core/src/conductor/cli/commands/run.py` |
| Chat TUI | `packages/conductor-core/src/conductor/cli/chat.py` |
| Smart delegation | `packages/conductor-core/src/conductor/cli/delegation.py` |
| Tests | `packages/conductor-core/tests/test_orchestrator.py` |

### Testing patterns

Tests use `pytest` with `pytest-asyncio`. Common patterns:

```python
# Mock the state manager
mgr = MagicMock()
mgr.read_state = MagicMock(return_value=mock_state)
mgr.mutate = MagicMock()

# Create an orchestrator with mocked dependencies
orch = Orchestrator(state_manager=mgr, repo_path=str(tmp_path))

# Patch internal methods to inspect calls
with patch.object(orch, '_run_agent_loop', new_callable=AsyncMock) as mock_loop:
    await orch.resume()
assert mock_loop.call_count == 1

# Track state mutations
mutations = []
mgr.mutate = MagicMock(side_effect=lambda fn: mutations.append(fn))
```

### Commit messages

Use conventional commit format:

```
feat: add file existence gate for task verification
fix: handle ReviewError in review_only resume path
test: add TestResumeSpawnLoop for edge cases
docs: update getting started guide with build verification
```

### Before submitting

1. Run the full test suite:
   ```bash
   cd packages/conductor-core && uv run pytest
   ```

2. Run the linter and type checker:
   ```bash
   uv run ruff check src/
   uv run pyright src/
   ```

3. Make sure your changes don't break the dashboard (if applicable):
   ```bash
   cd packages/conductor-dashboard && pnpm test && pnpm typecheck
   ```

---

## Architecture Decisions

Key design choices and their rationale:

| Decision | Rationale |
|----------|-----------|
| Shared state file over message passing | Simpler coordination; file system is durable; filelock prevents corruption |
| `asyncio.wait(FIRST_COMPLETED)` spawn loop | Ready tasks unblock as dependencies complete without waiting for whole wave |
| File existence gate in revision loop | Reuses existing revision mechanism — missing file treated same as failed review |
| Build command as report, not gate | Build failures are informational — they don't roll back completed tasks |
| Config loading in CLI, not orchestrator | Orchestrator is a pure execution engine; config resolution is a CLI concern |
| Review verdict with structured fields | `ReviewVerdict.revision_instructions` gives agents actionable feedback, not just pass/fail |

---

## Getting Help

- Open an issue on GitHub for bugs or feature requests
- Check existing [design docs](docs/plans/) for context on past decisions
- Read the [Getting Started guide](docs/GETTING-STARTED.md) for user-facing documentation
