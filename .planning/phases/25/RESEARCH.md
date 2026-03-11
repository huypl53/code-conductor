# Phase 25: Post-Run Build Verification - Research

**Researched:** 2026-03-11
**Domain:** Python asyncio subprocess, Typer CLI options, JSON config loading, Orchestrator extension
**Confidence:** HIGH

## Summary

Phase 25 adds a post-run build verification step (Layer 2 from the design doc at
`docs/plans/2026-03-11-task-verification-design.md`). After all tasks complete in
`Orchestrator.run()` and `Orchestrator.resume()`, if a `build_command` is configured
the orchestrator runs it via `asyncio.subprocess`, logs pass/fail, and prints stderr
on failure. The command can be supplied via `--build-command` CLI flag OR persisted in
`.conductor/config.json`.

The codebase currently has NO `.conductor/config.json` concept — only
`.conductor/state.json` (task state) and `.conductor/sessions.json` (session registry).
Config loading must be added from scratch, following the same `Path(repo_path) /
".conductor"` pattern already used throughout.

**Primary recommendation:** Add `build_command: str | None = None` to
`Orchestrator.__init__`, implement `_post_run_build_check()` as an `async` private
method using `asyncio.create_subprocess_shell`, call it at the tail of `run()` and
`resume()`, read the flag from `--build-command` in `run.py`, and load
`.conductor/config.json` in `_run_async` before constructing the Orchestrator (CLI-side
config resolution, not inside the Orchestrator itself).

---

## Q&A: Research Questions

### Q1: What is `Orchestrator.__init__` signature?

**Current signature (lines 108-117 of orchestrator.py):**

```python
def __init__(
    self,
    state_manager: StateManager,
    repo_path: str,
    mode: str = "auto",
    human_out: asyncio.Queue | None = None,
    human_in: asyncio.Queue | None = None,
    max_agents: int = 10,
    max_revisions: int = 2,
) -> None:
```

All parameters after `state_manager` and `repo_path` are keyword-only with defaults.
Adding `build_command: str | None = None` at the end is backward-compatible — no
existing call site passes it, so nothing breaks.

**Call sites that construct `Orchestrator`:**
1. `packages/conductor-core/src/conductor/cli/commands/run.py` lines 59-65 — primary CLI path
2. `packages/conductor-core/src/conductor/cli/delegation.py` line 144-150 — `handle_delegate` (fresh orch per delegation)
3. `packages/conductor-core/src/conductor/cli/delegation.py` line 226-232 — `resume_delegation` (/resume slash command)

All three sites will need `build_command` threaded through if the feature should work from the delegation path too. The design doc says `/resume` respects the build command, so delegation.py's `resume_delegation` is in scope.

### Q2: How do `run()`, `run_auto()`, and `resume()` end?

**`run()` (lines 146-226):** Ends after a `if pending: await asyncio.gather(...)` straggler wait at line 225-226. The last meaningful line is `await asyncio.gather(*pending.values(), return_exceptions=True)`. Build check goes **after** this block.

**`run_auto()` (lines 283-299):** Calls `await self.run(confirmed)` at line 299 and returns. It does NOT need its own build check — `run()` already handles it. Any post-run code in `run()` will execute before `run_auto()` returns.

**`resume()` (lines 301-431):** Ends with the same straggler pattern at lines 430-431: `await asyncio.gather(*pending.values(), return_exceptions=True)`. Build check goes **after** this block.

**Insertion points (exact):**
- `run()`: after line 226 (`await asyncio.gather(*pending.values(), return_exceptions=True)`)
- `resume()`: after line 431 (`await asyncio.gather(*pending.values(), return_exceptions=True)`)

### Q3: CLI run command structure — how are options passed to Orchestrator?

`run.py` defines a `run()` typer command (lines 23-40) that calls `asyncio.run(_run_async(...))`. The `_run_async` function (lines 43-133) constructs `Orchestrator` at lines 59-65 and passes it keyword arguments.

**Pattern for new option:**
1. Add `build_command: str | None = typer.Option(None, "--build-command", help="...")` to `run()` function signature
2. Pass it into `_run_async(... build_command=build_command)`
3. Add `build_command` parameter to `_run_async` signature
4. Load `.conductor/config.json` inside `_run_async` (after `conductor_dir` is created at line 53) and merge: CLI flag takes precedence over config file
5. Pass resolved `build_command` to `Orchestrator(...)`

**State manager creation pattern (reference for config loading):**
```python
conductor_dir = repo / ".conductor"
conductor_dir.mkdir(parents=True, exist_ok=True)
state_manager = StateManager(conductor_dir / "state.json")
```
Config loading should follow the same pattern: read `conductor_dir / "config.json"` if it exists.

### Q4: Does `.conductor/config.json` already exist?

**No.** A search of the entire codebase finds no reference to `.conductor/config.json`. The only `.conductor/` files currently referenced are:
- `state.json` — task/agent state (StateManager)
- `sessions.json` — session registry (SessionRegistry)
- `chat_sessions/` — directory for chat turn history (ChatHistoryStore)

Config loading must be implemented from scratch. The simplest approach: a standalone helper function in `run.py` (or a new `conductor/config.py`) that reads JSON and returns a dict. No new class needed — the config is read once at startup and resolved into concrete values before Orchestrator is constructed.

**Proposed config schema:**
```json
{
  "build_command": "npx tsc --noEmit"
}
```

**Priority rule:** `--build-command` CLI flag beats config file value (explicit beats implicit).

### Q5: How does the delegation module pass options through on resume?

`delegation.py` has two Orchestrator construction sites:

**`handle_delegate` (lines 144-150):**
```python
orchestrator = Orchestrator(
    state_manager=state_manager,
    repo_path=self._repo_path,
    mode="interactive",
    human_out=self._human_out,
    human_in=self._human_in,
)
```

**`resume_delegation` (lines 226-232):**
```python
orchestrator = Orchestrator(
    state_manager=state_manager,
    repo_path=self._repo_path,
    mode="interactive",
    human_out=self._human_out,
    human_in=self._human_in,
)
```

Neither currently passes `build_command`. For the delegation path, the build command would need to be injected into `DelegationManager.__init__` and stored as `self._build_command`. The design doc explicitly says `/resume` respects the build command, so `resume_delegation` is in scope. `handle_delegate` (the MCP tool path) is less clear — the design doc doesn't mention it explicitly. Safest approach: add `build_command: str | None = None` to `DelegationManager.__init__` so both delegation paths can optionally propagate it, but leave default as `None` (opt-in).

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `asyncio.create_subprocess_shell` | stdlib | Run build command as subprocess | Already used pattern in project; no new dependency |
| `typer.Option` | already installed | New CLI flag | Consistent with all other flags in `run.py` |
| `json` (stdlib) | stdlib | Parse `.conductor/config.json` | No new dependency |
| `pathlib.Path` | stdlib | Config file path resolution | Already used throughout |

### No New Dependencies
This phase adds zero new package dependencies. All required tools are Python stdlib or already-installed packages.

---

## Architecture Patterns

### Recommended Project Structure Changes

```
packages/conductor-core/src/conductor/
├── orchestrator/
│   └── orchestrator.py      # Add build_command param + _post_run_build_check()
├── cli/
│   ├── commands/
│   │   └── run.py           # Add --build-command flag + config.json loading
│   └── delegation.py        # Add build_command param to DelegationManager
```

No new files strictly required. The config loading logic is simple enough to inline in `run.py`.

### Pattern 1: `asyncio.create_subprocess_shell` for build command

```python
async def _post_run_build_check(self) -> None:
    """Run the configured build command and report pass/fail."""
    if not self._build_command:
        return

    logger.info("Running build verification: %s", self._build_command)
    proc = await asyncio.create_subprocess_shell(
        self._build_command,
        cwd=self._repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode == 0:
        logger.info("Build verification passed.")
        print("\nBuild verification: PASSED")
    else:
        stderr_text = stderr.decode(errors="replace")
        logger.error("Build verification FAILED (exit %d):\n%s", proc.returncode, stderr_text)
        print(f"\nBuild verification: FAILED (exit {proc.returncode})")
        print(stderr_text)
```

**Key detail:** `cwd=self._repo_path` ensures the command runs in the repo root, not wherever the process was launched from. This matters for relative paths in commands like `npx tsc --noEmit`.

**`stdout=asyncio.subprocess.PIPE`:** Captured but not printed in the success path. Stderr is the important output for build failures.

### Pattern 2: Config file loading in `_run_async`

```python
def _load_conductor_config(conductor_dir: Path) -> dict:
    config_path = conductor_dir / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}
```

Called inside `_run_async` after `conductor_dir.mkdir(...)`. CLI flag takes precedence:

```python
config = _load_conductor_config(conductor_dir)
resolved_build_command = build_command or config.get("build_command")
```

### Pattern 3: Typer option for new CLI flag

```python
def run(
    description: str = typer.Argument(None, help="Feature description"),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Run mode"),
    repo: str = typer.Option(".", "--repo", help="Path to repo root"),
    resume: bool = typer.Option(False, "--resume", help="Resume interrupted orchestration from state.json"),
    dashboard_port: int = typer.Option(None, "--dashboard-port", help="Start dashboard server on this port"),
    build_command: str = typer.Option(None, "--build-command", help="Shell command to run after all tasks complete (e.g. 'npx tsc --noEmit')"),
) -> None:
```

### Anti-Patterns to Avoid

- **Loading config inside `Orchestrator.__init__`:** The orchestrator is a pure execution engine. Config resolution belongs at the CLI layer (`run.py`). Orchestrator should receive a resolved `build_command` value.
- **Raising on build failure:** The design doc is explicit: "Does not block task completion — it's a final report, not a gate." Do NOT raise an exception or call `sys.exit()` on build failure.
- **Using `subprocess.run` (sync):** `run()` and `resume()` are async. Use `asyncio.create_subprocess_shell`.
- **Printing to stderr inside `_post_run_build_check`:** The existing pattern in the CLI is to print final status to stdout via `_console.print()`. Keep build verification output consistent.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async subprocess | Custom thread + Popen wrapper | `asyncio.create_subprocess_shell` | Stdlib, correct async semantics, no blocking |
| JSON config parsing | Custom parser | `json.loads(path.read_text())` | Stdlib, one line |
| CLI flag | Manual `sys.argv` parsing | `typer.Option` | Consistent with all existing flags |

---

## Common Pitfalls

### Pitfall 1: `cwd` not set on subprocess
**What goes wrong:** Build command like `npx tsc --noEmit` resolves `tsconfig.json` relative to process cwd (likely the user's terminal directory, not the repo root), producing "config not found" errors.
**How to avoid:** Always pass `cwd=self._repo_path` to `create_subprocess_shell`.

### Pitfall 2: Forgetting to call `_post_run_build_check` in `resume()`
**What goes wrong:** VRFY-02 only covered in `run()`, silent omission in `resume()`.
**How to avoid:** The straggler-gather pattern is identical in both methods. Add the call after the `if pending:` block in BOTH.

### Pitfall 3: `build_command` in delegation not propagated
**What goes wrong:** User sets `--build-command` on CLI, but `/resume` inside the chat TUI creates an Orchestrator without the flag (uses `DelegationManager` which doesn't know about it).
**How to avoid:** Add `build_command: str | None = None` to `DelegationManager.__init__`, store as `self._build_command`, and pass through to `Orchestrator(...)` in both `handle_delegate` and `resume_delegation`.

### Pitfall 4: Swallowing `stderr` on large build output
**What goes wrong:** `proc.communicate()` buffers all output in memory. For very large projects this is fine; the concern is truncation if decoded with wrong encoding.
**How to avoid:** Always decode with `errors="replace"` (not `errors="strict"`).

### Pitfall 5: Config JSON parsing failure silently drops config
**What goes wrong:** Malformed config.json causes KeyError or JSONDecodeError that propagates and crashes startup.
**How to avoid:** Wrap config loading in `try/except (json.JSONDecodeError, OSError)` and return `{}` on failure. Log a warning.

---

## Code Examples

### `asyncio.create_subprocess_shell` — basic async subprocess

```python
# Source: Python stdlib docs — asyncio.create_subprocess_shell
proc = await asyncio.create_subprocess_shell(
    "npx tsc --noEmit",
    cwd="/path/to/repo",
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()
# proc.returncode is set after communicate() returns
```

### Typer string option with default None

```python
# Source: existing run.py pattern for dashboard_port
build_command: str = typer.Option(
    None,
    "--build-command",
    help="Shell command to verify build after all tasks complete.",
)
```

### `_run_async` wiring pattern (reference: existing `dashboard_port` pattern)

The `dashboard_port` option follows the exact same wiring pattern needed for `build_command`:
1. Declared in `run()` (typer command)
2. Forwarded into `asyncio.run(_run_async(..., dashboard_port=dashboard_port))`
3. Used inside `_run_async` to configure the orchestrator/server

---

## Validation Architecture

nyquist_validation is enabled (not set to false in config.json).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `pytest.ini` or `pyproject.toml` (check existing) |
| Quick run command | `pytest packages/conductor-core/tests/test_orchestrator.py -x -q` |
| Full suite command | `pytest packages/conductor-core/tests/ -x -q` |

### Phase Requirements → Test Map

| ID | Behavior | Test Type | Automated Command | File Exists? |
|----|----------|-----------|-------------------|-------------|
| VRFY-02 | Build command runs after all tasks complete in `run()` | unit | `pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification -x` | ❌ Wave 0 |
| VRFY-02 | Build command runs after all tasks complete in `resume()` | unit | `pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification -x` | ❌ Wave 0 |
| VRFY-02 | Pass/fail reported with stderr output | unit | `pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification -x` | ❌ Wave 0 |
| VRFY-02 | Build NOT run if `build_command` is None | unit | `pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification -x` | ❌ Wave 0 |
| VRFY-03 | `--build-command` CLI flag sets build_command | unit | `pytest packages/conductor-core/tests/test_run_command.py::TestBuildCommand -x` | ❌ Wave 0 |
| VRFY-03 | `.conductor/config.json` `build_command` key is loaded | unit | `pytest packages/conductor-core/tests/test_run_command.py::TestBuildCommand -x` | ❌ Wave 0 |
| VRFY-03 | CLI flag overrides config.json value | unit | `pytest packages/conductor-core/tests/test_run_command.py::TestBuildCommand -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest packages/conductor-core/tests/test_orchestrator.py packages/conductor-core/tests/test_run_command.py -x -q`
- **Per wave merge:** `pytest packages/conductor-core/tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `packages/conductor-core/tests/test_orchestrator.py` — add `TestBuildVerification` class (new test class alongside existing `TestOrchestrator`)
- [ ] `packages/conductor-core/tests/test_run_command.py` — add `TestBuildCommand` class (new test class alongside existing `TestRunResume`)

*(Existing test infrastructure and fixtures cover all other setup needs.)*

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No build verification | Post-run `asyncio.create_subprocess_shell` gate | Phase 25 (now) | Catches cross-file import errors, syntax errors, type errors |
| Config only via CLI flags | CLI flags + `.conductor/config.json` fallback | Phase 25 (now) | Build command persists across runs without re-specifying |

---

## Open Questions

1. **Should `handle_delegate` (MCP delegation) also respect `build_command`?**
   - What we know: Design doc says `/resume` in chat TUI respects it. Does not mention `conductor_delegate` tool.
   - What's unclear: When the user types a feature in the TUI and Claude calls `conductor_delegate`, should a build check run after that delegation?
   - Recommendation: Add `build_command` to `DelegationManager` with `None` default. Wire it for `resume_delegation`. Leave `handle_delegate` wiring as optional (can be done in same PR for completeness at near-zero cost).

2. **Where should build result be printed — via `logger` or `print`?**
   - What we know: The CLI uses `rich.console.Console` for final output (see `run.py` lines 129-133). The orchestrator itself uses `logger`.
   - Recommendation: Log via `logger` inside the orchestrator method (for testability). The CLI layer can also print a summary line after `orch_task` completes if desired. Keep the orchestrator free of console/rich dependencies.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `orchestrator.py` — `__init__` signature, `run()`, `resume()` termination points
- Direct code inspection of `run.py` — CLI option pattern, `_run_async` wiring
- Direct code inspection of `delegation.py` — Orchestrator construction sites
- Python stdlib docs — `asyncio.create_subprocess_shell`, `asyncio.subprocess.PIPE`

### Secondary (MEDIUM confidence)
- Existing test patterns in `test_orchestrator.py` and `test_run_command.py` — confirmed pytest-asyncio + `unittest.mock` is the project's test style

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all findings from direct code inspection, no guessing
- Architecture: HIGH — insertion points verified with exact line numbers
- Pitfalls: HIGH — derived from code structure + stdlib subprocess semantics

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable codebase, no fast-moving dependencies)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VRFY-02 | After all tasks complete, if `build_command` is configured, the orchestrator runs it and reports pass/fail with stderr output | `asyncio.create_subprocess_shell` in `_post_run_build_check()`; call after straggler-gather in `run()` (line 226) and `resume()` (line 431) |
| VRFY-03 | User can set `build_command` via `--build-command` CLI flag or `.conductor/config.json` | `typer.Option` in `run.py`; `_load_conductor_config()` helper reads `conductor_dir / "config.json"`; CLI flag overrides config |
</phase_requirements>
