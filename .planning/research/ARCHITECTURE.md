# Architecture Research

**Domain:** Textual TUI integration into existing Python multi-agent orchestration framework (Conductor v2.0)
**Researched:** 2026-03-11
**Confidence:** HIGH

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Terminal (User Layer)                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                  ConductorApp (Textual App)                   │   │
│  │  ┌──────────────────────┐  ┌───────────────────────────────┐ │   │
│  │  │  TranscriptPane      │  │  AgentMonitorPane (right side) │ │   │
│  │  │  (ScrollView)        │  │  - AgentStatusRow per agent    │ │   │
│  │  │  - MessageCell/turn  │  │  - Reads state.json via worker │ │   │
│  │  │  - MarkdownStream    │  └───────────────────────────────┘ │   │
│  │  │    for live tokens   │                                     │   │
│  │  └──────────────────────┘                                     │   │
│  │  ┌──────────────────────────────────────────────────────────┐ │   │
│  │  │  CommandInput (Input + slash autocomplete popup)          │ │   │
│  │  └──────────────────────────────────────────────────────────┘ │   │
│  │  ┌──────────────────────────────────────────────────────────┐ │   │
│  │  │  StatusFooter (model, mode, tokens, rate limit)           │ │   │
│  │  └──────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                     Background Workers Layer                         │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ SDKStreamWorker │  │ StateWatchWorker  │  │ DashboardWorker  │   │
│  │ (@work coroutine│  │ (watchfiles +     │  │ (uvicorn server  │   │
│  │  on Textual     │  │  post_message to  │  │  asyncio.Task on │   │
│  │  event loop)    │  │  AgentMonitorPane)│  │  same loop)      │   │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                     Existing Preserved Layer                         │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ DelegationMgr   │  │  Orchestrator    │  │  StateManager    │   │
│  │ (kept intact,   │  │  (UI-agnostic,   │  │  + state.json    │   │
│  │  input_fn swap) │  │  kept intact)    │  │  (unchanged)     │   │
│  └─────────────────┘  └──────────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| `ConductorApp` | Textual App root — owns event loop, widget tree, screen stack | Replaces `ChatSession.run()`. Calls `asyncio.create_task()` in `on_mount()` for uvicorn; uses `run_worker()` for SDK and state watcher |
| `TranscriptPane` | Scrollable conversation history, one `MessageCell` per turn | `ScrollableContainer` holding `MessageCell` widgets; newest cell uses `MarkdownStream` while token stream is live |
| `MessageCell` | Single conversation turn (user or assistant). Immutable once stream ends | Custom widget wrapping `MarkdownStream` (assistant) or `Static` (user). Fixed after `StreamDone` message |
| `CommandInput` | Single-line input with slash autocomplete popup | `Input` widget with `Suggester` subclass. Popup via `textual-autocomplete` triggered on `/` |
| `AgentMonitorPane` | Right-side panel showing active agent status rows | `VerticalScroll` of `AgentStatusRow` widgets. Updated via `StateChanged` custom messages posted by `StateWatchWorker` |
| `AgentStatusRow` | One row per agent: ID, task title, status, elapsed time | Custom widget with `Reactive` attributes for status and elapsed. Auto-refreshes on reactive change |
| `StatusFooter` | Bottom bar: model name, mode (auto/interactive), token count, rate limit | `Horizontal` container with `Label` widgets; updated via `TokensUpdated` custom message from SDK stream worker |
| `ApprovalModal` | Modal overlay for agent file change or command approval | `ModalScreen[bool]` — pushed via `push_screen_wait()` from within a `@work` worker |
| `EscalationModal` | Modal overlay for sub-agent questions relayed to human | `ModalScreen[str]` — pushed via `push_screen_wait()` replacing `DelegationManager._input_fn` |
| `SDKStreamWorker` | Drives `ClaudeSDKClient` streaming — posts `TokenChunk` and `ToolActivity` messages to transcript | `@work` async coroutine on Textual's event loop; no separate thread needed |
| `StateWatchWorker` | Watches `state.json` via `watchfiles.awatch` — posts `StateChanged` to app | `@work` async coroutine. Replaces `DelegationManager._status_updater` polling |
| `DashboardWorker` | Runs uvicorn in background for web dashboard coexistence | `asyncio.create_task(server.serve())` in `on_mount()` — same event loop as Textual |
| `DelegationManager` | Spawns orchestrators, bridges escalation — kept intact | `input_fn` replaced: was `prompt_toolkit` prompt, becomes `push_screen_wait(EscalationModal(...))` |

---

## Recommended Project Structure

```
conductor/
├── cli/
│   ├── __init__.py            # MODIFIED: ConductorApp(...).run() replaces ChatSession
│   ├── chat.py                # KEPT as --legacy fallback or deleted after migration
│   ├── chat_persistence.py    # KEPT unchanged (session JSON store)
│   ├── delegation.py          # MODIFIED: input_fn swap + remove _status_updater/_clear_status_lines
│   ├── stream_display.py      # KEPT: format_tool_activity(), ContextTracker() reused
│   ├── input_loop.py          # KEPT: batch-mode input loop (conductor run) unchanged
│   └── display.py             # KEPT unchanged
│
└── tui/                       # NEW module
    ├── __init__.py
    ├── app.py                 # ConductorApp — Textual App root, lifecycle, worker launch
    ├── screens/
    │   ├── __init__.py
    │   ├── main.py            # MainScreen — default layout
    │   ├── approval.py        # ApprovalModal — ModalScreen[bool] for agent action approval
    │   └── escalation.py      # EscalationModal — ModalScreen[str] for agent question relay
    ├── widgets/
    │   ├── __init__.py
    │   ├── transcript.py      # TranscriptPane + MessageCell
    │   ├── command_input.py   # CommandInput (Input + slash autocomplete)
    │   ├── agent_monitor.py   # AgentMonitorPane + AgentStatusRow
    │   └── status_footer.py   # StatusFooter
    ├── workers/
    │   ├── __init__.py
    │   ├── sdk_stream.py      # SDKStreamWorker — drives ClaudeSDKClient streaming
    │   ├── state_watcher.py   # StateWatchWorker — watchfiles bridge to TUI messages
    │   └── dashboard.py       # DashboardWorker — uvicorn asyncio.create_task launcher
    ├── messages.py            # Custom Textual message types (TokenChunk, ToolActivity,
    │                          #   StateChanged, TokensUpdated, StreamDone, etc.)
    └── conductor.tcss         # Textual CSS for layout and styling
```

### Structure Rationale

- **`tui/`** is isolated from `cli/` so the old `ChatSession` remains for tests and fallback — no forced big-bang migration.
- **`tui/screens/`** holds screens separately from widgets — Textual treats screens as first-class routing units.
- **`tui/workers/`** groups all long-running async tasks to make event loop ownership explicit and auditable.
- **`tui/messages.py`** centralizes custom message types to prevent circular imports; makes the internal event bus explicit.
- **`tui/conductor.tcss`** separates visual styling from widget logic, allowing layout tuning without Python changes.

---

## Architectural Patterns

### Pattern 1: Textual App as the Single Asyncio Event Loop Owner

**What:** `ConductorApp.run()` becomes the asyncio entry point for the entire process. All previously concurrent tasks — SDK streaming, uvicorn, watchfiles — are launched as tasks *inside* Textual's event loop, not alongside it.

**When to use:** This is the root pattern for the entire migration. Everything else flows from it.

**Trade-offs:** Textual's `app.run()` creates and owns the asyncio event loop. Code that previously used `asyncio.run(...)` must move inside `on_mount()` or become `@work` workers.

**Example:**
```python
# conductor/tui/app.py
class ConductorApp(App):
    async def on_mount(self) -> None:
        # SDK streaming: @work coroutine on Textual's event loop
        self.run_worker(self._sdk_stream_loop(), exclusive=True)

        # State watcher: asyncio.create_task runs on same event loop
        self._state_watch_task = asyncio.create_task(self._watch_state())

        # Dashboard server: same event loop, no new thread
        if self._dashboard_port:
            server = self._create_uvicorn_server(self._dashboard_port)
            self._server_task = asyncio.create_task(server.serve())

    async def on_unmount(self) -> None:
        if hasattr(self, "_server_task"):
            self._uvicorn_server.should_exit = True
            await self._server_task

# conductor/cli/__init__.py (modified)
asyncio.run(...)  # REMOVED
ConductorApp(resume_session_id=..., dashboard_port=...).run()  # REPLACES
```

### Pattern 2: Custom Textual Messages as the Internal Event Bus

**What:** Background workers never call widget methods directly. They post custom `Message` subclasses (defined in `tui/messages.py`) to the app, and widgets handle them via `on_<MessageType>` handlers.

**When to use:** All cross-worker-to-widget communication. This is the canonical Textual pattern for thread-safe UI updates.

**Trade-offs:** Adds a layer of message types but prevents tight coupling. Moving or renaming a widget does not break the worker that feeds it.

**Example:**
```python
# conductor/tui/messages.py
from textual.message import Message

class TokenChunk(Message):
    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__()

class ToolActivity(Message):
    def __init__(self, activity_line: str) -> None:
        self.activity_line = activity_line
        super().__init__()

class StateChanged(Message):
    def __init__(self, state: ConductorState) -> None:
        self.state = state
        super().__init__()

class StreamDone(Message):
    pass

# conductor/tui/workers/sdk_stream.py
@work
async def _sdk_stream_loop(self) -> None:
    async for message in self._sdk_client.receive_response():
        if isinstance(message, StreamEvent):
            chunk = extract_text_delta(message)
            if chunk:
                self.post_message(TokenChunk(chunk))
        elif isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    activity = format_tool_activity(block.name, block.input)
                    if activity:
                        self.post_message(ToolActivity(activity))
        elif isinstance(message, ResultMessage):
            self.post_message(TokensUpdated(message.usage))
    self.post_message(StreamDone())

# conductor/tui/widgets/transcript.py
class TranscriptPane(ScrollableContainer):
    def on_token_chunk(self, event: TokenChunk) -> None:
        self._active_cell.append_token(event.text)

    def on_stream_done(self, event: StreamDone) -> None:
        self._active_cell.finalize()
        self._active_cell = None
```

### Pattern 3: MarkdownStream for Streaming LLM Responses

**What:** Each assistant `MessageCell` holds a `MarkdownStream` instance (available in Textual v4+). Incoming `TokenChunk` messages call `await stream.append(chunk)`. On `StreamDone`, the cell is finalized and made immutable. `MarkdownStream` batches rapid updates internally, preventing the 20 appends/second rendering bottleneck of the base `Markdown` widget.

**When to use:** For all streaming assistant responses. Do not use `Static` with manual string concatenation — it neither streams live nor renders markdown.

**Trade-offs:** Requires Textual v4+. `MarkdownStream` is specifically designed for LLM streaming patterns — this is the primary new feature of Textual v4.

**Example:**
```python
# conductor/tui/widgets/transcript.py
from textual.widgets import Markdown

class MessageCell(Widget):
    def __init__(self, role: str) -> None:
        super().__init__()
        self._role = role
        self._stream: Markdown.MarkdownStream | None = None

    async def start_stream(self) -> None:
        md = Markdown("")
        await self.mount(md)
        self._stream = await Markdown.get_stream(md)

    async def append_token(self, text: str) -> None:
        if self._stream:
            await self._stream.append(text)

    def finalize(self) -> None:
        self._stream = None  # cell is immutable after stream ends
```

### Pattern 4: ModalScreen for Approval and Escalation Overlays

**What:** Agent action approvals (file write, command execution) and sub-agent escalation questions use `ModalScreen[T]` pushed via `push_screen_wait()` from within a `@work` coroutine. The screen calls `self.dismiss(result)` and the worker receives the typed result and continues. The rest of the TUI remains interactive while the modal is displayed.

**When to use:** Any time the TUI must block a background operation waiting for human input, without freezing the main UI.

**Trade-offs:** `push_screen_wait()` must be called from a `@work` worker — not from an event handler. Calling it from an event handler deadlocks.

**Example:**
```python
# conductor/tui/screens/escalation.py
class EscalationModal(ModalScreen[str]):
    def __init__(self, question: str) -> None:
        self._question = question
        super().__init__()

    def compose(self) -> ComposeResult:
        yield Label(self._question)
        yield Input(placeholder="Your answer...", id="answer")
        yield Button("Send", id="send", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        answer = self.query_one("#answer", Input).value
        self.dismiss(answer or "proceed")

# conductor/tui/app.py — wire into DelegationManager
async def _make_escalation_input_fn(self):
    """Returns a callable that opens EscalationModal and returns user's answer."""
    @work
    async def _ask(question: str) -> str:
        return await self.push_screen_wait(EscalationModal(question))
    return _ask
```

### Pattern 5: StateWatchWorker Replaces _status_updater Polling

**What:** `DelegationManager._status_updater()` currently polls `StateManager.read_state()` every 2 seconds and uses ANSI escape codes (`\033[A\033[2K`) to overwrite terminal lines. Replace this with a `@work` coroutine using `watchfiles.awatch()` — the same mechanism as `conductor.dashboard.watcher` — that posts `StateChanged` messages to `AgentMonitorPane`.

**When to use:** Always in the TUI. File event-driven updates are more responsive than polling and ANSI cursor manipulation is illegal inside a Textual app (Textual owns cursor positioning).

**Trade-offs:** `watchfiles.awatch` must watch the *parent directory* (not `state.json` directly) because `StateManager` uses `os.replace()` which swaps the inode. This is the same documented gotcha already solved in `conductor/dashboard/watcher.py`.

**Example:**
```python
# conductor/tui/workers/state_watcher.py
from watchfiles import awatch
from conductor.state.manager import StateManager

@work
async def watch_state(self, state_path: Path) -> None:
    stop = asyncio.Event()
    async for changes in awatch(str(state_path.parent), stop_event=stop):
        changed_names = {Path(p).name for _, p in changes}
        if state_path.name not in changed_names:
            continue
        try:
            new_state = await asyncio.to_thread(
                StateManager(state_path).read_state
            )
        except Exception:
            continue  # mid-write atomic swap; skip this cycle
        self.post_message(StateChanged(new_state))

# conductor/tui/widgets/agent_monitor.py
class AgentMonitorPane(VerticalScroll):
    def on_state_changed(self, event: StateChanged) -> None:
        state = event.state
        # diff agents, add/remove/update AgentStatusRow widgets
        active_ids = {a.id for a in state.agents if a.status in ("working", "waiting")}
        self._sync_rows(state.agents, active_ids)
```

---

## Data Flow

### User Message → Streaming Response

```
CommandInput (Input.Submitted event)
    ↓
ConductorApp.on_input_submitted()
    ↓ creates MessageCell("user") in TranscriptPane with user text
    ↓ creates MessageCell("assistant") with MarkdownStream
    ↓ launches SDKStreamWorker via run_worker()
    ↓
SDKStreamWorker (@work coroutine)
    ↓ sdk_client.query(text)
    ↓ async for message in sdk_client.receive_response()
    │
    ├─ StreamEvent(text_delta)
    │     → post_message(TokenChunk(chunk))
    │           → TranscriptPane.on_token_chunk()
    │                 → active_cell.append_token(chunk)
    │                       → MarkdownStream.append(chunk)   [batched, non-blocking]
    │
    ├─ AssistantMessage(ToolUseBlock)
    │     → post_message(ToolActivity(format_tool_activity(name, input)))
    │           → TranscriptPane.on_tool_activity()
    │                 → writes dim activity line below streaming cell
    │
    ├─ ResultMessage(usage)
    │     → post_message(TokensUpdated(usage))
    │           → StatusFooter.on_tokens_updated()
    │                 → update token label + context warning if >75%
    │
    └─ (stream ends)
          → post_message(StreamDone())
                → TranscriptPane.on_stream_done()
                      → active_cell.finalize()        [cell now immutable]
                      → ChatHistoryStore.save_turn()  [persistence unchanged]
```

### State File Change → Agent Monitor Panel Update

```
Orchestrator/StateManager writes state.json (os.replace atomic swap)
    ↓
StateWatchWorker (watchfiles.awatch on parent directory)
    ↓ detects state.json in changed file set
    ↓ asyncio.to_thread(StateManager.read_state)
    ↓ post_message(StateChanged(new_state))
    ↓
AgentMonitorPane.on_state_changed(event)
    ↓ diff agents: add new AgentStatusRow, remove completed rows
    ↓ each AgentStatusRow.status = new_status   [Reactive → auto re-render]
    ↓ each AgentStatusRow.elapsed = elapsed_secs
```

### Sub-Agent Escalation → Human → Answer

```
Orchestrator._human_out.put(HumanQuery(question))
    ↓
DelegationManager._escalation_listener() detects queue item
    ↓ calls self._input_fn(question)
    ↓ [input_fn is now: await self.app.push_screen_wait(EscalationModal(question))]
    ↓
EscalationModal displayed over main screen
    ↓ rest of TUI (transcript, agent monitor) remains live
    ↓ user types answer + presses Send → modal.dismiss(answer)
    ↓
input_fn returns answer string to _escalation_listener
    ↓
DelegationManager puts answer in _human_in queue
    ↓
Orchestrator resumes sub-agent with human answer
```

### Dashboard Server Coexistence

```
ConductorApp.on_mount() — if --dashboard-port provided:
    ↓ create_app(state_path) → FastAPI app     [unchanged from v1.x]
    ↓ uvicorn.Server(Config(...))
    ↓ asyncio.create_task(server.serve())      [same event loop as Textual]
    ↓
Both Textual and uvicorn run as asyncio tasks on one loop.
Web dashboard connects via WebSocket — state_watcher inside dashboard
server is separate from StateWatchWorker (each has its own awatch).

ConductorApp.on_unmount():
    ↓ server.should_exit = True
    ↓ await server_task  [uvicorn drains gracefully]
```

---

## Integration Points: New vs Existing

### Components Kept Intact (Zero Changes)

| Module | Why Kept |
|--------|----------|
| `conductor/orchestrator/` (all files) | UI-agnostic; no changes needed |
| `conductor/state/models.py`, `state/manager.py` | Pure data; `ConductorState` and `StateManager` unchanged |
| `conductor/dashboard/server.py` | FastAPI app unchanged — still `create_app(state_path)` |
| `conductor/dashboard/watcher.py` | `state_watcher()` coroutine reused inside `DashboardWorker` |
| `conductor/dashboard/events.py` | `DeltaEvent`, `classify_delta()` unchanged |
| `conductor/cli/chat_persistence.py` | `ChatHistoryStore` is pure file I/O — reused in `on_stream_done` |
| `conductor/cli/stream_display.py` | `format_tool_activity()`, `ContextTracker` reused in `SDKStreamWorker` |
| `conductor/cli/input_loop.py` | Batch-mode `conductor run` unchanged |
| `conductor/cli/commands/run.py` | Unchanged |
| `conductor/cli/commands/status.py` | Unchanged |

### Components Modified

| Module | Change |
|--------|--------|
| `conductor/cli/__init__.py` | Replace `asyncio.run(_run_chat_with_dashboard(...))` with `ConductorApp(...).run()`. Keep `--dashboard-port`, `--resume`, `--resume-id` flags — pass as constructor args to `ConductorApp`. |
| `conductor/cli/delegation.py` | Three changes: (1) `input_fn` type stays the same (`Callable[[str], Awaitable[str]]`) but the injected value changes from a `prompt_toolkit` coroutine to `push_screen_wait(EscalationModal(q))`; (2) remove `_status_updater` method entirely — replaced by `StateWatchWorker`; (3) remove `_clear_status_lines()` — ANSI cursor manipulation conflicts with Textual rendering. |

### Components Added (New)

| Module | Purpose |
|--------|---------|
| `conductor/tui/app.py` | `ConductorApp` — Textual App root, `on_mount` lifecycle, worker launch |
| `conductor/tui/screens/main.py` | `MainScreen` — two-column layout (TranscriptPane + AgentMonitorPane + CommandInput + StatusFooter) |
| `conductor/tui/screens/approval.py` | `ApprovalModal` — file/command approval overlay |
| `conductor/tui/screens/escalation.py` | `EscalationModal` — agent question relay overlay |
| `conductor/tui/widgets/transcript.py` | `TranscriptPane` scroll container + `MessageCell` per turn |
| `conductor/tui/widgets/command_input.py` | `CommandInput` with slash autocomplete |
| `conductor/tui/widgets/agent_monitor.py` | `AgentMonitorPane` + `AgentStatusRow` |
| `conductor/tui/widgets/status_footer.py` | `StatusFooter` |
| `conductor/tui/workers/sdk_stream.py` | `SDKStreamWorker` — drives SDK streaming |
| `conductor/tui/workers/state_watcher.py` | `StateWatchWorker` — watchfiles bridge |
| `conductor/tui/workers/dashboard.py` | `DashboardWorker` — uvicorn `asyncio.create_task` launcher |
| `conductor/tui/messages.py` | All custom Textual message types |
| `conductor/tui/conductor.tcss` | Textual CSS for layout and visual styling |

---

## Build Order (Incremental Migration)

Build from the inside out — static shell first, then live data, then modals. Each phase is independently testable.

### Phase A: Static Shell (no live data)

Build `ConductorApp`, `MainScreen`, `TranscriptPane`, `CommandInput`, `StatusFooter`. Hard-code a few `MessageCell` widgets to verify layout. Wire `CommandInput.Submitted` to create a user `MessageCell` with the typed text. No SDK, no workers, no delegation.

**Deliverable:** `conductor` opens a Textual TUI with two-column layout. Input creates cells. App exits cleanly on `/exit` or Ctrl+C. Confirms Textual is wired into CLI entry point correctly.

### Phase B: SDK Streaming

Add `SDKStreamWorker`, `MarkdownStream`-backed assistant `MessageCell`, `TokenChunk`/`ToolActivity`/`StreamDone`/`TokensUpdated` messages. Wire `CommandInput.Submitted` to create a live streaming cell and launch the worker. Wire `StatusFooter` token counter.

**Deliverable:** Real Claude responses stream token by token into the transcript. Tool activity lines appear inline. Context tracker threshold warning works.

### Phase C: Agent Monitor Panel

Add `AgentMonitorPane`, `AgentStatusRow`, `StateWatchWorker`, `StateChanged` message. Confirm `watchfiles.awatch` on parent directory picks up `os.replace` writes from `StateManager`.

**Deliverable:** Right panel shows live agent status when a delegation is active. Panel shows nothing when no delegation is running.

### Phase D: Escalation Modal

Add `EscalationModal` and wire it as the new `input_fn` for `DelegationManager`. Remove `_status_updater` from `DelegationManager` (now replaced by `StateWatchWorker`). Remove `_clear_status_lines()`.

**Deliverable:** Sub-agent escalation questions appear as modal overlays over the live TUI. Background transcript and agent monitor remain live. User answer is routed back to the orchestrator correctly.

### Phase E: Approval Modal

Add `ApprovalModal` for file write and command execution approval. Wire from `DelegationManager` or wherever approval was handled in `chat.py`. Test with a mock delegation that triggers an approval request.

**Deliverable:** Approve/deny overlays work. Background TUI stays live during approval.

### Phase F: Slash Commands and Autocomplete

Add slash command dispatch to `CommandInput`. Implement `Suggester` subclass for `/` prefix. Wire `/help`, `/exit`, `/status`, `/summarize`, `/resume`. Add `textual-autocomplete` dropdown for popup display.

**Deliverable:** All existing slash commands work. Autocomplete popup shows candidates when user types `/`.

### Phase G: Dashboard Coexistence and CLI Wiring

Add `DashboardWorker` (uvicorn as `asyncio.create_task` inside `on_mount`). Finalize `conductor/cli/__init__.py` replacement — `ConductorApp(...).run()` replaces `asyncio.run(_run_chat_with_dashboard(...))`. Confirm `--dashboard-port` flag. Confirm `conductor run "..."` batch mode is unaffected.

**Deliverable:** `conductor --dashboard-port 8000` starts both TUI and WebSocket server concurrently in one process. Web dashboard connects and shows live state alongside the terminal.

### Phase H: Session Persistence

Wire `ChatHistoryStore` save into `on_stream_done`. Add session picker startup modal (replaces the `pick_session()` terminal prompt). Wire `--resume`/`--resume-id` flags to `ConductorApp` constructor.

**Deliverable:** Sessions persist across restarts. `--resume` shows a Textual session picker modal.

---

## Anti-Patterns

### Anti-Pattern 1: Calling Widget Methods Directly From Workers

**What people do:** Inside a `@work` coroutine or `asyncio.create_task`, call `self.transcript_pane.append_cell(...)` directly.

**Why it's wrong:** Textual's widget methods are not thread-safe from outside the message dispatch loop. Even async workers can cause rendering race conditions without going through the message bus.

**Do this instead:** Post a custom `Message` subclass via `self.post_message(TokenChunk(text))`. Textual routes it safely to the `on_token_chunk` handler.

### Anti-Pattern 2: Running Uvicorn With asyncio.run() Alongside Textual

**What people do:** Start uvicorn with `asyncio.run(server.serve())` in a separate thread or process, then call `ConductorApp().run()` which creates its own asyncio event loop.

**Why it's wrong:** Two separate event loops cannot share `asyncio.Queue` objects. `DelegationManager`'s escalation queues (`human_in`, `human_out`) would silently break — puts and gets would never meet.

**Do this instead:** Launch `asyncio.create_task(server.serve())` inside `ConductorApp.on_mount()`. One event loop owns everything.

### Anti-Pattern 3: Keeping prompt_toolkit Inside Textual

**What people do:** Keep `PromptSession.prompt_async()` or `patch_stdout()` active inside the Textual app for the `_escalation_input` function.

**Why it's wrong:** `prompt_toolkit` takes over stdin/stdout/terminal state in a way that conflicts with Textual's terminal control. Both cannot own the terminal simultaneously.

**Do this instead:** Use `ModalScreen` with a Textual `Input` widget for all human input inside the TUI. Remove `prompt_toolkit` dependency entirely in v2.0.

### Anti-Pattern 4: ANSI Escape Codes Inside Textual

**What people do:** Port `_clear_status_lines()` from `DelegationManager` into a Textual widget, emitting `\033[A\033[2K` to overwrite lines.

**Why it's wrong:** Textual owns terminal cursor positioning. Manual ANSI escape codes conflict with Textual's rendering loop and produce garbled output.

**Do this instead:** Use `Reactive` attributes on `AgentStatusRow`. When `status` or `elapsed` changes, Textual's reactive system handles re-rendering cleanly. Remove `_clear_status_lines()` and `_print_live_status()` entirely.

### Anti-Pattern 5: Awaiting push_screen_wait() From an Event Handler

**What people do:** Call `await self.app.push_screen_wait(EscalationModal(...))` directly inside an `on_<event>` handler.

**Why it's wrong:** `push_screen_wait()` must run inside a Textual `@work` worker. Awaiting it from a regular message handler will deadlock because handlers run on the message processing queue, which cannot process the modal's dismiss event while blocked.

**Do this instead:** Event handlers call `self.run_worker(self._handle_escalation(question))` and the `@work` coroutine calls `push_screen_wait()`.

### Anti-Pattern 6: Watching state.json Directly With watchfiles

**What people do:** Call `watchfiles.awatch(str(state_path))` to watch the state file itself.

**Why it's wrong:** `StateManager` uses `os.replace()` which is an atomic inode swap — the original file descriptor disappears. `watchfiles` watching the file directly misses these events. This is an existing known bug documented in `PROJECT.md` under Key Decisions.

**Do this instead:** Watch the parent directory: `watchfiles.awatch(str(state_path.parent))`, then filter: `if state_path.name in changed_names`. This is the same pattern used in `conductor/dashboard/watcher.py`.

---

## Scaling Considerations

This is a single-user local TUI — scaling means responsiveness under load, not distributed scale.

| Concern | Approach |
|---------|----------|
| Rapid token chunks from fast LLM response | `MarkdownStream` batches updates internally — handles bursts above 20 chunks/second without UI lag |
| Many concurrent agents (10+) | `AgentMonitorPane` is a `VerticalScroll` — Textual only re-renders dirty regions. Works without special handling up to dozens of agents. |
| Large session transcript (100+ turns) | All `MessageCell` widgets remain mounted. If performance degrades, add a `max_cells` setting: unmount oldest cells while keeping their content in `ChatHistoryStore` for persistence. |
| Uvicorn startup during TUI init | `asyncio.create_task(server.serve())` starts immediately in `on_mount()`. TUI is interactive before server is fully ready — no blocking. |
| Textual v4 requirement | `MarkdownStream` requires Textual v4+. The existing dependency is `rich` (not `textual`). Adding `textual>=4.0` adds a new dependency. Confirm no version conflicts with `rich>=13`. |

---

## Sources

- [Textual Workers Guide](https://textual.textualize.io/guide/workers/) — `@work`, `run_worker`, `post_message` thread safety — HIGH confidence (official docs)
- [Textual Screens Guide](https://textual.textualize.io/guide/screens/) — `ModalScreen[T]`, `push_screen_wait()`, `dismiss()` pattern — HIGH confidence (official docs)
- [Textual Markdown Widget](https://textual.textualize.io/widgets/markdown/) — `MarkdownStream`, `Markdown.get_stream()`, `append()` — HIGH confidence (official docs)
- [Textual RichLog Widget](https://textual.textualize.io/widgets/rich_log/) — `write()` API, `markup`, `auto_scroll` — HIGH confidence (official docs)
- [Textual v4.0.0 — MarkdownStream release](https://simonwillison.net/2025/Jul/22/textual-v4/) — streaming Markdown as first-class v4 feature — HIGH confidence (official release coverage)
- [Textual Discussion #339 — Long-running async tasks](https://github.com/Textualize/textual/discussions/339) — `asyncio.create_task()` vs `await` inside `on_mount()` — MEDIUM confidence (official maintainer response)
- [darrenburns/textual-autocomplete](https://github.com/darrenburns/textual-autocomplete) — slash command autocomplete dropdown — MEDIUM confidence (third-party, authored by Textual team member, Textual 2.0+ compatible)
- Existing codebase: `conductor/cli/chat.py`, `conductor/cli/delegation.py`, `conductor/cli/__init__.py`, `conductor/dashboard/server.py`, `conductor/dashboard/watcher.py` — HIGH confidence (primary source for integration points)

---

*Architecture research for: Conductor v2.0 — Textual TUI integration*
*Researched: 2026-03-11*
