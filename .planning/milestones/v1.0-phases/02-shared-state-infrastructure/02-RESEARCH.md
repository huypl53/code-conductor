# Phase 2: Shared State Infrastructure - Research

**Researched:** 2026-03-10
**Domain:** Python concurrent file I/O, Pydantic v2 data modeling, atomic writes, file locking
**Confidence:** HIGH

## Summary

Phase 2 implements the single coordination backbone for Conductor: a `.conductor/state.json` file that multiple processes (orchestrator + sub-agents) can read and write safely. The two hard problems are (1) preventing corruption from concurrent writes, and (2) defining a clear, validated schema for tasks, agents, and dependencies that all consumers agree on.

The standard Python solution for cross-process file locking is `filelock` 3.x (maintained by the tox-dev organization, production-stable). It wraps OS-level primitives (`fcntl.flock` on Unix, `msvcrt.locking` on Windows) and falls back to `SoftFileLock` on exotic filesystems. Pydantic v2 `BaseModel` provides schema-validated serialization/deserialization; `model_dump_json()` + `model_validate_json()` is the canonical round-trip. Atomic writes use the write-to-temp-then-`os.replace` pattern, which is POSIX-guaranteed atomic and Python stdlib only.

The combination — acquire lock → read → mutate → write to temp → `os.replace` → release lock — prevents both torn reads and torn writes. This is the pattern used in production state-management systems and requires no third-party atomic-write library.

**Primary recommendation:** `filelock` for cross-process locking + `pydantic` v2 `BaseModel` for schema + stdlib `os.replace` for atomic commit. No custom locking code. No custom serializer.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CORD-01 | Shared state file (`.conductor/state.json`) tracks all tasks, agent assignments, status, outputs, and interfaces | Pydantic models define `Task`, `AgentRecord`, `Dependency`, `ConductorState` schema; `StateManager` reads/writes to `.conductor/state.json` |
| CORD-02 | Orchestrator writes task assignments and resolves conflicts in shared state | `StateManager.write_tasks()` / `assign_task()` acquires filelock before mutation; orchestrator role documented in schema |
| CORD-03 | Sub-agents update their own task status and outputs in shared state | `StateManager.update_task_status()` accepts agent identity + task ID; uses same filelock pattern |
| CORD-06 | Task list is visible to all agents — each agent can see what others are working on and their status | `StateManager.read_state()` returns full `ConductorState`; no per-agent filtering |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| filelock | 3.25.1 | Cross-process file locking | OS-level primitives, tox-dev maintained, zero dependencies, production-stable |
| pydantic | 2.12.x | Schema definition + JSON validation | Industry standard for Python data models; `model_validate_json` / `model_dump_json` are the canonical round-trip |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=8 (already in dev deps) | Test framework | All tests — already configured in Phase 1 |
| stdlib: `os`, `tempfile`, `pathlib` | stdlib | Atomic writes, path handling | No extra install needed |
| stdlib: `enum` (`StrEnum`) | Python 3.11+ | Status enumerations | Task/agent status fields |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `filelock` | `fcntl` directly | Platform-specific (Unix only); filelock handles Windows + fallback |
| `filelock` | `portalocker` | portalocker is older and less actively maintained; filelock is the tox-dev standard |
| `pydantic` BaseModel | plain `dataclasses` + `json` | No validation; runtime errors instead of parse-time errors; harder to extend |
| `os.replace` atomic pattern | `atomicwrites` library | `atomicwrites` is unmaintained; `os.replace` is stdlib and POSIX-atomic |

**Installation:**
```bash
# In packages/conductor-core/pyproject.toml [project] dependencies:
# "filelock>=3.16",
# "pydantic>=2.10",
uv add filelock pydantic --directory packages/conductor-core
```

## Architecture Patterns

### Recommended Project Structure
```
packages/conductor-core/src/conductor/state/
├── __init__.py          # Public API: StateManager, re-exports models
├── models.py            # Pydantic models: ConductorState, Task, AgentRecord, Dependency
├── manager.py           # StateManager class: read/write/update operations
└── errors.py            # StateError, StateLockTimeout, StateCorrupted
packages/conductor-core/tests/
└── test_state.py        # All state tests
.conductor/              # Runtime directory (gitignored, created on first use)
└── state.json           # Live state file
```

### Pattern 1: File-Locked Atomic Read-Modify-Write

**What:** Acquire exclusive lock on `.lock` file, read current JSON, apply mutation, write to temp file in same directory, `os.replace` to target, release lock.

**When to use:** Any write to `state.json` (task assignment, status update, output append).

**Example:**
```python
# Source: filelock docs (https://py-filelock.readthedocs.io/) + stdlib os.replace
import json
import os
import tempfile
from pathlib import Path
from filelock import FileLock, Timeout

class StateManager:
    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path
        self._lock_path = state_path.with_suffix(".json.lock")

    def _atomic_write(self, data: str) -> None:
        """Write atomically: temp file in same dir, then os.replace."""
        dir_ = self._state_path.parent
        dir_.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())  # durability before rename
            os.replace(tmp_path, self._state_path)  # atomic on POSIX
        except Exception:
            os.unlink(tmp_path)  # clean up on failure
            raise

    def read_state(self) -> "ConductorState":
        """Read-only: no lock needed for reads (JSON is atomic after os.replace)."""
        if not self._state_path.exists():
            return ConductorState()
        return ConductorState.model_validate_json(self._state_path.read_text())

    def mutate(self, fn: Callable[[ConductorState], None], timeout: float = 10.0) -> ConductorState:
        """Acquire lock, read, apply fn, write back."""
        lock = FileLock(str(self._lock_path), timeout=timeout)
        try:
            with lock:
                state = self.read_state()
                fn(state)
                self._atomic_write(state.model_dump_json(indent=2))
                return state
        except Timeout:
            raise StateLockTimeout(f"Could not acquire state lock within {timeout}s")
```

### Pattern 2: Pydantic Schema for `ConductorState`

**What:** Define the full state schema with `BaseModel`. Use `StrEnum` for status fields. Use `datetime` with UTC for timestamps. Use `model_config = ConfigDict(use_enum_values=True)` so enums serialize to their string values in JSON.

**When to use:** Defining all data structures; guarantees JSON round-trip fidelity and validation at parse time.

**Example:**
```python
# Source: Pydantic v2 docs (https://docs.pydantic.dev/latest/concepts/models/)
from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"

class AgentStatus(StrEnum):
    IDLE = "idle"
    WORKING = "working"
    WAITING = "waiting"
    DONE = "done"

class Task(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AgentRecord(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    name: str
    role: str
    current_task_id: str | None = None
    status: AgentStatus = AgentStatus.IDLE
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Dependency(BaseModel):
    task_id: str        # task that depends on another
    depends_on: str     # task ID it depends on

class ConductorState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    version: str = "1"
    tasks: list[Task] = Field(default_factory=list)
    agents: list[AgentRecord] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

### Pattern 3: Testing Concurrent Writes with `multiprocessing`

**What:** Spawn two Python processes via `multiprocessing`, each performing N writes to the same `state.json` under the same lock, assert no task entries are lost after both finish.

**When to use:** CORD-02 concurrent-write test — proves filelock prevents races.

**Example:**
```python
import multiprocessing
from pathlib import Path

def worker_write(state_path: str, agent_id: str, n: int) -> None:
    """Write n tasks as a specific agent."""
    mgr = StateManager(Path(state_path))
    for i in range(n):
        def add_task(state: ConductorState) -> None:
            state.tasks.append(Task(id=f"{agent_id}-{i}", title=f"task {i}"))
        mgr.mutate(add_task)

def test_concurrent_writes_no_corruption(tmp_path: Path) -> None:
    state_path = tmp_path / ".conductor" / "state.json"
    p1 = multiprocessing.Process(target=worker_write, args=(str(state_path), "orch", 10))
    p2 = multiprocessing.Process(target=worker_write, args=(str(state_path), "agent1", 10))
    p1.start(); p2.start()
    p1.join(); p2.join()
    assert p1.exitcode == 0
    assert p2.exitcode == 0
    final = StateManager(state_path).read_state()
    assert len(final.tasks) == 20  # no writes lost
```

### Anti-Patterns to Avoid

- **Lock on the state file itself:** Lock a separate `.lock` file; locking the target file directly is fragile across platforms.
- **Read without lock, write with lock:** Torn reads are possible if another process replaces the file between your read and write. Always read inside the lock when doing read-modify-write.
- **Lock file in /tmp:** Must be in the same directory as `state.json` to ensure `os.replace` is atomic (same filesystem).
- **Using `json.dump` directly to the target file:** Non-atomic; partial write on crash produces corrupted JSON. Always write to temp then rename.
- **Storing absolute paths in state.json:** Breaks portability. Store relative paths or path-independent identifiers.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process file locking | Custom `fcntl`/`msvcrt` wrapper | `filelock` | Handles platform differences, stale lock detection, timeout, reentrancy |
| JSON schema + validation | Manual dict parsing with `isinstance` | Pydantic v2 `BaseModel` | Validators, error messages, round-trip guarantee, future extensibility |
| Atomic file writes | Custom temp + rename | stdlib `os.replace` + `tempfile.mkstemp` | POSIX-atomic, handles same-filesystem constraint, no extra dep |
| Status constants | Plain string constants | `StrEnum` | Type-safe, IDE autocomplete, validates on deserialization |

**Key insight:** The three primitives (filelock + pydantic + os.replace) each handle a distinct failure mode. Removing any one opens a specific corruption scenario: no lock = torn concurrent write; no pydantic = schema drift causes silent data loss; no atomic write = crash mid-write produces unreadable JSON.

## Common Pitfalls

### Pitfall 1: Lock File on a Different Filesystem Than State File
**What goes wrong:** `os.replace(tmp, target)` raises `OSError: [Errno 18] Invalid cross-device link` if temp file is in `/tmp` and target is in `/home/user/.conductor/`.
**Why it happens:** `tempfile.mkstemp()` defaults to the system temp directory, which may be a different mount.
**How to avoid:** Always pass `dir=state_path.parent` to `tempfile.mkstemp()`.
**Warning signs:** Tests pass on a single machine but fail in Docker with mounted volumes.

### Pitfall 2: `FileLock` Timeout Not Set — Hangs Forever
**What goes wrong:** A crashed process leaves the lock held (on some systems). The next process hangs indefinitely.
**Why it happens:** `FileLock` default `timeout=-1` (no timeout) blocks forever.
**How to avoid:** Always specify a `timeout` (e.g., 10 seconds). Catch `filelock.Timeout` and surface it as `StateLockTimeout`.
**Warning signs:** A test hangs and never completes.

### Pitfall 3: `SoftFileLock` Stale Lock After Crash
**What goes wrong:** `SoftFileLock` (used when OS primitives aren't available) checks the PID in the lock file. On PID reuse, it may think a dead process is alive and refuse to acquire.
**Why it happens:** PID reuse in Linux is common when running many short-lived processes.
**How to avoid:** Use `FileLock` (OS-level), not `SoftFileLock`, on Linux/macOS/Windows. `SoftFileLock` is only the fallback for exotic filesystems.
**Warning signs:** Tests show `Timeout` exceptions that shouldn't happen.

### Pitfall 4: Enum Serialization Gotcha — Pydantic v2 + StrEnum
**What goes wrong:** Fields typed as `TaskStatus` serialize as `"TaskStatus.pending"` (the repr) instead of `"pending"` (the value) if `use_enum_values=True` is missing.
**Why it happens:** Without `ConfigDict(use_enum_values=True)`, Pydantic v2 serializes the enum member itself, and `json.dumps` falls back to `repr`.
**How to avoid:** Use `StrEnum` (inherits from `str`) + `ConfigDict(use_enum_values=True)` on every model that contains enum fields. `model_dump_json()` will always produce clean string values.
**Warning signs:** `state.json` contains `"status": "TaskStatus.pending"` instead of `"status": "pending"`.

### Pitfall 5: Concurrent Test Isolation
**What goes wrong:** Concurrent write tests using `multiprocessing` inherit the parent's open file handles, which can confuse the lock state.
**Why it happens:** `fork()` duplicates file descriptors; the child may already hold references to locks the parent opened.
**How to avoid:** Use `multiprocessing.Process` with `start_method="spawn"` (not `fork`) in tests, or ensure worker functions are standalone and import `StateManager` fresh. In the test worker, construct `StateManager` from scratch.
**Warning signs:** `p1.exitcode` is non-zero; lock error in worker despite no contention.

## Code Examples

### Full Read-Modify-Write Cycle
```python
# Source: filelock docs + pydantic v2 docs
def assign_task(self, task_id: str, agent_id: str) -> None:
    def _assign(state: ConductorState) -> None:
        for task in state.tasks:
            if task.id == task_id:
                task.assigned_agent = agent_id
                task.status = TaskStatus.IN_PROGRESS
                task.updated_at = datetime.now(timezone.utc)
                break
    self.mutate(_assign)

def update_task_status(self, task_id: str, status: TaskStatus, output: dict[str, Any] | None = None) -> None:
    def _update(state: ConductorState) -> None:
        for task in state.tasks:
            if task.id == task_id:
                task.status = status
                task.updated_at = datetime.now(timezone.utc)
                if output:
                    task.outputs.update(output)
                break
    self.mutate(_update)
```

### State Directory Bootstrap
```python
# Create .conductor/ directory on first use
def _ensure_dir(self) -> None:
    self._state_path.parent.mkdir(parents=True, exist_ok=True)
```

### JSON Round-Trip Test Pattern
```python
def test_task_round_trip(tmp_path: Path) -> None:
    mgr = StateManager(tmp_path / ".conductor" / "state.json")
    task = Task(id="t1", title="Write auth module", description="Implement JWT auth")
    def add(state: ConductorState) -> None:
        state.tasks.append(task)
    mgr.mutate(add)
    loaded = mgr.read_state()
    assert loaded.tasks[0].id == "t1"
    assert loaded.tasks[0].status == "pending"  # StrEnum value, not member
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `lockfile` (abandoned) | `filelock` (tox-dev) | ~2018 | Active maintenance, async support, SQLite-backed read-write lock variant |
| Pydantic v1 `class Config` | Pydantic v2 `ConfigDict` | Pydantic 2.0 (2023) | Breaking change — `class Config` is deprecated, use `model_config = ConfigDict(...)` |
| `atomicwrites` library | stdlib `os.replace` + `tempfile.mkstemp` | `atomicwrites` abandoned ~2021 | No external dependency needed |
| Python `str(Enum)` for JSON | `StrEnum` (Python 3.11+) | Python 3.11 | Clean string values without subclassing tricks |

**Deprecated/outdated:**
- `atomicwrites` PyPI package: unmaintained since 2021, do not use
- `lockfile` PyPI package: abandoned, do not use
- Pydantic v1 `class Config` inner class: deprecated in v2, use `model_config = ConfigDict(...)`

## Open Questions

1. **Max state file size / performance at scale**
   - What we know: JSON read/write is synchronous; at Phase 2 scale (dozens of tasks) this is negligible.
   - What's unclear: At what task count does synchronous JSON become a bottleneck?
   - Recommendation: Not a Phase 2 concern — design for correctness now, profile later. Schema is extensible.

2. **State migration versioning**
   - What we know: `ConductorState.version` field is included in the schema.
   - What's unclear: Migration logic between schema versions is not needed for Phase 2 but will be needed by Phase 3+.
   - Recommendation: Include `version: str = "1"` in the schema now; don't implement migration in Phase 2.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `packages/conductor-core/pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_state.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CORD-01 | Task, AgentRecord, Dependency written and read back with full fidelity | unit | `uv run pytest tests/test_state.py::test_task_round_trip -x` | Wave 0 |
| CORD-01 | ConductorState contains tasks, agents, dependencies after write | unit | `uv run pytest tests/test_state.py::test_full_state_round_trip -x` | Wave 0 |
| CORD-02 | Concurrent writes from two processes do not corrupt state.json | integration | `uv run pytest tests/test_state.py::test_concurrent_writes_no_corruption -x` | Wave 0 |
| CORD-02 | Orchestrator can write a task assignment | unit | `uv run pytest tests/test_state.py::test_assign_task -x` | Wave 0 |
| CORD-03 | Sub-agent can update its own task status | unit | `uv run pytest tests/test_state.py::test_update_task_status -x` | Wave 0 |
| CORD-03 | Orchestrator can observe the sub-agent's status change | unit | `uv run pytest tests/test_state.py::test_orchestrator_observes_status -x` | Wave 0 |
| CORD-06 | All agents see the full task list with every task visible | unit | `uv run pytest tests/test_state.py::test_all_tasks_visible -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_state.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `packages/conductor-core/tests/test_state.py` — covers all CORD-01, CORD-02, CORD-03, CORD-06 tests (file does not exist yet)
- [ ] `packages/conductor-core/src/conductor/state/models.py` — Pydantic models
- [ ] `packages/conductor-core/src/conductor/state/manager.py` — StateManager class
- [ ] `packages/conductor-core/src/conductor/state/errors.py` — StateError, StateLockTimeout

## Sources

### Primary (HIGH confidence)
- `filelock` PyPI 3.25.1 (https://pypi.org/project/filelock/) — current version, production status confirmed
- filelock ReadTheDocs (https://py-filelock.readthedocs.io/en/latest/) — API reference, lock types, context manager pattern
- filelock API reference (https://py-filelock.readthedocs.io/en/latest/api.html) — timeout parameter, FileLock vs SoftFileLock
- Pydantic v2 Models docs (https://docs.pydantic.dev/latest/concepts/models/) — model_validate_json, model_dump_json, ConfigDict
- Pydantic v2 JSON docs (https://docs.pydantic.dev/latest/concepts/json/) — JSON-specific parsing performance, jiter integration
- Pydantic PyPI 2.12.5 (https://pypi.org/project/pydantic/) — current version confirmed

### Secondary (MEDIUM confidence)
- Python `os.replace` atomic semantics — POSIX standard, verified via Python docs and multiple sources; `rename()` atomic on same filesystem
- `StrEnum` (Python 3.11+) + `ConfigDict(use_enum_values=True)` pattern — verified via pydantic discussion threads and official enum docs

### Tertiary (LOW confidence)
- Concurrent test isolation notes on `multiprocessing` `spawn` vs `fork` — from pytest GitHub issues; behavior verified conceptually but not tested against this exact codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — filelock and pydantic versions verified against PyPI; both are production-stable with active maintenance
- Architecture: HIGH — atomic write + filelock pattern is well-established POSIX pattern; pydantic round-trip is documented
- Pitfalls: HIGH — cross-filesystem temp file and enum serialization pitfalls verified against official sources and known pydantic issue tracker

**Research date:** 2026-03-10
**Valid until:** 2026-09-10 (stable ecosystem; pydantic minor versions may add features but API is stable)
