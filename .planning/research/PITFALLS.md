# Pitfalls Research

**Domain:** Interactive chat TUI added to existing multi-agent orchestration CLI (Conductor v1.1)
**Researched:** 2026-03-11
**Confidence:** HIGH — pitfalls derived from existing codebase analysis, official Rich/prompt_toolkit docs, CPython issues, and Claude Agent SDK official docs. Pitfalls specific to integrating chat mode into this exact existing system.

> **Note:** This file covers v1.1-specific pitfalls (adding interactive chat TUI). For v1.0 multi-agent orchestration pitfalls (state corruption, agent proliferation, ACP deadlock, etc.), see the original PITFALLS.md content preserved in `PITFALLS-v1.0.md`. Both apply to v1.1 work.

---

## Critical Pitfalls

### Pitfall 1: Rich Live Display + Input Prompt = Terminal Corruption

**What goes wrong:**
The existing `conductor run` command mixes a `Rich.Live` status table (on stdout) with `input()` calls in `_input_loop` (via `asyncio.to_thread`). When the TUI adds streaming token output (chat response printed character-by-character), both the Live table refreshes and the streaming print compete to write to the same terminal. The result: partial ANSI escape sequences interleaved with output, garbled display, cursor jumping, and the input prompt appearing mid-token-stream. The user sees a corrupted screen that never recovers without clearing.

**Why it happens:**
Rich Live uses ANSI cursor manipulation to overwrite its area in-place. When another coroutine (streaming token display) calls `console.print()` or writes to stdout simultaneously, it writes at whatever cursor position the Live refresh left, not at the bottom. The existing codebase already separates `input_console = Console(stderr=True)` from `Live(console=Console(stderr=False))` to dodge this — but chat mode introduces a third stream (streaming LLM tokens) that must also be routed without colliding. Developers miss that Rich Live redirects stdout by default, so a naive `print()` call in a streaming handler goes through Live's redirect and hits the table area.

**How to avoid:**
- Do not use `Rich.Live` in interactive chat mode. In chat mode, the display is a scrolling conversation log, not a live-updating table. Drop the `_display_loop`/`Live` layer entirely when running chat mode.
- If the status table is still desired in chat mode (background agent status), use Rich's `Console(stderr=True)` or a `Rich.Panel` appended to output after each turn — never a concurrent `Live` while streaming to the same terminal.
- Route all LLM streaming tokens through a single `Console` instance that is not under a `Live` context manager.
- Use `prompt_toolkit`'s `patch_stdout()` context manager when mixing asynchronous prompt and print output — it serializes all output through prompt_toolkit's renderer.

**Warning signs:**
- Terminal shows garbled ANSI codes (`[?25l`, `[A`, etc.) interleaved with response text.
- Chat prompt appears mid-response line.
- Screen flickers or goes blank during streaming.
- `Rich.Live` raises `LiveError: Only one live display may be active at once` when chat mode is entered while batch mode status display is running.

**Phase to address:** TUI entry point and display architecture phase — establish the display model before implementing any streaming output.

---

### Pitfall 2: `asyncio.to_thread(input)` Cannot Be Cleanly Cancelled

**What goes wrong:**
The existing `_ainput()` uses `asyncio.to_thread(input, prompt)`. When the user presses Ctrl+C, the `asyncio.gather()` raises `KeyboardInterrupt` in the event loop, the orchestrator task is cancelled, and `_input_loop` receives `CancelledError` — but the blocking `input()` thread keeps running, holding the process open waiting for Enter. The run.py comment already documents this: "asyncio.to_thread(input) cannot be cancelled from Python — the thread blocks until Enter is pressed." For `conductor run`, this is acceptable because the process exits. For an interactive TUI with a persistent loop, this becomes a session lifecycle bug: the user cannot gracefully exit or restart a chat session without pressing Enter.

**Why it happens:**
Python threads are not cancelable from outside the thread. `asyncio.to_thread` submits the blocking call to the default `ThreadPoolExecutor`; cancelling the outer `asyncio.Task` prevents the future from being awaited, but the OS thread continues running `input()`. This is a CPython architectural limitation documented in issue #107505.

**How to avoid:**
- Replace `asyncio.to_thread(input)` with `prompt_toolkit`'s `PromptSession.prompt_async()`. prompt_toolkit uses its own event loop integration that responds to cancellation and restores terminal state properly.
- If prompt_toolkit is not adopted, use `sys.stdin` with `asyncio.get_event_loop().add_reader()` for non-blocking stdin — this is cancellable because it is I/O-based not thread-based.
- Never rely on `asyncio.to_thread(input)` as the input mechanism for a persistent interactive session. It is acceptable only for one-shot blocking prompts (like the existing escalation "Your answer:" prompt) where process exit is the intended outcome on cancellation.

**Warning signs:**
- After Ctrl+C to exit chat mode, the terminal hangs waiting for Enter.
- `ps aux` shows the conductor process still running after the user pressed Ctrl+C.
- Re-running `conductor` immediately after exit fails because the previous process is still holding the TTY.

**Phase to address:** Input handling foundation phase — choose the input mechanism before building any interaction logic.

---

### Pitfall 3: Chat History Grows Unbounded, Silently Exhausting Context

**What goes wrong:**
In chat mode, every user message and assistant response is appended to the conversation history passed to the Claude Agent SDK. After 20-30 turns of a complex coding session (especially with tool use results being large), the accumulated history can exceed Claude's context window. The SDK may silently apply auto-compaction, losing critical earlier context (e.g., "we decided NOT to use class-based approach" from turn 3). The orchestrator's delegation decisions in turn 25 then contradict the early architectural decisions the user established, producing wrong code or re-doing already-completed work.

**Why it happens:**
Developers building chat interfaces treat conversation history as an ever-growing list. The Claude Agent SDK does not surface a token count warning to the caller by default; auto-compaction happens server-side without a client event. There is no visible signal to the user that their earlier instructions have been lost from the model's effective context.

**How to avoid:**
- Track approximate token count client-side after each turn (user message + assistant response + tool outputs). Warn the user at 60% context utilization ("Context is 60% full — consider starting a new session for major new features").
- Implement a session summary mechanism: at 75% utilization, offer to summarize the session so far into a compact "session brief" that replaces the full history, preserving decisions and constraints but compressing rationale.
- Store full conversation history to `.conductor/chat_history.json` for the user's record (separate from the truncated context sent to the API).
- Design the orchestrator's "chat mode" system prompt to include a "decisions made" structured section that the model updates each turn — a durable summary that survives compaction better than raw conversation history.

**Warning signs:**
- After many turns, the model starts contradicting earlier decisions.
- The model "forgets" the codebase context established at session start.
- Response quality degrades noticeably after 30+ turns.
- Tool outputs (file reads, shell results) in history are very large and accumulate quickly.

**Phase to address:** Chat session lifecycle phase — context management design must precede any long-running chat capability.

---

### Pitfall 4: Smart Delegation Decision Is Non-Deterministic and Leaks Between Modes

**What goes wrong:**
The orchestrator must decide: handle this task directly (read/edit files inline) vs. spawn sub-agents. This decision is made by the LLM and is non-deterministic. The failure mode has two variants: (1) The orchestrator delegates a trivial one-liner change to a sub-agent, introducing seconds of latency and unnecessary cost. (2) The orchestrator handles a complex multi-file refactor directly (in-context), producing incomplete work because a single agent pass cannot atomically handle the full scope. Additionally, the delegation decision references the existing batch-mode `Orchestrator` class, which holds state (`_active_clients`, `_active_tasks`) from any concurrent `conductor run` session — sharing this instance between batch and chat modes corrupts both.

**Why it happens:**
LLMs make delegation decisions based on prompt framing and context. Without an explicit, rule-based pre-filter (e.g., "if task touches >2 files → delegate") the model makes inconsistent decisions across similar inputs. The state leakage happens because developers reuse the existing `Orchestrator` singleton across both modes rather than instantiating separate scoped instances.

**How to avoid:**
- Define a clear, rule-based delegation policy that the LLM applies before deciding: "If the task requires creating or modifying more than 1 file, spawns from a single conceptual change, or requires running tests — delegate. Otherwise, handle directly."
- Implement a lightweight heuristic pre-filter in Python (before LLM decision): count implied file modifications from the user's message. Use it to gate whether to even ask the LLM.
- Chat mode and batch mode must use separate `Orchestrator` instances with separate state. Never share an `Orchestrator` instance between `conductor` (chat) and `conductor run` (batch) invocations.
- In chat mode, sub-agent delegation is a discrete action with a visible status update ("Spawning 2 agents for this task...") — not a silent background decision.

**Warning signs:**
- Simple "rename this variable" requests spin up sub-agents.
- Complex multi-file refactors are handled in-context with incomplete results.
- After a `conductor run` session, starting `conductor` shows stale agent statuses from the batch run.
- `_active_clients` dict has entries from a previous session when a new chat session starts.

**Phase to address:** Delegation logic and orchestrator scoping phase.

---

### Pitfall 5: Terminal Raw Mode Left Dirty on Crash or Exception

**What goes wrong:**
Interactive TUI tools (prompt_toolkit, readline, or any library that enters raw/cbreak terminal mode for arrow key navigation and history) modify the terminal's tty settings. If the process crashes with an unhandled exception, a `KeyboardInterrupt` outside the input handler's cleanup path, or an `asyncio.CancelledError` propagated incorrectly, the terminal is left in raw mode. All subsequent shell input appears with no echo, no line buffering, and keyboard shortcuts behave strangely. The user must manually run `stty sane` or `reset` to recover. This is a highly visible, jarring failure mode.

**Why it happens:**
Raw mode is entered via a context manager (e.g., `with prompt_toolkit.input.create_input() as input:`) but exceptions that bypass the `__exit__` call leave the terminal modified. Additionally, `asyncio.CancelledError` is a `BaseException` subclass — standard `try/except Exception` blocks do not catch it, meaning cleanup code in `except Exception:` blocks is skipped. A known prompt_toolkit issue (#787) documents that `prompt_async()` does not clean up terminal state if cancelled, leaving echo off.

**How to avoid:**
- Wrap the entire chat session entry point in a `try/finally` block that explicitly calls `terminal.restore()` or equivalent in the `finally` clause — not just in `except`.
- Use `prompt_toolkit`'s `PromptSession` which has its own cleanup, but additionally catch `BaseException` (not just `Exception`) in the outermost chat loop to ensure cleanup runs on `CancelledError`, `SystemExit`, and `KeyboardInterrupt`.
- Test explicitly: force a crash (raise an unhandled exception) mid-prompt and verify `stty -a` shows normal terminal settings afterward.
- Register a `signal.signal(signal.SIGTERM, ...)` handler that triggers the same cleanup path as Ctrl+C.

**Warning signs:**
- After an unexpected exit from `conductor`, shell input is invisible (no echo).
- Backspace and arrow keys produce `^H`, `^[[A` visible characters instead of navigating.
- Users report needing to run `reset` after `conductor` crashes.

**Phase to address:** Input handling foundation phase — terminal cleanup must be a first-class concern, not an afterthought.

---

### Pitfall 6: Streaming Token Display Blocks the Event Loop

**What goes wrong:**
Streaming LLM response tokens arrives via `async for message in client.stream_response()`. Developers display each token with `console.print(token)` or `sys.stdout.write(token)` inside the `async for` loop. `Rich.Console.print()` acquires an internal thread lock and does terminal I/O — it is a blocking call. Under normal conditions this is fast enough to be invisible, but when the terminal is slow (SSH session, Windows Terminal with many columns, large response chunks), the lock acquisition and I/O block the event loop long enough to miss incoming ACP events from background agents. The existing background monitoring loop (`_display_loop`, agent question queue) can starve.

**Why it happens:**
Rich's `Console.print()` is not async-aware. Inside an `async for` loop, synchronous I/O that takes >1ms effectively blocks all other coroutines for that duration. With fast typing and large responses (code blocks), this adds up to hundreds of milliseconds of event loop blockage per turn.

**How to avoid:**
- Buffer streaming tokens and flush in batches using `asyncio.to_thread(console.print, buffered_text)` every N tokens or every M milliseconds.
- Alternatively, use `sys.stdout.write()` + `sys.stdout.flush()` directly for streaming token output (bypassing Rich's lock) and reserve `Console.print()` for formatted non-streaming output.
- Use `asyncio.sleep(0)` periodically inside the streaming loop to yield control to other coroutines between token batches.
- Benchmark: measure event loop latency (`asyncio.get_event_loop().call_later(0, ...)`) during active streaming to detect blockage.

**Warning signs:**
- Agent question prompts arrive with noticeable delay while a response is streaming.
- Background agent status updates are visibly delayed during chat responses.
- Event loop monitoring shows >50ms gaps during streaming.

**Phase to address:** Streaming output display phase.

---

### Pitfall 7: Typer `no_args_is_help=True` Conflicts with Chat Mode Entry

**What goes wrong:**
The existing CLI has `no_args_is_help=True` on the Typer app. Running `conductor` with no arguments currently shows the help text. V1.1 goal is for `conductor` with no arguments to enter interactive chat mode. These two behaviors are mutually exclusive — the Typer setting must be changed or overridden. If the developer forgets this, `conductor` still shows help text and the chat mode entry is unreachable via the primary invocation path. Additionally, changing `no_args_is_help` to False means that `conductor --help` must remain discoverable, or users lose the help entry point entirely.

**Why it happens:**
Typer's `no_args_is_help` is a Typer-level setting that intercepts the no-arguments case before any command dispatch. There is no hook to "check if args are empty and then do something custom" — the setting is binary. Developers testing the change in isolation do not notice because `conductor chat` (a subcommand) works, but `conductor` alone still shows help until the Typer app config is updated.

**How to avoid:**
- Change `no_args_is_help=False` on the Typer app when adding chat mode.
- Implement the default-to-chat behavior by overriding the Typer app's `result_callback` or by adding a default command that is invoked when no subcommand is given.
- The cleanest pattern: use Typer's `invoke_without_command=True` with a callback that checks `ctx.invoked_subcommand is None` and starts chat mode.
- Ensure `conductor --help` still works and prominently documents the no-args chat mode entry.

**Warning signs:**
- `conductor` with no args shows help text instead of starting chat mode.
- `conductor` with no args starts chat, but `conductor --help` no longer works.
- Subcommand `conductor run "..."` behavior changes unexpectedly after the Typer config update.

**Phase to address:** CLI entry point restructuring phase — must be addressed before any chat mode implementation is testable.

---

### Pitfall 8: Chat Mode Session State Is Not Isolated from Batch State File

**What goes wrong:**
Batch mode (`conductor run`) writes task and agent records to `.conductor/state.json`. If a user starts `conductor` (chat mode) while a batch session's state is in `.conductor/state.json` — or if chat mode writes its conversation metadata to the same file — the state file becomes ambiguous. The dashboard reads `state.json` and displays both chat-mode interactions and batch agent records in the same view, creating a confusing mixed display. Worse, if chat mode triggers sub-agent delegation (which writes to `state.json`), the batch-run's task records may be overwritten or merged incorrectly.

**Why it happens:**
The state file path `.conductor/state.json` is hardcoded as the single coordination file. Batch mode and chat mode both use `StateManager` pointing to the same path. Developers add chat-mode metadata to the same `ConductorState` model without considering that the dashboard was designed to display batch-mode records exclusively.

**How to avoid:**
- Use a separate state namespace for chat mode. Options: a separate file (`.conductor/chat_state.json`), a separate key in the state model (`chat_sessions` alongside `tasks` and `agents`), or a separate directory (`.conductor/sessions/[session-id]/`).
- Chat-triggered sub-agent delegation that writes task records should use a session-scoped prefix on task IDs to avoid collisions (`chat-[session-id]-task-001` vs. `batch-task-001`).
- The dashboard should explicitly handle the case of mixed batch + chat state and either filter to the active session or display them in separate panels.

**Warning signs:**
- Dashboard shows both chat conversation metadata and batch agent tasks in the same table.
- Task IDs from a previous batch run appear in chat-mode status displays.
- State file grows without bound across multiple chat sessions because old chat records are never cleaned up.

**Phase to address:** State model extension phase — before any chat-mode state is written.

---

### Pitfall 9: Tool Use in Chat Mode Breaks the Conversation Flow Display

**What goes wrong:**
When the orchestrator handles a task directly in chat mode (reading files, editing code, running shell commands), the ACP streaming response includes tool call events interspersed with text tokens. If the display layer naively streams everything, the user sees raw tool call JSON (`{"type": "tool_use", "name": "edit_file", "input": {...}}`) mixed into the conversation. Alternatively, if tool events are filtered entirely, the user has no visibility into what the agent is doing during a "thinking" period, which feels like a frozen UI. Neither extreme is good UX.

**Why it happens:**
The Claude Agent SDK's streaming output includes `TextChunk`, `ToolUseBlock`, `ToolResultBlock`, and `ResultMessage` events in the same stream. The existing `StreamMonitor` (in v1.0) processes these for batch mode but does not produce user-facing output — it accumulates result text for the reviewer. Chat mode needs a different rendering strategy: tool calls should be shown as progress indicators, not raw JSON, and text tokens should be streamed character by character.

**How to avoid:**
- Build a chat-mode stream renderer that handles each event type distinctly:
  - `TextChunk`: stream character by character to the conversation display.
  - `ToolUseBlock`: show a compact progress line ("Reading `src/auth.py`...") that updates in-place.
  - `ToolResultBlock`: show a collapsed summary ("Read 245 lines") with an expand option.
  - `ResultMessage`: mark the turn complete and update the conversation.
- Render tool activity in a separate display zone (e.g., a status line above the prompt) rather than inline in the conversation.
- Do not use the existing `StreamMonitor` for chat mode — it was designed for batch review, not interactive display.

**Warning signs:**
- Chat output contains raw JSON tool call payloads.
- Long pauses with no visual feedback while the agent reads files or runs commands.
- Users report the terminal "hanging" during tool execution even though the agent is actively working.

**Phase to address:** Streaming output display phase — concurrent with tool use implementation.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Reusing `asyncio.to_thread(input)` for chat input | No new dependencies | Thread cannot be cancelled; graceful exit broken; terminal corruption on crash | Never for persistent chat sessions — acceptable only for one-shot blocking prompts |
| Keeping `Rich.Live` table running during chat mode | Reuse existing display code | Terminal corruption when streaming text mixes with Live refresh | Never — drop Live in chat mode or display in separate panel |
| Single global `Orchestrator` instance for both modes | Simpler instantiation | State leakage between chat and batch sessions; `_active_clients` dict corruption | Never — always scope Orchestrator instances to session |
| Appending all tool output verbatim to conversation history | Complete audit trail in context | Context exhaustion within 10-15 turns if tool outputs are large (file reads, shell output) | Acceptable in early prototype only; must be replaced before any real usage |
| Storing chat history only in SDK session (no local persistence) | Simplest implementation | User loses entire conversation on process crash; no history browsing | Never — persist to `.conductor/chat_history.json` from day one |
| Using subprocess `input()` poll for Ctrl+C handling | No new async logic | Race condition between KeyboardInterrupt and CancelledError cleanup | Never — use signal handlers with explicit cleanup |

---

## Integration Gotchas

Common mistakes when connecting chat mode to the existing system.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Typer CLI entry | Setting `no_args_is_help=True` conflicts with no-args chat mode; changing it breaks help discoverability | Use `invoke_without_command=True` with callback checking `ctx.invoked_subcommand is None`; keep `--help` explicit |
| Claude Agent SDK in chat mode | Using `query()` one-shot function (as in spec review) for multi-turn chat | Use `ACPClient` with a persistent session and `send()`/`stream_response()` per turn — the same pattern used for sub-agents |
| `StateManager.mutate()` in chat mode | Calling `mutate()` from chat async code without `asyncio.to_thread()` wrapper | All `mutate()` calls require `asyncio.to_thread()` — it uses `filelock` which is blocking |
| Rich Live + streaming | Calling `console.print()` inside a `Rich.Live` context from a streaming handler | Never print to Live's console from outside the Live refresh callback; use a separate Console instance |
| `_input_loop` reuse for chat | Adapting the existing command-dispatch `_input_loop` for free-form chat | Chat input is free-form text, not command tokens; the existing dispatch table must not apply in chat mode |
| Dashboard in chat mode | Dashboard reads `state.json` and expects batch-mode schema | Either update dashboard to handle chat mode state or isolate chat state from dashboard's data path |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `console.print()` per token in streaming loop | Fine for slow LLM responses, lags with fast streaming | Buffer tokens, flush every 50ms or every newline | Immediately visible on fast network / small responses |
| Awaiting full response before displaying | Response appears all at once, feels slow | Stream token-by-token from SDK `include_partial_messages=True` | Any response >2 seconds |
| Loading full `.conductor/state.json` on every turn to check background agent status | Fast for small state, slow as state grows after many sessions | Cache last-known state; only reload on state file change event (watchfiles) | State file >50KB (~10 accumulated sessions) |
| Chat history as flat list with no summarization | Works for 5 turns, context exhaustion at 20-30 turns | Sliding window with summarization at 75% utilization | Turn 20-30 of any complex session |
| Spawning sub-agents for every delegation decision in chat mode | Fast when agents complete quickly, blocks chat responsiveness | Show agent status async; do not block chat loop waiting for agent completion | Agents taking >10 seconds per task |

---

## Security Mistakes

Domain-specific security issues in chat mode (beyond the v1.0 pitfalls).

| Mistake | Risk | Prevention |
|---------|------|------------|
| Trusting user's chat input as safe shell commands without review | Chat input could instruct the orchestrator to run `rm -rf` or exfiltrate files | In chat mode, shell commands are still subject to ACP permission flow — do not bypass `PermissionHandler` |
| Including full file contents verbatim in chat history sent to API | Large files in history waste tokens; sensitive credentials in read files get sent | Strip or truncate file contents in history; never persist raw API messages containing sensitive paths |
| Chat history stored in plaintext `.conductor/chat_history.json` | History may contain code, credentials, or architectural details | Document that `chat_history.json` should be in `.gitignore`; warn user on first run |
| Accepting user-specified `--repo` path in chat mode without canonicalization | Relative paths or symlinks could escape intended directory | Always `Path(repo).resolve()` before passing to agents (already done in batch mode — must be carried over) |

---

## UX Pitfalls

Common user experience mistakes specific to chat TUI mode.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No distinction between "orchestrator thinking" and "orchestrator delegating" | User cannot tell if a 10-second pause is inference or sub-agent spawning | Show explicit status: "Planning..." → "Delegating to 2 agents..." → "Waiting for agents..." → "Done" |
| Streaming tokens interrupted by agent question prompt | Mid-response, a sub-agent escalation appears, breaking the readable text | Queue escalation events; display them after the current response completes unless urgency requires interrupt |
| No turn separator in conversation display | After 10+ turns, conversation is a wall of text with no structure | Print `---` or a Rich Panel border between turns; include turn number and timestamp |
| `KeyboardInterrupt` mid-streaming aborts without cleanup message | User sees a traceback or silent hang | Catch `KeyboardInterrupt` in the streaming loop; print "Response interrupted." and restore prompt cleanly |
| Chat mode and `conductor run` look identical on startup | Users accidentally run the wrong mode | Chat mode should have a distinct greeting/banner; batch mode should state "Starting orchestration for: [task]..." |
| Long tool execution with spinner but no details | User cannot tell if agent is stuck or making progress | Show the specific tool being called: "Running: `pytest tests/`" not just "Working..." |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces specific to v1.1.

- [ ] **Chat entry point:** `conductor` with no args opens chat mode — verify `conductor --help` still works and documents the no-args behavior.
- [ ] **Terminal cleanup:** Force-crash the process mid-prompt — verify terminal echo and line mode are restored (`stty -a` shows `echo` and `icanon`).
- [ ] **Streaming display:** Stream a 2000-token response — verify no other coroutines (agent question queue, status updates) are starved during streaming.
- [ ] **Context management:** Run 30 turns in one session — verify the user receives a warning before context exhaustion, not a silent mid-session failure.
- [ ] **Delegation boundary:** Ask for a single-line fix — verify no sub-agents are spawned. Ask for a multi-file feature — verify sub-agents are spawned with visible status.
- [ ] **State isolation:** Run `conductor run "task"` and `conductor` (chat mode) in parallel — verify state files and agent records do not collide.
- [ ] **Tool output display:** Execute a chat turn that triggers file reads — verify the user sees human-readable progress, not raw JSON tool call payloads.
- [ ] **Session persistence:** Start a chat session, answer 5 turns, kill the process (`kill -9`), restart `conductor` — verify chat history is recoverable from `.conductor/chat_history.json`.
- [ ] **Ctrl+C behavior:** Press Ctrl+C once during active streaming — verify clean stop with no zombie threads and no terminal corruption.
- [ ] **Input mechanism:** Verify arrow key history navigation and Ctrl+R search work (requires prompt_toolkit or readline — not achievable with `asyncio.to_thread(input)`).

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Terminal corruption from Live + streaming conflict | LOW | User runs `reset` or `stty sane`; fix requires removing Live context from chat mode path |
| Thread leak from `asyncio.to_thread(input)` | LOW | Process will exit normally after user presses Enter; fix requires switching to prompt_toolkit |
| Context exhaustion (silent compaction) | MEDIUM | Load `.conductor/chat_history.json` to review full history; start new session with explicit "session brief" context |
| Delegation decision loops (trivial tasks spawning agents) | LOW | User can ask "do this yourself" to force direct handling; fix requires delegation policy rules |
| Chat + batch state collision | MEDIUM | Delete or rename `.conductor/state.json`; restart clean; fix requires session-scoped state namespacing |
| Terminal left in raw mode after crash | LOW | `stty sane` or `reset` restores terminal; fix requires `finally` block with explicit terminal restore |
| Tool call JSON appearing in chat display | LOW | No user recovery needed; cosmetic fix in stream renderer layer |

---

## Pitfall-to-Phase Mapping

How v1.1 roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Rich Live + input terminal corruption | CLI entry point restructuring (Phase 1) | Test: stream 500 tokens while Live display is active — screen must not corrupt |
| `asyncio.to_thread(input)` uncancellable | Input handling foundation (Phase 1) | Test: press Ctrl+C during active prompt — verify clean exit without requiring Enter key |
| Chat history context exhaustion | Chat session lifecycle (Phase 2) | Test: 30-turn session — verify warning fires before API returns context error |
| Smart delegation non-determinism | Delegation logic phase (Phase 3) | Test: 10 identical "rename this variable" requests — verify 0 sub-agents spawned each time |
| Terminal raw mode left dirty | Input handling foundation (Phase 1) | Test: `kill -9` the process mid-prompt — run `stty -a` — verify echo is on |
| Streaming blocks event loop | Streaming output display (Phase 2) | Test: measure event loop latency during 2000-token stream — verify <10ms gaps |
| Typer `no_args_is_help` conflict | CLI entry point restructuring (Phase 1) | Test: `conductor` with no args enters chat; `conductor --help` shows help; `conductor run "..."` still works |
| Chat/batch state isolation | State model extension (Phase 1) | Test: parallel `conductor run` + `conductor` session — verify state.json shows no cross-contamination |
| Tool use display in chat | Streaming output display (Phase 2) | Test: trigger file read in chat turn — verify human-readable status, no raw JSON |
| Session persistence on crash | Chat session lifecycle (Phase 2) | Test: kill -9 mid-turn — verify history recoverable from disk on next start |

---

## Sources

- [Rich Live Display documentation](https://rich.readthedocs.io/en/stable/live.html) — HIGH confidence (official)
- [Rich Live Display discussion: input during Live](https://github.com/Textualize/rich/discussions/1791) — HIGH confidence (official repo discussion, confirmed limitation)
- [Rich thread-safety issue #1530](https://github.com/willmcgugan/rich/issues/1530) — HIGH confidence (official repo bug report)
- [prompt_toolkit async_prompt cleanup issue #787](https://github.com/prompt-toolkit/python-prompt-toolkit/issues/787) — HIGH confidence (official repo, confirmed terminal state bug)
- [prompt_toolkit async docs](https://python-prompt-toolkit.readthedocs.io/en/master/pages/asking_for_input.html) — HIGH confidence (official)
- [CPython issue #107505: run_in_executor thread not stopped after task cancellation](https://github.com/python/cpython/issues/107505) — HIGH confidence (official CPython tracker)
- [asyncio development guide (blocking calls)](https://docs.python.org/3/library/asyncio-dev.html) — HIGH confidence (official Python docs)
- [Claude Agent SDK streaming docs](https://platform.claude.com/docs/en/agent-sdk/streaming-output) — HIGH confidence (official Anthropic)
- [Claude Agent SDK agent loop docs](https://platform.claude.com/docs/en/agent-sdk/agent-loop) — HIGH confidence (official Anthropic)
- [Claude Agent SDK tool use context costs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use) — HIGH confidence (official Anthropic)
- [Context window management strategies](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/) — MEDIUM confidence (practitioner article, aligns with Anthropic official guidance)
- Codebase analysis: `/packages/conductor-core/src/conductor/cli/input_loop.py`, `run.py`, `orchestrator.py`, `display.py` — HIGH confidence (direct code review, pitfalls derived from existing patterns)

---
*Pitfalls research for: interactive chat TUI added to Conductor multi-agent orchestration CLI (v1.1)*
*Researched: 2026-03-11*
