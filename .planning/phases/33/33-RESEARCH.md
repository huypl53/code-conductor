# Phase 33: SDK Streaming - Research

**Researched:** 2026-03-11
**Domain:** Claude Agent SDK streaming + Textual worker pattern + reactive UI
**Confidence:** HIGH

## Summary

Phase 33 wires the Claude Agent SDK's streaming message protocol into the Textual TUI built in Phase 32. The SDK already supports token-by-token streaming via `StreamEvent` messages when `include_partial_messages=True` is set on `ClaudeAgentOptions`. The existing `chat.py` `ChatSession._process_message()` is a working reference implementation — it receives `StreamEvent` objects with `event.get("type") == "content_block_delta"` payloads containing text chunks.

Textual's `@work` decorator (from `textual._work_decorator`) creates a managed async worker from any async method on a `DOMNode`. The SDK streaming loop runs as a `@work` coroutine in `ConductorApp` or `TranscriptPane`, iterates `async for message in sdk_client.receive_response()`, and routes token chunks to the active `AssistantCell` by posting `TokenChunk` messages to the app bus. A 20fps refresh timer on `AssistantCell` flushes the buffered token string into the cell's `Markdown` widget. The status footer subscribes to `TokensUpdated` messages from `ResultMessage` delivery and uses Textual `reactive` attributes to update without polling.

The STATE.md concern about `MarkdownStream` API accuracy is **resolved**: `MarkdownStream` DOES exist in Textual 8.1.1 (installed version). The correct API is `stream = Markdown.get_stream(markdown_widget)` then `await stream.write(chunk)` then `await stream.stop()`. This is different from the guessed `stream.append(chunk)` variant — the correct method is `write()`, not `append()`.

**Primary recommendation:** Use `@work(exclusive=True)` on the SDK streaming coroutine; let `Markdown.get_stream()` handle render batching (no separate 20fps timer needed for the cell content); use `reactive` string attributes on `StatusFooter` for model/token display; disable `CommandInput` by setting `input_widget.disabled = True` during streaming and `False` on `StreamDone`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRNS-02 | Assistant responses stream token-by-token into the active cell with a working/thinking indicator before first token | SDK `StreamEvent` + `include_partial_messages=True` + `MarkdownStream.write()` + `LoadingIndicator` widget in AssistantCell |
| STAT-01 | Status footer displays current model, mode, token usage, and session info | `ResultMessage.usage` dict → `TokensUpdated` message → `reactive` attributes on `StatusFooter` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude_agent_sdk` | `>=0.1.48` | SDK streaming source | Already wired in project; `ClaudeSDKClient` + `receive_response()` is the established pattern |
| `textual` | `>=4.0` (8.1.1 installed) | TUI framework and worker host | Owns the event loop; `@work` decorator manages async tasks safely |
| `textual.widgets.Markdown` | same | Renders markdown content incrementally | Built-in; `append()` + `MarkdownStream` handle batching |
| `textual.widgets.LoadingIndicator` | same | Animated thinking spinner | Built-in; 16fps self-refresh; just mount it in AssistantCell before first token |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `textual.reactive` | same | Reactive state for StatusFooter | Model name, token count, mode — auto-repaint on change |
| `textual._work_decorator.work` | same | Decorator to create managed workers | Wrap the SDK stream loop; `exclusive=True` prevents double-submission |
| `asyncio.Queue` | stdlib | Token buffer between worker and UI timer | Only if 20fps timer is used instead of `MarkdownStream` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Markdown.get_stream()` | `asyncio.Queue` + `set_interval` | `get_stream()` is purpose-built for streaming; avoids hand-rolling the accumulation loop. Queue+timer adds complexity with no benefit for this use case. |
| `LoadingIndicator` widget | Custom spinner `Static` with `set_interval` | `LoadingIndicator` is self-refreshing and theme-aware. Custom spinner adds code with no benefit. |
| `reactive` on `StatusFooter` | `post_message(TokensUpdated)` + manual `update()` | Both work. `reactive` is cleaner because no handler boilerplate needed; just assign and Textual repaints. However, `TokensUpdated` message is already defined in `messages.py` — a handler pattern fits the existing bus design better. Recommendation: use `TokensUpdated` message (consistent with existing bus) + `reactive` attributes on `StatusFooter` that get set from the message handler. |

**Installation:**
Already installed. No new packages needed.

## Architecture Patterns

### Recommended Project Structure

```
tui/
├── app.py                        # ConductorApp — starts SDK worker in on_mount
├── messages.py                   # TokenChunk, StreamDone, TokensUpdated (already defined)
├── widgets/
│   ├── transcript.py             # TranscriptPane, UserCell, AssistantCell — AssistantCell gains streaming state
│   ├── command_input.py          # Disable/enable via .disabled flag during streaming
│   └── status_footer.py         # StatusFooter — reactive model/tokens/session display
```

### Pattern 1: SDK Streaming as Textual Worker

**What:** An `async def` method decorated with `@work(exclusive=True)` that owns the SDK connection lifecycle and routes events to the app message bus.

**When to use:** Any long-running async I/O task that must post messages to the Textual UI. `exclusive=True` cancels any prior worker in the same group — prevents double-submission if user somehow triggers twice.

**Example:**
```python
# Source: textual._work_decorator (verified in .venv)
from textual import work
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, ResultMessage
from claude_agent_sdk.types import StreamEvent

class ConductorApp(App):
    @work(exclusive=True, exit_on_error=False)
    async def _stream_response(self, text: str) -> None:
        """Run SDK streaming as a Textual managed worker."""
        # Disable input before streaming starts
        self.query_one(CommandInput).disabled = True
        self.post_message(StreamingStarted())  # custom message to create AssistantCell

        try:
            await self._sdk_client.query(text)
            async for message in self._sdk_client.receive_response():
                if isinstance(message, StreamEvent):
                    event = message.event
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            chunk = delta.get("text", "")
                            if chunk:
                                self.post_message(TokenChunk(chunk))
                elif isinstance(message, ResultMessage):
                    if message.usage:
                        self.post_message(TokensUpdated(message.usage))
        finally:
            self.post_message(StreamDone())
            self.query_one(CommandInput).disabled = False
```

### Pattern 2: MarkdownStream for Token Buffering

**What:** `Markdown.get_stream()` creates a `MarkdownStream` object that accumulates fragments and coalesces rapid writes, preventing render storms above ~20fps.

**When to use:** Any time text chunks arrive faster than the UI can render (i.e., always during SDK streaming).

**Actual API (verified in Textual 8.1.1):**
```python
# Source: .venv/lib/.../textual/widgets/_markdown.py line 1100-1137
from textual.widgets import Markdown

class AssistantCell(Widget):
    async def start_streaming(self) -> None:
        """Called when StreamingStarted arrives — mount Markdown widget and begin stream."""
        self._markdown = Markdown("")
        await self.mount(self._markdown)
        self._stream = Markdown.get_stream(self._markdown)  # starts internal asyncio.Task
        # Remove LoadingIndicator (thinking state)
        self.remove_class("thinking")

    async def append_token(self, chunk: str) -> None:
        """Route a TokenChunk into the MarkdownStream."""
        if self._stream:
            await self._stream.write(chunk)  # method is write(), NOT append()

    async def finalize(self) -> None:
        """Called on StreamDone — stop the stream and make cell immutable."""
        if self._stream:
            await self._stream.stop()
            self._stream = None
        self._is_streaming = False
```

**CRITICAL:** The method name is `write()`, NOT `append()`. The STATE.md concern flagged this uncertainty — it is now resolved. The internal `MarkdownStream._run()` loop calls `Markdown.append()` internally, but the public API on `MarkdownStream` is `write()`.

### Pattern 3: Thinking Indicator

**What:** `LoadingIndicator` is mounted inside `AssistantCell` during the "waiting for first token" phase. On first `TokenChunk`, it is removed and the `Markdown` widget takes its place.

**When to use:** Before any text arrives from the SDK.

**Example:**
```python
# Source: .venv/lib/.../textual/widgets/_loading_indicator.py (verified)
from textual.widgets import LoadingIndicator

class AssistantCell(Widget):
    def compose(self) -> ComposeResult:
        yield Static("Conductor", classes="cell-label")
        yield LoadingIndicator()  # removed on first token

    async def on_token_chunk(self, event: TokenChunk) -> None:
        # First chunk — swap LoadingIndicator for Markdown streaming widget
        if self._stream is None:
            try:
                self.query_one(LoadingIndicator).remove()
            except NoMatches:
                pass
            await self.start_streaming()
        await self.append_token(event.text)
```

### Pattern 4: Reactive StatusFooter

**What:** `StatusFooter` uses `reactive` class attributes for `model`, `mode`, `token_count`, and `session_id`. Textual re-renders the widget automatically when any reactive changes.

**When to use:** Any widget that shows live state values that change asynchronously.

**Example:**
```python
# Source: textual.reactive (verified in .venv)
from textual.reactive import reactive
from textual.widgets import Static

class StatusFooter(Widget):
    model_name: reactive[str] = reactive("—")
    mode: reactive[str] = reactive("interactive")
    token_count: reactive[int] = reactive(0)
    session_id: reactive[str] = reactive("—")

    def compose(self) -> ComposeResult:
        yield Static(id="status-left", classes="footer-left")
        yield Static("Ctrl+C to quit", classes="footer-right")

    def watch_model_name(self, value: str) -> None:
        self._update_status()

    def watch_token_count(self, value: int) -> None:
        self._update_status()

    def _update_status(self) -> None:
        label = f"model: {self.model_name} | mode: {self.mode} | tokens: {self.token_count} | session: {self.session_id}"
        self.query_one("#status-left", Static).update(label)
```

### Pattern 5: Disabling CommandInput During Streaming

**What:** `Widget.disabled` is a `Reactive[bool]` on `Widget`. Setting it `True` greys the input and stops it accepting key events.

**When to use:** During the SDK streaming window to prevent re-submission.

**Example:**
```python
# Source: textual/widget.py line 346: disabled: Reactive[bool] = Reactive(False)
# In ConductorApp._stream_response() worker:
command_input = self.query_one(CommandInput)
command_input.disabled = True   # at start of stream
# ... stream ...
command_input.disabled = False  # in finally block
command_input.query_one(Input).focus()  # restore focus
```

### Anti-Patterns to Avoid

- **Calling `widget.update()` per-token:** Causes render thrash. Use `MarkdownStream.write()` which coalesces.
- **Using `Markdown.append()` directly per-token:** Same problem — the internal locking + asyncio.shield overhead per call exceeds 20fps budget. Use `MarkdownStream` which batches multiple pending fragments.
- **Running `ClaudeSDKClient.connect()` inside a Textual worker without exception handling:** SDK subprocess errors surface as `CLIConnectionError` / `ProcessError` — must catch and post a user-visible error message.
- **Forgetting `exit_on_error=False` on the worker:** Default is `True` which exits the entire app on any exception in the worker. For streaming, connection errors should show inline errors, not crash the app.
- **Keeping `ClaudeSDKClient` connected as a singleton at startup:** The SDK caveat states "you cannot use a ClaudeSDKClient instance across different async runtime contexts." Connect once in `on_mount` and keep alive for the session, OR reconnect per-query. Connecting once in `on_mount` is safer — matches the existing `chat.py` pattern (`_ensure_sdk_connected` lazy-connect).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token render batching | `asyncio.Queue` + `set_interval` + manual flush | `Markdown.get_stream()` → `MarkdownStream.write()` | Purpose-built; handles accumulation, event coalescing, and error cleanup internally |
| Thinking spinner | `set_interval` timer + mutable `Static` text | `LoadingIndicator` | Self-refreshing at 16fps, theme-aware, zero config |
| Worker lifecycle | `asyncio.create_task()` + `_background_tasks.add()` | `@work(exclusive=True)` | WorkerManager tracks state, cancels on app exit, exclusive mode prevents double-start |
| Reactive status display | Manual message handler + `self.update()` calls | `reactive` descriptors + `watch_*` methods | Textual schedules repaints automatically on reactive change |

**Key insight:** Every custom solution in this domain requires re-implementing render coalescing, error boundary handling, and cancellation cleanup. The Textual ecosystem has already solved each of these for 4.x.

## Common Pitfalls

### Pitfall 1: Wrong MarkdownStream Method Name
**What goes wrong:** Calling `stream.append(chunk)` raises `AttributeError` — the method is `write()`.
**Why it happens:** The `Markdown` widget itself has `append()` but `MarkdownStream` exposes only `write()` and `stop()`.
**How to avoid:** Always use `await stream.write(chunk)` on the `MarkdownStream` object. The `Markdown.append()` is the internal batched path that `MarkdownStream._run()` calls.
**Warning signs:** `AttributeError: 'MarkdownStream' object has no attribute 'append'`

### Pitfall 2: SDK StreamEvent Not Emitted (Missing include_partial_messages)
**What goes wrong:** `async for message in sdk_client.receive_response()` yields only `AssistantMessage` objects (full blocks after completion), not per-token `StreamEvent` chunks. The user sees no streaming — only the completed response.
**Why it happens:** `ClaudeAgentOptions.include_partial_messages` defaults to `False`. When `False`, the SDK does not surface raw Anthropic API stream events.
**How to avoid:** Set `include_partial_messages=True` in `ClaudeAgentOptions` — identical to the existing `chat.py` pattern (line 305).
**Warning signs:** No `TokenChunk` messages arriving; the full response appears at once after several seconds.

### Pitfall 3: Worker exit_on_error=True Crashes App on Connection Failure
**What goes wrong:** SDK connection errors (bad API key, subprocess launch failure) crash the entire Textual app instead of showing an inline error.
**Why it happens:** `@work` default is `exit_on_error=True`.
**How to avoid:** Always use `@work(exit_on_error=False)` for the SDK streaming worker. Catch `ClaudeSDKError` / `Exception` inside the worker and post a user-visible error message.
**Warning signs:** App exits with traceback on SDK connection failure.

### Pitfall 4: Forgetting to Re-focus Input After StreamDone
**What goes wrong:** After streaming completes, the input widget is re-enabled but the user's cursor focus is elsewhere — they must click the input field to type.
**Why it happens:** Setting `disabled = False` re-enables the widget but does not restore keyboard focus.
**How to avoid:** In the `StreamDone` handler: `self.query_one(CommandInput).query_one(Input).focus()`.
**Warning signs:** User must click input field after every response.

### Pitfall 5: ClaudeSDKClient Reconnection Across Event Loop Contexts
**What goes wrong:** Calling `sdk_client.connect()` in one Textual worker and then using it in another fails with `RuntimeError` or silent failures.
**Why it happens:** SDK caveat: "you cannot use a ClaudeSDKClient instance across different async runtime contexts." A Textual worker IS its own async context.
**How to avoid:** Connect the SDK client once in `on_mount` (not inside a `@work` coroutine). Store it on `ConductorApp`. The streaming `@work` coroutine only calls `query()` and `receive_response()` on an already-connected client.
**Warning signs:** Silent streaming failures, or `CLIConnectionError` on second query.

### Pitfall 6: AssistantCell Subscribing to TokenChunk Before Being Mounted
**What goes wrong:** The `@work` streaming coroutine posts `TokenChunk` messages before the new `AssistantCell` is mounted and visible — messages are dropped.
**Why it happens:** `app.post_message()` routes to handlers in the current widget tree. If `AssistantCell` is not yet mounted, its `on_token_chunk` handler does not exist.
**How to avoid:** The sequence must be: (1) mount `AssistantCell` → (2) `await pilot.pause()` / wait for mount — then start the SDK `@work`. Or post `TokenChunk` messages to the `AssistantCell` directly (not app-level) only after the mount confirmation.

## Code Examples

Verified patterns from official sources:

### SDK Streaming Loop (from existing chat.py)
```python
# Source: packages/conductor-core/src/conductor/cli/chat.py lines 402-462
from claude_agent_sdk import AssistantMessage, ResultMessage
from claude_agent_sdk.types import StreamEvent

# options must include: include_partial_messages=True
async for message in sdk_client.receive_response():
    if isinstance(message, StreamEvent):
        event = message.event
        if event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                chunk = delta.get("text", "")
                if chunk:
                    # post TokenChunk to app bus
                    self.post_message(TokenChunk(chunk))
    elif isinstance(message, ResultMessage):
        if message.usage:
            self.post_message(TokensUpdated(message.usage))
        # receive_response() auto-terminates after ResultMessage
```

### MarkdownStream Pattern (verified in Textual 8.1.1)
```python
# Source: .venv/lib/.../textual/widgets/_markdown.py lines 41-110 and 1100-1137
from textual.widgets import Markdown
from textual.widgets._markdown import MarkdownStream

# Inside a @work coroutine or after await self.mount(markdown_widget):
stream = Markdown.get_stream(markdown_widget)  # creates MarkdownStream and starts background task
try:
    while (chunk := await get_next_chunk()) is not None:
        await stream.write(chunk)   # write(), NOT append()
finally:
    await stream.stop()
```

### Textual @work Decorator
```python
# Source: .venv/lib/.../textual/_work_decorator.py (verified)
from textual import work

class ConductorApp(App):
    @work(exclusive=True, exit_on_error=False)
    async def _stream_response(self, text: str) -> None:
        """SDK streaming worker. exclusive=True cancels prior if still running."""
        ...
```

### LoadingIndicator (verified in Textual 8.1.1)
```python
# Source: .venv/lib/.../textual/widgets/_loading_indicator.py
from textual.widgets import LoadingIndicator

class AssistantCell(Widget):
    def compose(self) -> ComposeResult:
        yield Static("Conductor", classes="cell-label")
        yield LoadingIndicator()   # animated, auto_refresh=1/16, zero config
```

### Input Disable/Enable Pattern
```python
# Source: .venv/lib/.../textual/widget.py line 346
# disabled is Reactive[bool] = Reactive(False)
input_widget = self.query_one(CommandInput)
input_widget.disabled = True   # during streaming
# ... streaming completes ...
input_widget.disabled = False
input_widget.query_one(Input).focus()
```

### Reactive StatusFooter
```python
# Source: .venv/lib/.../textual/reactive.py lines 125-163
from textual.reactive import reactive

class StatusFooter(Widget):
    model_name: reactive[str] = reactive("—")
    token_count: reactive[int] = reactive(0)

    def watch_token_count(self, value: int) -> None:
        """Called automatically when token_count changes."""
        self._refresh_display()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `asyncio.Queue` + `set_interval` for token buffering | `Markdown.get_stream()` → `MarkdownStream` | Textual 4.x (in 8.1.1) | First-class streaming support; no timer management needed |
| `Static` widget with manual `.update()` per token | `Markdown` with `MarkdownStream.write()` | Textual 4.x | Handles markdown parsing + render coalescing |
| `asyncio.create_task()` with manual reference tracking | `@work(exclusive=True)` | Textual 2.x+ | WorkerManager lifecycle; no `_background_tasks` set needed for streaming |

**Deprecated/outdated:**
- Direct `widget.update()` per-token: replaced by `MarkdownStream.write()` which accumulates fragments
- Global `asyncio.create_task()` for long I/O: replaced by `@work` for tasks that post to the widget tree

## Open Questions

1. **Session ID source**
   - What we know: `ClaudeSDKClient.query()` takes a `session_id` parameter (default `"default"`). `ResultMessage` has a `session_id` field.
   - What's unclear: Is the session ID a stable UUID per `ClaudeSDKClient` instance or does it change per query?
   - Recommendation: Read `message.session_id` from the first `ResultMessage` and display it in `StatusFooter`. If it's always `"default"`, consider using a UUID generated on `on_mount`.

2. **Model name extraction**
   - What we know: `ClaudeAgentOptions` has no `model` field in the version installed. `ResultMessage` has no `model` field in the type definition reviewed.
   - What's unclear: How to get the actual model name the SDK is using (to show in status footer).
   - Recommendation: Get it from `get_server_info()` on the connected client, or hardcode from `ClaudeAgentOptions` if none available. The `get_server_info()` method returns server info including output style. Check at connect time.

3. **MarkdownStream thread safety with @work**
   - What we know: `MarkdownStream.write()` appends to a list and sets an `asyncio.Event`. `@work` runs as an asyncio task, not a thread.
   - What's unclear: Whether `MarkdownStream.write()` is safe to call from a `@work` coroutine (different asyncio task).
   - Recommendation: It should be safe — both run on the same event loop and `asyncio.Event.set()` is safe from any coroutine. But verify with a smoke test in Wave 1.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-textual-snapshot |
| Config file | packages/conductor-core/pyproject.toml |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_tui_streaming.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRNS-02 | Thinking indicator appears after submission | unit/headless | `pytest tests/test_tui_streaming.py::test_thinking_indicator_appears -x` | ❌ Wave 0 |
| TRNS-02 | TokenChunk appended to active AssistantCell | unit/headless | `pytest tests/test_tui_streaming.py::test_token_chunk_routes_to_cell -x` | ❌ Wave 0 |
| TRNS-02 | StreamDone finalizes cell and re-enables input | unit/headless | `pytest tests/test_tui_streaming.py::test_stream_done_finalizes -x` | ❌ Wave 0 |
| STAT-01 | StatusFooter updates token count on TokensUpdated | unit/headless | `pytest tests/test_tui_streaming.py::test_status_footer_token_update -x` | ❌ Wave 0 |
| STAT-01 | StatusFooter shows session ID | unit/headless | `pytest tests/test_tui_streaming.py::test_status_footer_session_id -x` | ❌ Wave 0 |

**Note on SDK mocking:** Tests cannot call the real SDK (requires API key + subprocess). All streaming tests use direct `post_message(TokenChunk(...))` and `post_message(StreamDone())` to simulate the worker output. The `@work` coroutine's SDK integration is covered by manual smoke testing.

### Sampling Rate
- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_tui_streaming.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui_streaming.py` — covers TRNS-02 and STAT-01
- [ ] No new framework config needed — existing pytest setup applies

## Sources

### Primary (HIGH confidence)
- `.venv/lib/python3.13/site-packages/textual/widgets/_markdown.py` — `MarkdownStream` class (lines 41-110), `Markdown.get_stream()` classmethod (lines 1100-1137), `Markdown.append()` (lines 1390-1430)
- `.venv/lib/python3.13/site-packages/textual/_work_decorator.py` — `@work` decorator full source
- `.venv/lib/python3.13/site-packages/textual/widget.py` line 346 — `disabled: Reactive[bool]`
- `.venv/lib/python3.13/site-packages/textual/reactive.py` lines 125-163 — `Reactive` descriptor pattern
- `.venv/lib/python3.13/site-packages/textual/dom.py` lines 494-540 — `run_worker()` API
- `.venv/lib/python3.13/site-packages/textual/widgets/_loading_indicator.py` — `LoadingIndicator` full source
- `packages/conductor-core/.venv/lib/.../claude_agent_sdk/client.py` — `ClaudeSDKClient` API, `receive_response()` contract
- `packages/conductor-core/.venv/lib/.../claude_agent_sdk/types.py` lines 888-898 — `StreamEvent` dataclass, `Message` union
- `packages/conductor-core/src/conductor/cli/chat.py` lines 361-476 — Working `_process_message()` SDK streaming reference

### Secondary (MEDIUM confidence)
- `packages/conductor-core/src/conductor/tui/messages.py` — Existing `TokenChunk`, `StreamDone`, `TokensUpdated` message types (project code, verified by reading)
- Textual 8.1.1 installed version verified via `python3 -c "import textual; print(textual.__version__)"`

### Tertiary (LOW confidence)
- None — all critical claims are verified from source files in the installed environment.

## Metadata

**Confidence breakdown:**
- SDK streaming API: HIGH — verified from `chat.py` working implementation + `client.py` source
- MarkdownStream API: HIGH — verified `write()` method name and `get_stream()` classmethod from installed Textual 8.1.1 source; STATE.md uncertainty resolved
- @work decorator: HIGH — read full source from installed Textual
- Pitfalls: HIGH — derived from SDK source inspection and Textual reactive documentation

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (Textual releases frequently but 8.x API is stable; SDK API is stable at 0.1.48+)
