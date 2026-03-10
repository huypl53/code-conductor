# Phase 8: CLI Interface - Research

**Researched:** 2026-03-11
**Domain:** Python CLI (Typer + Rich), async interactive terminal, asyncio queue wiring
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLI-01 | User can chat with the orchestrator via CLI terminal | asyncio queue pair (human_out / human_in already built in escalation layer); CLI must feed input to human_in and print human_out answers |
| CLI-02 | User can see which agents exist, their roles, and current task status | Rich Live + Table reads `.conductor/state.json` via StateManager; poll or on-demand refresh |
| CLI-03 | User can intervene (cancel, redirect, provide feedback) via CLI commands | Orchestrator.cancel_agent / inject_guidance / pause_for_human_decision are built; CLI must expose them as typed sub-commands or inline chat commands |
</phase_requirements>

---

## Summary

Phase 8 adds the `conductor` CLI that a developer runs to launch orchestration and interact with it in real time. The orchestrator core (Phase 7) is complete and already exposes `run_auto()`, `run()`, `cancel_agent()`, `inject_guidance()`, and `pause_for_human_decision()`. The escalation layer already uses `asyncio.Queue` pairs (`human_out`, `human_in`) for interactive mode communication. The CLI's job is: (1) wire those queues, (2) drive a live terminal display showing agent/task status, and (3) accept typed input that is routed to the correct intervention method.

The standard stack for this phase is **Typer 0.24.x** (CLI command structure, entry point `conductor`) plus **Rich 14.x** (`Live`, `Table`, `Console`) for the live-updating display. Typer wraps async commands with `asyncio.run()` automatically when you define `async def` command callbacks. Rich `Live` works with asyncio via a background refresh task and `live.update()` calls from any coroutine.

The key design decision is **display loop vs. input loop**. Both must run concurrently inside the same asyncio event loop. The standard pattern: a `display_task` polls state every N seconds and calls `live.update(table)`, while a separate `input_task` uses `asyncio.to_thread(input, "> ")` to read a line without blocking the event loop. A command parser dispatches lines to `cancel`, `redirect`, or `feedback` sub-commands, which call into the already-built `Orchestrator` intervention methods.

**Primary recommendation:** Use Typer for the `conductor run` command, Rich `Live` for the agent status table, and `asyncio.to_thread(input, "> ")` for non-blocking human input — no additional TUI framework needed.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typer | 0.24.1 | CLI framework — `conductor run`, `conductor status`, argument parsing | FastAPI ecosystem, type-hint-native, auto async support, auto help generation, already depends on Rich |
| rich | 14.3.3 | `Live` display, `Table` for agent status, `Console` for output | De-facto standard for terminal UI in Python; already pulled in transitively by Typer |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio (stdlib) | 3.12+ | Concurrency between display loop and input loop | Always — already used by the whole project |

Typer and Rich are the only new **direct** dependencies for this phase. Both are pure-Python and have zero transitive surprises.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Typer | Click directly | Click has no native async support, requires manual `asyncio.run()` wrapper. Typer handles it transparently. |
| Rich Live | Textual | Textual is a full TUI app framework (event loop replaces asyncio). Overkill for this phase; also conflicts with the orchestrator's own asyncio loop unless explicitly integrated. |
| `asyncio.to_thread(input)` | prompt_toolkit | prompt_toolkit `prompt_async()` is more polished (completion, history) but adds a new heavy dependency. `asyncio.to_thread(input)` is stdlib only and sufficient for Phase 8 scope. |

**Installation:**
```bash
# Add to packages/conductor-core/pyproject.toml [project] dependencies:
uv add --package conductor-core "typer>=0.24" "rich>=14"
```

Note: Typer declares `rich` as a dependency (`typer[all]` installs it explicitly). Adding both gives version pinning control.

---

## Architecture Patterns

### Recommended Project Structure
```
packages/conductor-core/src/conductor/
├── cli/
│   ├── __init__.py          # main() entrypoint — Typer app
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── run.py           # `conductor run "<description>"` command
│   │   └── status.py        # `conductor status` command (read-only)
│   ├── display.py           # Rich Live table builder + refresh loop
│   └── input_loop.py        # async input reader + command dispatcher
```

The `__init__.py` currently has a stub `main()` with argparse. It will be replaced with a Typer app.

### Pattern 1: Typer App with Async Commands

**What:** Typer detects `async def` command callbacks and wraps them in `asyncio.run()` automatically.
**When to use:** Every `conductor` sub-command that needs to await orchestrator methods.

```python
# Source: https://pypi.org/project/typer/ (Typer 0.24.1)
import asyncio
import typer

app = typer.Typer(help="Conductor: AI agent orchestration")

@app.command()
def run(
    description: str = typer.Argument(..., help="Feature description to build"),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Run mode"),
    repo: str = typer.Option(".", "--repo", help="Repository root path"),
) -> None:
    """Start orchestrator and show agent activity in the terminal."""
    asyncio.run(_run_async(description, auto=auto, repo=repo))

async def _run_async(description: str, *, auto: bool, repo: str) -> None:
    ...

def main() -> None:
    app()
```

Note: Typer's handling of `async def` commands is documented but the wrapping is implicit in some versions. Explicit `asyncio.run()` in a sync wrapper is the safest and most readable approach, confirmed by project patterns (no issues with nesting since CLI is the top-level entry point).

### Pattern 2: Concurrent Display and Input in asyncio

**What:** `asyncio.gather()` two tasks: one polls state and refreshes `Live`, the other reads user input without blocking the loop.
**When to use:** The `conductor run` command's inner async loop.

```python
# Source: Verified against asyncio docs + Rich Live asyncio discussion
# https://github.com/Textualize/rich/discussions/1401
import asyncio
from rich.live import Live
from rich.table import Table

async def _run_async(description: str, *, auto: bool, repo: str) -> None:
    human_out: asyncio.Queue = asyncio.Queue()
    human_in: asyncio.Queue = asyncio.Queue()

    state_manager = StateManager(Path(repo) / ".conductor" / "state.json")
    orchestrator = Orchestrator(
        state_manager=state_manager,
        repo_path=repo,
        mode="auto" if auto else "interactive",
        human_out=human_out,
        human_in=human_in,
    )

    orch_task = asyncio.create_task(
        orchestrator.run_auto(description) if auto else orchestrator.run(description)
    )

    with Live(console=Console(stderr=False), refresh_per_second=4) as live:
        await asyncio.gather(
            _display_loop(live, state_manager, until=orch_task),
            _input_loop(human_out, human_in, orchestrator),
            orch_task,
        )
```

### Pattern 3: Non-Blocking Input with `asyncio.to_thread`

**What:** Runs `input()` in a thread pool so the event loop stays responsive.
**When to use:** Any point where the CLI needs to read a line from the user.

```python
# Source: Python 3.12 stdlib asyncio docs
async def _ainput(prompt: str = "") -> str:
    return await asyncio.to_thread(input, prompt)

async def _input_loop(
    human_out: asyncio.Queue,
    human_in: asyncio.Queue,
    orchestrator: Orchestrator,
) -> None:
    while True:
        line = await _ainput("> ")
        line = line.strip()
        if not line:
            continue
        if line == "quit" or line == "exit":
            break
        await _dispatch_command(line, human_out, human_in, orchestrator)
```

### Pattern 4: Rich Live Agent Status Table

**What:** Build a `rich.table.Table` from current state on each refresh cycle.
**When to use:** The display loop polls `state_manager.read_state()` every ~2 seconds.

```python
# Source: Rich docs https://rich.readthedocs.io/en/stable/live.html
from rich.table import Table
from rich.live import Live
from conductor.state.manager import StateManager
from conductor.state.models import AgentStatus, TaskStatus

def _build_table(state) -> Table:
    table = Table(title="Conductor Agents", expand=True)
    table.add_column("Agent", style="cyan", no_wrap=True)
    table.add_column("Role", style="magenta")
    table.add_column("Task")
    table.add_column("Status", style="bold")

    status_styles = {
        TaskStatus.PENDING: "dim",
        TaskStatus.IN_PROGRESS: "yellow",
        TaskStatus.COMPLETED: "green",
        TaskStatus.FAILED: "red",
        TaskStatus.BLOCKED: "orange3",
    }
    agent_map = {a.id: a for a in state.agents}
    for task in state.tasks:
        agent = agent_map.get(task.assigned_agent or "") if task.assigned_agent else None
        agent_name = agent.name if agent else "-"
        agent_role = agent.role if agent else "-"
        style = status_styles.get(task.status, "")
        table.add_row(agent_name, agent_role, task.title, task.status, style=style)
    return table

async def _display_loop(live: Live, state_manager: StateManager, until: asyncio.Task) -> None:
    while not until.done():
        state = await asyncio.to_thread(state_manager.read_state)
        live.update(_build_table(state))
        await asyncio.sleep(2.0)
    # Final refresh after completion
    state = await asyncio.to_thread(state_manager.read_state)
    live.update(_build_table(state))
```

### Pattern 5: CLI Intervention Commands

**What:** Simple prefix-based command dispatch from the input loop to orchestrator methods.
**When to use:** Interactive mode only; in auto mode, input is still read but only for forwarding human answers to the `human_in` queue.

Supported inline commands (suggested):
- `cancel <agent_id>` — calls `orchestrator.cancel_agent()`
- `redirect <agent_id> <new instructions>` — cancel + re-assign with new description
- `feedback <agent_id> <message>` — calls `orchestrator.inject_guidance()`
- `status` — prints current agent table without requiring Live
- `quit` / `exit` — signals clean shutdown

In interactive mode, when `human_out` has an item waiting, the input loop should show the question prominently before the `> ` prompt.

### Anti-Patterns to Avoid

- **Calling `input()` directly in async code:** Blocks the entire event loop. Always use `asyncio.to_thread(input, "> ")`.
- **Using `print()` inside a Rich `Live` context:** Corrupts the Live display. Use `live.console.print()` or `Console(stderr=True)` for all output within the Live block.
- **Creating a new StateManager per refresh:** Opens and locks the file on every call. Reuse the same `StateManager` instance across the whole CLI session.
- **Holding the `asyncio.Semaphore` from a different event loop:** The orchestrator creates its semaphore inside `run()` — never pass it from outside.
- **Running Textual inside the orchestrator's asyncio loop:** Textual replaces the event loop. Keep Rich Live which is loop-agnostic.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Argument parsing for `conductor run` | Custom argparse | Typer | Auto help, type coercion, completions, subcommand tree |
| Spinner / progress animation | Print `\r` loops | Rich `Status` or `Spinner` | Thread-safe, handles terminal resize, no flicker |
| ANSI color codes | String formatting with escape codes | Rich `Console` markup | Handles no-color terminals, Windows, piping |
| Non-blocking stdin | Custom `select()` / `fcntl` non-blocking tricks | `asyncio.to_thread(input)` | Cross-platform, integrates with event loop cleanly |
| Periodic polling sleep loop | `while True: time.sleep()` | `asyncio.sleep()` inside async task | Yields to event loop; `time.sleep()` blocks everything |

**Key insight:** The orchestrator machinery is complete. This phase is entirely a presentation + wiring layer. Do not re-implement queue routing or state reading — consume the existing APIs.

---

## Common Pitfalls

### Pitfall 1: `print()` inside Rich Live
**What goes wrong:** Console output mid-render corrupts the Live display — lines jump, cursor resets, display tears.
**Why it happens:** Rich Live takes over stdout rendering. External writes race with its render cycle.
**How to avoid:** Use `live.console.print(...)` for all output within the `with Live(...)` block.
**Warning signs:** Garbled output when agent logs appear.

### Pitfall 2: `input()` blocking the event loop
**What goes wrong:** All async tasks freeze while waiting for user to press Enter.
**Why it happens:** `input()` is a blocking C call that holds the OS thread.
**How to avoid:** Always `await asyncio.to_thread(input, "> ")`.
**Warning signs:** Display stops updating as soon as the input prompt appears.

### Pitfall 3: Race on `asyncio.Queue.get()` and `asyncio.to_thread(input)`
**What goes wrong:** The input loop awaits `input()` in a thread AND the `human_out` queue simultaneously — a question arrives but the user is already mid-typing a different command.
**Why it happens:** Two concurrent waits on different sources with no priority.
**How to avoid:** Use `asyncio.wait([input_task, queue_task], return_when=FIRST_COMPLETED)` so whichever fires first wins. Cancel the other, handle the result.

### Pitfall 4: Orphaned orchestrator task on KeyboardInterrupt
**What goes wrong:** User presses `Ctrl+C`, the Typer command exits, but the orchestrator's agent tasks continue running in background processes (ACP sub-processes).
**Why it happens:** asyncio tasks are not automatically cancelled on `KeyboardInterrupt` if not in the gathered set.
**How to avoid:** Wrap the entire `asyncio.gather(orch_task, display_task, input_task)` in a `try/except KeyboardInterrupt` block that cancels `orch_task` and awaits it before exiting.

### Pitfall 5: `StateManager.read_state()` in the display loop calling from wrong thread
**What goes wrong:** `StateManager.read_state()` uses `filelock` which is blocking. Calling it directly from a coroutine blocks the event loop during file I/O.
**Why it happens:** Forgetting the project pattern established in Phase 3.
**How to avoid:** Always `await asyncio.to_thread(state_manager.read_state)` — this is already the pattern used throughout the orchestrator.

### Pitfall 6: `conductor run` with no `.conductor/` directory
**What goes wrong:** `StateManager` may fail on first run if `.conductor/state.json` doesn't exist.
**Why it happens:** StateManager expects the directory to exist (or be created).
**How to avoid:** CLI `run` command should call `Path(repo) / ".conductor"` `.mkdir(parents=True, exist_ok=True)` before constructing `StateManager`. Check how Phase 2 initializes this.

---

## Code Examples

### Minimal Typer app with `conductor run`
```python
# Source: Typer docs https://typer.tiangolo.com/tutorial/commands/
import asyncio
from pathlib import Path
import typer
from rich.console import Console

app = typer.Typer(prog_name="conductor", help="Conductor: AI agent orchestration")
console = Console()

@app.command()
def run(
    description: str = typer.Argument(..., help="Feature description"),
    auto: bool = typer.Option(True, "--auto/--interactive"),
    repo: str = typer.Option(".", "--repo", help="Path to repo root"),
) -> None:
    """Run the orchestrator on a feature description."""
    asyncio.run(_run_async(description, auto=auto, repo=Path(repo).resolve()))

def main() -> None:
    app()
```

### Live table with async refresh
```python
# Source: Rich docs https://rich.readthedocs.io/en/stable/live.html
from rich.live import Live
from rich.table import Table

async def _display_loop(live: Live, state_manager, until: asyncio.Task) -> None:
    while not until.done():
        state = await asyncio.to_thread(state_manager.read_state)
        live.update(_build_table(state))
        await asyncio.sleep(2.0)
```

### Human question pump (interactive mode)
```python
# When running in interactive mode, the input loop must drain human_out
# and present questions before taking user commands.
async def _input_loop(
    human_out: asyncio.Queue,
    human_in: asyncio.Queue,
    orchestrator,
) -> None:
    input_task = asyncio.create_task(asyncio.to_thread(input, "> "))
    queue_task = asyncio.create_task(human_out.get())

    while True:
        done, pending = await asyncio.wait(
            {input_task, queue_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if queue_task in done:
            query = queue_task.result()
            console.print(f"\n[bold yellow]Agent question:[/] {query.question}")
            answer = await asyncio.to_thread(input, "Your answer: ")
            await human_in.put(answer)
            queue_task = asyncio.create_task(human_out.get())
        if input_task in done:
            line = input_task.result().strip()
            if line:
                await _dispatch_command(line, human_out, human_in, orchestrator)
            input_task = asyncio.create_task(asyncio.to_thread(input, "> "))
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `argparse` (current stub) | Typer 0.24 | Phase 8 | Auto help, type hints, subcommands, async support |
| Synchronous `print` loops | Rich `Live` | Phase 8 | Flicker-free, structured display |
| Blocking `input()` | `asyncio.to_thread(input)` | Phase 8 | Non-blocking stdin in async context |

**Deprecated/outdated:**
- `argparse` stub in `conductor/cli/__init__.py`: The Phase 1 placeholder. Replace entirely with Typer app in this phase.

---

## Open Questions

1. **`.conductor/` directory initialization**
   - What we know: `StateManager` uses the path passed to it; `Orchestrator.__init__` builds `_sessions_path` from `repo_path / ".conductor" / "sessions.json"`.
   - What's unclear: Whether `StateManager` auto-creates the directory or requires it to exist.
   - Recommendation: CLI `run` command creates `.conductor/` with `mkdir(parents=True, exist_ok=True)` before constructing any manager — cheap guard, no harm if already exists.

2. **`conductor status` as separate command**
   - What we know: CLI-02 says "user can see which agents exist" — not scoped to only within an active `run`.
   - What's unclear: Whether a standalone `conductor status` (reads state file without running) is in scope for Phase 8, or only the live view inside `conductor run`.
   - Recommendation: Implement both: `conductor run` shows live view, `conductor status` prints current state as a one-shot table. The `status` command reuses `_build_table()` and is trivial to add.

3. **Shutdown of orphan ACP processes**
   - What we know: Each agent runs as a subprocess spawned by ACP. Cancelling the orchestrator task does not automatically kill subprocess.
   - What's unclear: Whether the ACP SDK cleans up subprocesses on `ACPClient.__aexit__` when cancelled.
   - Recommendation: Test `KeyboardInterrupt` behavior manually in Phase 8 verification. If subprocesses linger, add a `cleanup()` hook that calls `orchestrator.cancel_agent()` for all active agents before exit.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23.x |
| Config file | `packages/conductor-core/pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_cli.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CLI-01 | `conductor run "..."` starts orchestrator; user can type and answers reach human_in queue | unit (mock orchestrator) | `uv run pytest tests/test_cli.py::test_run_interactive_routes_input -x` | ❌ Wave 0 |
| CLI-02 | Agent table displays name, role, status from state | unit | `uv run pytest tests/test_cli.py::test_build_table -x` | ❌ Wave 0 |
| CLI-03 | `cancel <agent_id>` calls `orchestrator.cancel_agent`; `feedback <agent_id> <msg>` calls `inject_guidance` | unit (mock orchestrator) | `uv run pytest tests/test_cli.py::test_dispatch_cancel -x` `uv run pytest tests/test_cli.py::test_dispatch_feedback -x` | ❌ Wave 0 |

Existing `tests/test_cli.py` has two tests (`test_conductor_help`, `test_conductor_version`). New tests extend this file.

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_cli.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_cli.py` — extend with: `test_run_interactive_routes_input`, `test_build_table`, `test_dispatch_cancel`, `test_dispatch_feedback`
- [ ] No new framework install needed — pytest, pytest-asyncio already in dev dependencies

---

## Sources

### Primary (HIGH confidence)
- PyPI typer 0.24.1 — https://pypi.org/project/typer/ — version, async support, Rich dependency
- PyPI rich 14.3.3 — https://pypi.org/project/rich/ — version confirmed
- Rich Live docs — https://rich.readthedocs.io/en/stable/live.html — Live class API, update() pattern
- Python 3.12 asyncio.to_thread — https://docs.python.org/3/library/asyncio-task.html — non-blocking input pattern

### Secondary (MEDIUM confidence)
- Rich + asyncio community discussion — https://github.com/Textualize/rich/discussions/1401 — asyncio.create_task + Live.update() pattern
- Python Rich Live async blog — https://epsi.bitbucket.io/monitor/2022/12/05/python-rich-live-03/ — verified pattern: `with Live(...): task = asyncio.create_task(...)`, loop updates layout

### Tertiary (LOW confidence)
- Typer async support claims from blog posts — not independently verified against Typer source; safe pattern is explicit `asyncio.run()` wrapper regardless

---

## Metadata

**Confidence breakdown:**
- Standard stack (Typer + Rich versions): HIGH — verified on PyPI 2026-02-19/2026-02-21
- Architecture (async queue wiring): HIGH — directly matches existing orchestrator API (human_out/human_in, cancel_agent, inject_guidance already built)
- Display pattern (Rich Live + asyncio): MEDIUM — documented in Rich discussions, pattern is established but nuances of Rich Live thread-safety are best verified in Wave 0 tests
- Pitfalls: HIGH — derived from project codebase patterns (asyncio.to_thread already used throughout Phases 3-7)

**Research date:** 2026-03-11
**Valid until:** 2026-06-11 (Typer/Rich are stable; check for breaking changes if > 90 days)
