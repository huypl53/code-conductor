# Pitfalls Research

**Domain:** Adding a Textual TUI to an existing Python asyncio application (Conductor v2.0)
**Researched:** 2026-03-11
**Confidence:** HIGH (Textual official docs + GitHub issues + codebase analysis)

---

## Critical Pitfalls

### Pitfall 1: Textual Owns the Event Loop — No Cohabitation with asyncio.run()

**What goes wrong:**
`App.run()` calls `asyncio.run()` internally, which creates a new event loop. The current codebase already runs an event loop via the orchestrator coroutines, the FastAPI/uvicorn server, and the Claude Agent SDK's async generator. If any of these subsystems also call `asyncio.run()` — or if the Textual app is started from within a running loop — Python raises `RuntimeError: This event loop is already running`.

**Why it happens:**
Developers assume Textual "wraps" their existing async code. It does not. Textual creates and owns a fresh event loop. The existing prompt_toolkit approach uses `patch_stdout()` to coexist with Rich in a shared loop, but Textual's architecture is fundamentally different — it is the event loop owner, not a guest.

The existing code in `chat.py` calls `asyncio.shield()`, `asyncio.create_task()`, and prompt_toolkit's `PromptSession.prompt_async()` all within one loop. That loop must become Textual's loop, not a separate one.

**How to avoid:**
- Start Textual as the top-level `asyncio.run()` entry point. All other async work (Claude Agent SDK queries, orchestrator delegation, FastAPI server) must run as Textual workers or as tasks on Textual's loop.
- For FastAPI/uvicorn: use `uvicorn.Server` with `Config` and `await server.serve()` as a Textual async worker — never `uvicorn.run()` which calls `asyncio.run()` internally.
- The Claude Agent SDK's `ClaudeSDKClient.connect()` / `receive_response()` are async coroutines; they compose naturally into Textual workers once the event loop ownership is settled.
- Do not reach for `nest_asyncio` as a fix — it masks the symptom and fails in production async contexts.

**Warning signs:**
- `RuntimeError: This event loop is already running` at startup
- Tests that worked with `asyncio.run()` now hang or fail
- `nest_asyncio` appearing as a "fix" in any PR

**Phase to address:**
Phase 1 (Skeleton / event loop architecture) — the entry-point design must be resolved before any UI work begins.

---

### Pitfall 2: Stdout/Stderr Corruption — Rich Console Writes Fight Textual's Renderer

**What goes wrong:**
The current codebase writes directly to stdout/stderr via `Console(stderr=True, highlight=False)` at arbitrary times. Textual takes exclusive control of the terminal when running. Any `print()`, `console.print()`, or Rich `Console` write that bypasses Textual's renderer causes partial overwrite of the TUI layout, garbled output, and invisible text painted behind widget regions.

Specifically, the `_status_updater()` and `_clear_status_lines()` in `delegation.py` use raw ANSI escape codes (`\033[A\033[2K`) to overwrite lines. These escape codes are invisible to Textual's compositor and will corrupt the display.

**Why it happens:**
prompt_toolkit's `patch_stdout()` context manager temporarily re-routes stdout so Rich prints appear above the input prompt — a hack that works because prompt_toolkit renders only a single input line. Textual renders the entire screen; there is no "safe" region for external writes.

Textual intercepts `print()` and routes it to devtools (or `/dev/null` if devtools is off). But `Console` objects that write directly to `sys.stderr` bypass this capture.

**How to avoid:**
- Remove all `Console.print()` calls from business logic during TUI lifetime. Route all output through Textual widget updates: `RichLog.write()`, `Static.update()`, or custom `Message` + handler chains.
- The `_status_updater` / `_clear_status_lines` pattern must be replaced entirely by a Textual widget that owns a status panel. ANSI cursor manipulation has no equivalent in Textual — use reactive attributes on a `Static` widget instead.
- The `Console(stderr=True, highlight=False)` instances in `delegation.py`, `input_loop.py`, and `display.py` must be removed from all code paths that run while the TUI is active.

**Warning signs:**
- Terminal shows garbled output or flashing during delegation runs
- Textual layout "glitches" after each orchestrator status update
- Text appears and immediately disappears or overlaps widgets

**Phase to address:**
Phase 1 (entry-point refactor) and Phase 2 (first widget), because the output routing architecture must be defined before any streaming display is built.

---

### Pitfall 3: Claude Agent SDK Subprocess Output Leaks Into the Terminal

**What goes wrong:**
The Claude Agent SDK runs the Claude Code CLI as a subprocess. That subprocess can write to stdout/stderr directly, bypassing both Textual's capture and the Python-level `print()` intercept. During streaming, raw bytes from the subprocess paint over the Textual TUI.

**Why it happens:**
Python's `begin_capture_print()` only intercepts Python-level `sys.stdout` / `sys.stderr` writes. Child processes get their own file descriptors inherited from the parent. If the SDK subprocess inherits the terminal's stdout, it can write to it independently of the Textual app.

**How to avoid:**
- Verify what the Claude Agent SDK subprocess inherits for stdout/stderr. Redirect subprocess stdout/stderr to `PIPE` if the SDK supports it (inspect `ClaudeAgentOptions` for pipe settings or `capture_output`).
- If the SDK does not expose pipe configuration, wrap the subprocess launch so that its stdout/stderr are redirected to asyncio queues before the Textual app starts.
- Route all streamed SDK messages through `async for message in client.receive_response()` — which the existing code already does correctly. The risk is only if the subprocess also writes to the inherited terminal fd independently.

**Warning signs:**
- Raw JSON or ANSI escape sequences appear in the TUI outside of widget boundaries
- `[ERROR]` or subprocess error messages paint over the layout
- TUI becomes partially unresponsive after SDK subprocess exit

**Phase to address:**
Phase 1 (SDK integration architecture) — verify subprocess fd inheritance before the first widget is built.

---

### Pitfall 4: Thread Safety Violations When Updating Widgets from Workers

**What goes wrong:**
The orchestrator (`delegation.py`) spawns `asyncio.Task` objects for `_status_updater` and `_escalation_listener`. These tasks currently call `self._console.print()` directly. In the Textual world, calling widget methods from a worker task that runs in a different asyncio context (or a thread) causes `NoActiveAppError` or silently drops updates.

More broadly: Textual is not thread-safe. Any update to a widget must happen on the Textual event loop's thread via the widget's own coroutines, `call_from_thread()` (for thread workers), or `post_message()`.

**Why it happens:**
The existing code in `delegation.py` uses `asyncio.create_task()` for background updates. Under Textual, the context variable that identifies the active app may not propagate to tasks created outside of Textual's startup context, especially in Python < 3.11.

**How to avoid:**
- Convert `_status_updater` to a Textual `@work` async worker; use `self.app.call_from_thread()` or widget `post_message()` for any UI update from within it.
- For thread workers (SDK subprocess I/O): always use `App.call_from_thread()` to update reactive attributes or call widget methods.
- Prefer posting Textual `Message` subclasses and handling them in `on_*` handlers — this is the idiomatic, thread-safe pattern.
- Check `worker.is_cancelled` before any UI update in long-running workers to avoid race conditions during shutdown.

**Warning signs:**
- `NoActiveAppError` exceptions in worker tasks
- Widget state updates that appear to be silently dropped
- Status lines stop updating mid-delegation without error

**Phase to address:**
Phase 2 (delegation status panel) — the `_status_updater` is the first multi-task interaction with the TUI.

---

### Pitfall 5: asyncio Task Garbage Collection — "Fire and Forget" Workers Die Silently

**What goes wrong:**
`asyncio.create_task()` returns a `Task` object. If that reference is not stored somewhere (a list, a set, an instance variable), Python's garbage collector can delete the task mid-execution. The task's code stops running silently, with no exception and no log entry. This is the "Heisenbug" documented by Textual.

In `delegation.py`, `_status_task` and `_escalation_task` are stored as instance variables — correctly. But if any future phase adds "fire and forget" tasks (e.g., for streaming token updates, background health checks), they will disappear under GC pressure.

**Why it happens:**
Unlike threads, asyncio tasks do not keep themselves alive. The event loop only holds a weak reference. Once no strong reference remains in user code, GC is free to collect the task.

**How to avoid:**
- Use a module-level or app-level `_background_tasks: set[asyncio.Task]` and call `task.add_done_callback(_background_tasks.discard)` for any task that must outlive its creator's scope.
- Prefer Textual's `@work` decorator over raw `create_task()` — Textual's `WorkerManager` holds references automatically.
- Code review trigger: search for `asyncio.create_task(` without an accompanying variable assignment or `_background_tasks.add()` call.

**Warning signs:**
- Background updates work in development (where GC rarely fires) but drop intermittently in production
- Worker count stays at zero despite active tasks being expected
- Status displays freeze after a few seconds without error

**Phase to address:**
Phase 1 (architecture) — establish a convention for background tasks before any phase spawns them.

---

### Pitfall 6: High-Frequency Streaming Causes TUI Flicker and Input Lag

**What goes wrong:**
The current code streams tokens by calling `self._console.print(chunk, end="")` for every `text_delta` event. In Textual, calling `widget.update()` or `rich_log.write()` for every single token triggers a full widget refresh cycle (layout → compositor → render → output). At typical LLM streaming speeds (20-60 tokens/second across multiple concurrent agents), this saturates the compositor and causes visible flicker and input lag.

**Why it happens:**
Textual's compositor is optimized for partial updates but still has overhead per update cycle. The `RichLog` widget specifically notes that "a downside of widgets that return Rich renderables is that Textual will redraw the entire widget when its state is updated." When multiple agent streams write simultaneously, the update rate can exceed 100 updates/second.

**How to avoid:**
- Batch streaming token updates: accumulate chunks in a buffer and flush to the widget on a timer (e.g., `set_interval(0.05, flush_buffer)` — 20fps max update rate).
- Use `RichLog` for streaming output (it is designed for append-only real-time logs and is more efficient than `Static` for this pattern).
- Do not use `Static.update()` for token-by-token streaming — it re-renders the entire widget on each call.
- For concurrent agent panels, use Textual's reactive batching: modifying multiple reactive attributes triggers only a single refresh cycle.
- Set `max_lines` on `RichLog` to prevent unbounded memory growth during long agent runs.

**Warning signs:**
- TUI becomes unresponsive during active streaming
- Visible "tearing" or flicker in the streaming cell
- Input keystrokes are dropped or delayed during high-output phases
- CPU usage spikes to 100% during streaming

**Phase to address:**
Phase 2 (streaming cell / transcript widget) — the buffering strategy must be baked in from the first streaming implementation.

---

### Pitfall 7: Modal Approval Overlays Block the Event Loop Without Proper Async Suspension

**What goes wrong:**
The current escalation bridge in `delegation.py` collects human input via `await self._input_fn("  Reply> ")` which wraps prompt_toolkit's `prompt_async()`. In Textual, modal approval dialogs must be implemented via Textual's screen stack using `await self.app.push_screen_wait()`. If a developer tries to replicate the current pattern using `asyncio.Queue.get()` awaited inside a Textual worker without properly suspending the application UI, the modal "blocks" but the TUI continues rendering — the user can click buttons that should be disabled.

**Why it happens:**
The mental model from prompt_toolkit (where input blocks the loop) does not transfer to Textual (where the loop runs continuously and input is event-driven). Approval workflows require a suspend/resume pattern using Textual's screen lifecycle.

**How to avoid:**
- Use `app.push_screen_wait(ApprovalScreen(...))` which correctly suspends the caller and resumes when the modal screen is dismissed with a result.
- The escalation queue (`human_out` / `human_in`) in `delegation.py` must be bridged via a Textual `Message` + modal screen pair: when `human_out.get()` fires, post a message to the app which pushes the approval screen.
- Never block a Textual async worker with `await queue.get()` while expecting the TUI to remain fully interactive — the worker will freeze its task but the event loop continues, leaving UI state inconsistent.

**Warning signs:**
- Approval screen appears but background agent panels continue updating unexpectedly
- User can interact with elements that should be blocked during approval
- `push_screen_wait()` deadlock if called from a non-app coroutine

**Phase to address:**
Phase 3 (modal approval overlays) — the entire escalation bridge must be redesigned around Textual's screen stack, not asyncio queues.

---

### Pitfall 8: prompt_toolkit Keybindings and Input Semantics Are Not Portable

**What goes wrong:**
The current `ChatSession` uses prompt_toolkit for vi mode, `Ctrl+G` to open editor, `Ctrl+C` cancellation, `InMemoryHistory`, and `patch_stdout()`. None of these APIs exist in Textual. Attempting to run prompt_toolkit alongside Textual in the same terminal session fails catastrophically because both frameworks try to own terminal raw mode (termios settings).

Specific migration gaps:
- `PromptSession.prompt_async()` → must become Textual's `Input` widget with `on_input_submitted` handler
- `vi_mode=True` → Textual's `Input` has no built-in vi mode; requires custom key binding via `@on(Key)` handlers
- `InMemoryHistory` → must be reimplemented with a Python `deque` and `Up`/`Down` key handlers
- `open_in_editor()` via `Ctrl+G` → must use `app.suspend()` to temporarily release the terminal, launch editor, then resume
- `patch_stdout()` → entirely replaced by Textual's rendering; no equivalent needed

**Why it happens:**
prompt_toolkit and Textual are both full terminal-ownership frameworks. They cannot coexist in the same terminal session. The migration is a clean replacement, not an extension.

**How to avoid:**
- Remove `from prompt_toolkit import ...` entirely from all modules that will run while Textual is active.
- Implement input history with a simple Python `deque` and wire `Key("up")`/`Key("down")` bindings on an `Input` widget.
- Implement `app.suspend()` for editor integration — Textual provides this built-in to safely release and recapture the terminal.
- Accept that vi-mode keybindings require custom implementation; do not block TUI work on feature parity with the old system.

**Warning signs:**
- `import prompt_toolkit` anywhere in code paths that run after `App.run()` starts
- Two terminal raw-mode owners fighting → terminal left in broken state on exit
- `KeyboardInterrupt` from prompt_toolkit firing inside Textual's event loop

**Phase to address:**
Phase 1 (entry-point refactor) — prompt_toolkit must be fully removed from the startup path before any Textual code runs.

---

### Pitfall 9: Textual Testing and pytest-asyncio Fixture Incompatibility

**What goes wrong:**
`App.run_test()` creates asyncio context variables to track the active app. In pytest, fixtures and test functions run in different asyncio tasks. Context variables from a fixture's task do not propagate to the test function's task, causing `NoActiveAppError` when the test tries to query widget state. This is a known incompatibility documented in Textual GitHub issue #4998.

A secondary issue: if any test calls `asyncio.run()` directly (e.g., a non-Textual unit test earlier in the suite), subsequent calls to `pytest-textual-snapshot`'s `snap_compare` fixture fail with `RuntimeError: There is no current event loop in thread 'MainThread'` (GitHub issue #5788).

**Why it happens:**
pytest-asyncio creates a fresh event loop per test. Fixtures run in their own coroutine context. When `run_test()` stores app context in a `contextvars.ContextVar`, that context is not inherited by tests in a different task on the same loop.

**How to avoid:**
- Put `async with app.run_test() as pilot:` directly inside the test function, not in a pytest fixture.
- Use `pytest-asyncio >= 0.25.0` with Python >= 3.11 where context propagation is fixed.
- Ensure `asyncio_mode = "auto"` in `pyproject.toml` to avoid per-test `@pytest.mark.asyncio` decoration.
- Keep Textual snapshot tests (`snap_compare`) in a separate test file from non-Textual asyncio tests to prevent loop contamination.
- Never mix `asyncio.run()` calls in a pytest session that also runs Textual tests.

**Warning signs:**
- `NoActiveAppError` in test output
- Tests pass when run individually but fail when run with the full suite
- `RuntimeError: There is no current event loop` only after certain test ordering

**Phase to address:**
Phase 1 (test infrastructure setup) — establish testing patterns before any widget tests are written.

---

### Pitfall 10: FastAPI/Uvicorn WebSocket Server Cannot Use uvicorn.run() Inside Textual

**What goes wrong:**
The existing `dashboard/server.py` can be launched via `uvicorn.run(create_app(...), ...)`. Inside a Textual app, `uvicorn.run()` calls `asyncio.run()` internally, which raises `RuntimeError: This event loop is already running` because Textual already owns the loop.

Additionally, the current `create_app()` uses `asyncio.Event()` and `asyncio.create_task()` in a `lifespan` context manager that assumes a running loop at module init time. This is fine when uvicorn runs its own loop but causes `DeprecationWarning: There is no current event loop` under Python 3.12+ if triggered at import time.

**Why it happens:**
`uvicorn.run()` is designed as a top-level entrypoint. It always creates a new event loop. The `uvicorn.Config` + `uvicorn.Server` approach with `await server.serve()` is the correct way to run uvicorn inside an existing event loop.

**How to avoid:**
- Replace `uvicorn.run(...)` with the `uvicorn.Config` + `uvicorn.Server` pattern and run it as a Textual async worker:
  ```python
  config = uvicorn.Config(app, host="localhost", port=8765)
  server = uvicorn.Server(config)
  await server.serve()  # awaitable — runs in Textual's event loop
  ```
- The `asyncio.Event()` and `asyncio.create_task()` in `create_app()`'s lifespan must only execute after Textual's event loop has started — ensure `create_app()` is called from within an `on_mount` handler or a worker, not at module import.

**Warning signs:**
- `RuntimeError: This event loop is already running` when the dashboard worker starts
- FastAPI WebSocket connections work but state watcher events are not broadcast (loop isolation)
- `DeprecationWarning: There is no current event loop` during import

**Phase to address:**
Phase 4 (web dashboard coexistence) — the uvicorn integration change is isolated but must be done before the dashboard worker is tested.

---

### Pitfall 11: Reactive Variable Updates Before Widget Is Mounted

**What goes wrong:**
Textual reactive attributes can trigger watchers during `__init__` or `compose()` — before the widget is mounted and its children are accessible via the DOM. If a watcher queries the DOM (e.g., `self.query_one(StatusLabel)`), it raises a `NoMatches` or `MountError` because the widget tree does not yet exist.

This is particularly relevant for the Conductor TUI, where reactive state (agent counts, streaming tokens, approval pending) will be set by background workers that may fire before the UI has fully initialized.

**Why it happens:**
Textual's reactive system triggers watchers immediately when a reactive attribute is set, regardless of mount state. Developers who set initial state in `__init__` or pass initial values to constructors trigger watchers prematurely.

**How to avoid:**
- Initialize reactive attributes to sentinel/default values in `__init__`; set their real initial values in `on_mount`.
- Use `set_reactive()` (the class-level method) when you must set a reactive before mount without triggering watchers.
- Guards in watchers: `if not self.is_attached: return` to short-circuit pre-mount updates.
- Prefer `compose()` for initial UI structure; reserve `on_mount` for all state initialization and first data loads.

**Warning signs:**
- `MountError: Can't mount widget(s) before <Widget> is mounted` in startup
- `NoMatches` exceptions in reactive watchers during app initialization
- Widgets that appear but show stale data from before mount completes

**Phase to address:**
Phase 2 (first widget) — establish the mount/reactive initialization convention before building complex compound widgets.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep Rich Console writes for "background log" paths | Avoids touching existing code | Console writes corrupt TUI; intermittent display bugs | Never during TUI lifetime |
| Use `nest_asyncio` to allow nested loops | Unblocks development quickly | Masks architectural flaws; fails in production async contexts; breaks pytest | Never — fix the architecture |
| Direct `widget.update()` per streaming token | Simple, obvious implementation | 20-60fps widget redraws; CPU saturation; input lag | Never for streaming; always batch |
| `asyncio.create_task()` without storing reference | Convenient | Silent GC-collected tasks; non-deterministic failures | Never for tasks that must complete |
| Run prompt_toolkit and Textual simultaneously | Preserves vi-mode keybindings short term | Two terminal raw-mode owners; terminal left broken on exit | Never |
| `App.run_test()` in pytest fixtures | DRY test setup | `NoActiveAppError` in all tests using that fixture | Never — use inline context manager |
| Global `Console` objects instantiated at module level | Convenient access | Console writes bypass Textual during TUI lifetime | Only in CLI-mode code paths that do not touch Textual |
| Set reactive attributes in `__init__` | Convenient initialization | Triggers watchers before mount; DOM queries fail | Never — use `on_mount` for real state initialization |

---

## Integration Gotchas

Common mistakes when connecting to external services or components.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Claude Agent SDK | Calling `asyncio.run(client.connect())` after Textual starts | `await client.connect()` inside a Textual async worker |
| Claude Agent SDK subprocess | Inheriting terminal stdout → subprocess writes over TUI | Ensure SDK subprocess uses piped I/O; validate on first integration |
| FastAPI/uvicorn | Using `uvicorn.run()` | `uvicorn.Config` + `uvicorn.Server` + `await server.serve()` as a worker |
| FastAPI lifespan tasks | `asyncio.create_task()` at app creation time | Create tasks only inside the lifespan context (after `yield`) |
| Rich Console output during delegation | `Console.print()` during active TUI | Post a Textual `Message`; update widget in handler |
| ANSI cursor manipulation | `\033[A\033[2K` escape codes for status clearing | Reactive `Static` widget; Textual manages cursor entirely |
| WebSocket state watcher | `state_watcher` uses `watchfiles` which runs in a thread | Wrap in `@work(thread=True)` + `call_from_thread()` for UI updates |
| Escalation queues | `await human_out.get()` blocking in a worker | `asyncio.Queue` + Textual `Message` + `push_screen_wait()` for modal |
| RichLog for streaming | Per-token `write()` calls | Buffer tokens; flush at fixed interval via `set_interval` |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-token `RichLog.write()` | TUI flicker, 100% CPU, dropped keystrokes | Buffer tokens; flush at 20fps via `set_interval` | > 10 tokens/second |
| Unbounded `RichLog` without `max_lines` | Memory growth; terminal scroll becomes slow | Set `max_lines=1000` or equivalent | After ~5 minutes of active streaming |
| Per-agent `Static` widget refreshing independently | Compositor overwhelmed with partial updates | Group agent panels; update via a single parent reactive | > 4 concurrent agents |
| `StateManager.read_state()` on every refresh tick | Disk I/O on asyncio loop thread blocks rendering | Run state reads in `asyncio.to_thread()`; cache last state | State files > 100KB |
| Rich `Table` re-rendered every 2 seconds | Full table re-render on each tick | Use a `DataTable` widget with row-level updates | > 20 agents |
| `asyncio.Queue` watchers consuming all events before TUI gets them | Escalation messages lost | Use Textual `Message` bus instead of raw queues for UI-bound events | Concurrent delegations |

---

## UX Pitfalls

Common user experience mistakes for this type of application.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Clearing terminal history on TUI exit | User loses context of what happened | Use `app.exit()` cleanly; preserve scroll history above the TUI region |
| Modal approval blocking all keyboard input | User cannot cancel or see agent progress | Keep agent panels visible during modal; allow Escape to defer approval |
| Streaming cell auto-scrolling fights manual scroll | User loses their place when reading output | Detect manual scroll; pause auto-scroll; show "jump to bottom" affordance |
| No visual distinction between current cell and history | User cannot tell where new output starts | Immutable cells with visual separator (border or rule) |
| Slash command autocomplete covers input history | Navigation ambiguous | Use a popup overlay, not an inline replacement of input text |
| Terminal resize corrupts layout | Widgets overflow or wrap unexpectedly | Handle `on_resize` event; use containers with `min_width` guards |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Textual app starts:** Verify that `app.run()` is the top-level entry point and nothing else calls `asyncio.run()` in the same process.
- [ ] **Streaming display works:** Verify that streaming tokens are buffered and flushed at a fixed rate, not written per-token. Run with 3 concurrent agents; confirm no flicker.
- [ ] **Delegation status panel:** Verify that `_status_updater` equivalent no longer uses `Console.print()` or ANSI cursor codes; all updates go through Textual widget reactivity.
- [ ] **Modal approval overlay:** Verify that `push_screen_wait()` is used; confirm that the TUI does not accept non-modal input while approval is pending.
- [ ] **FastAPI WebSocket server:** Verify that `uvicorn.Server.serve()` is awaited inside a Textual worker; confirm WebSocket events are received by the React dashboard during active TUI session.
- [ ] **Terminal restored on exit:** Verify that `app.exit()` or `app.run()` cleanup restores termios state. Run in tmux and confirm terminal is usable after exit.
- [ ] **SDK subprocess output:** Verify that no raw subprocess bytes appear outside widget boundaries during a full delegation run.
- [ ] **Tests pass in full suite:** Verify that Textual tests and non-Textual asyncio tests do not contaminate each other's event loops.
- [ ] **tmux/SSH compatibility:** Run inside tmux with `TERM=tmux-256color`; confirm colors render correctly and no TERM-related errors appear.
- [ ] **No prompt_toolkit imports:** Grep confirms zero `from prompt_toolkit` or `import prompt_toolkit` in any code path active under Textual.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Event loop ownership conflict | HIGH | Remove all `asyncio.run()` callers except Textual; refactor uvicorn and SDK launch into workers; may require 1-2 sprint phases to untangle |
| Console writes corrupting TUI | MEDIUM | Grep for all `console.print()` / `Console(` usages; route each through a Textual message or widget update; test after each change |
| Streaming performance saturation | MEDIUM | Add a `_token_buffer` list and `set_interval(0.05, _flush_buffer)` to the streaming widget; no architectural change required |
| Task GC killing background workers | LOW | Add `_background_tasks: set` store; add `add_done_callback(discard)` pattern; usually detectable in first integration test |
| pytest fixture / run_test incompatibility | LOW | Move `async with app.run_test()` into test body; upgrade pytest-asyncio; 30-minute fix |
| Terminal not restored on exit | MEDIUM | Ensure `app.run()` is in a `try/finally`; call `app.exit()` from signal handlers; test with `Ctrl+C` and process kill |
| prompt_toolkit coexistence attempt | HIGH | Cannot coexist; full removal required; vi-mode and editor features must be reimplemented from scratch in Textual |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Event loop ownership (Textual owns loop) | Phase 1: Architecture skeleton | Smoke test: app starts, SDK worker runs, no `RuntimeError` |
| Stdout/Console corruption | Phase 1: Entry-point + Phase 2: First widget | Full delegation run produces no console artifacts in TUI |
| SDK subprocess output leak | Phase 1: SDK integration audit | Run delegation; verify no raw subprocess bytes outside widgets |
| Thread safety / widget update safety | Phase 2: Delegation status panel | Status updates visible; no `NoActiveAppError` in logs |
| Task GC / fire-and-forget | Phase 1: Architecture + convention | Code review: no bare `create_task` without reference storage |
| Streaming performance | Phase 2: Streaming transcript cell | 3 concurrent agent streams at 30 tok/s; no flicker; CPU < 40% |
| Modal approval event loop | Phase 3: Approval overlays | Approval screen blocks input; agent panels still visible; dismisses cleanly |
| prompt_toolkit removal | Phase 1: Entry-point refactor | Zero `import prompt_toolkit` in any code path that runs under Textual |
| pytest / run_test incompatibility | Phase 1: Test infrastructure | Full test suite passes; no `NoActiveAppError`; no event loop contamination |
| uvicorn inside Textual | Phase 4: Dashboard coexistence | Dashboard WebSocket receives events while TUI is active |
| Reactive before mount | Phase 2: First widget | No `MountError` on startup; reactive watchers guard against pre-mount calls |

---

## Sources

- [Textual Workers guide](https://textual.textualize.io/guide/workers/) — thread safety, `call_from_thread`, `post_message` patterns (HIGH confidence — official)
- [Textual RichLog widget](https://textual.textualize.io/widgets/rich_log/) — performance characteristics, `max_lines` (HIGH confidence — official)
- [Textual: Algorithms for high-performance terminal apps (Dec 2024)](https://textual.textualize.io/blog/2024/12/12/algorithms-for-high-performance-terminal-apps/) — compositor partial updates, spatial indexing (HIGH confidence — official)
- [The Heisenbug lurking in your async code](https://textual.textualize.io/blog/2023/02/11/the-heisenbug-lurking-in-your-async-code/) — asyncio task GC problem (HIGH confidence — official)
- [GitHub issue #4998: App.run_test() incompatible with pytest fixtures](https://github.com/Textualize/textual/issues/4998) — context variable isolation root cause (HIGH confidence — official repo)
- [GitHub issue #5788: pytest-textual-snapshot fails after asyncio.run()](https://github.com/Textualize/textual/issues/5788) — event loop contamination in test suites (HIGH confidence — official repo)
- [GitHub issue #600: Documentation about adding other event loops](https://github.com/Textualize/textual/issues/600) — Textual event loop ownership (HIGH confidence — official repo)
- [Uvicorn: Running from inside a running loop](https://github.com/Kludex/uvicorn/discussions/2457) — `uvicorn.Server` + `Config` pattern for async contexts (MEDIUM confidence — maintainer discussion)
- [Textual Discussion #3254: Textual vs prompt_toolkit](https://github.com/Textualize/textual/discussions/3254) — architectural differences (HIGH confidence — official repo)
- [Textual issue #2952: Capture prints](https://github.com/Textualize/textual/issues/2952) — print interception behavior (HIGH confidence — official repo)
- [Reactive mount timing issues #4691, #4570](https://github.com/Textualize/textual/issues/4691) — reactive before mount errors (HIGH confidence — official repo)
- [Claude Agent SDK overview](https://platform.claude.com/docs/en/agent-sdk/overview) — subprocess architecture, async generator interface (HIGH confidence — official Anthropic)
- Codebase analysis: `conductor/cli/chat.py`, `conductor/cli/delegation.py`, `conductor/dashboard/server.py`, `conductor/cli/input_loop.py` — HIGH confidence (direct code review)

---
*Pitfalls research for: Textual TUI integration — Conductor v2.0*
*Researched: 2026-03-11*
