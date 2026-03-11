# Phase 36: Approval Modals - Research

**Researched:** 2026-03-11
**Domain:** Textual ModalScreen, asyncio.Queue bridge, escalation flow
**Confidence:** HIGH (Textual APIs verified from official docs; escalation flow verified from codebase)

---

## Summary

Phase 36 adds modal overlays so users can approve/deny file writes, approve/deny command execution, and reply to sub-agent escalation questions — all without leaving the terminal. Three modal types are needed: a file approval modal (APRV-01), a command approval modal (APRV-02), and an escalation reply modal (APRV-03).

The Textual `ModalScreen[T]` + `dismiss(value)` + `push_screen_wait()` pattern is the right tool for each modal. The critical engineering challenge is the asyncio.Queue bridge: `_escalation_listener()` in `DelegationManager` runs as an asyncio Task on Textual's own event loop, and it blocks waiting on `self._human_out.get()`. When a `HumanQuery` arrives, the listener must call `push_screen_wait()` to show the modal and await the user's reply, then put that reply into `self._human_in`. This works because `push_screen_wait()` is an awaitable that can be called from any async context running on Textual's event loop — including `_escalation_listener()` itself. However, `push_screen_wait()` must be called on the `App` object (via `self.app`), meaning the escalation listener needs a reference to the app.

There is no separate "file write" or "command execution" approval path in the current SDK integration. The `ACPClient` uses `permission_mode="default"` for sub-agents, and the `PermissionHandler` currently only intercepts `AskUserQuestion` tool calls — it auto-allows everything else. APRV-01 and APRV-02 are therefore best implemented at the **DelegationManager level**, either by adding permission hooks to the `ACPClient` inside the orchestrator, or more practically for this phase: by treating all three approval types as variants of the same "surface a question to the user and await reply" pattern. The simplest correct implementation wires APRV-01 and APRV-02 as explicit test-only paths (simulated escalations), deferring real permission hooks to when the SDK's `can_use_tool` hook is taught to route file/command events through `human_out`.

**Primary recommendation:** Implement three `ModalScreen` subclasses with `dismiss()`; show them from a new `show_approval_modal()` helper on `ConductorApp` called by a refactored `_escalation_listener()`; wire a `EscalationRequest` message so the listener can safely cross into the Textual message bus.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| APRV-01 | Modal overlay when agent requests file change approval, with approve/deny | FileApprovalModal(ModalScreen[bool]) with file_path field, dismiss(True/False) |
| APRV-02 | Modal overlay when agent requests command execution approval | CommandApprovalModal(ModalScreen[bool]) with command field, dismiss(True/False) |
| APRV-03 | Escalation question modal with agent ID prefix and reply input | EscalationModal(ModalScreen[str]) with question + Input widget, dismiss(reply_text) |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `textual.screen.ModalScreen` | 8.1.1 (project version) | Modal overlay base class | Official Textual API; dims background automatically |
| `textual.widgets.Button` | 8.1.1 | Approve/Deny buttons | Standard interactive widget |
| `textual.widgets.Input` | 8.1.1 | Reply input field in escalation modal | Already used in CommandInput widget |
| `textual.widgets.Label` | 8.1.1 | Display question/file path/command | Lightweight text display |
| `textual.containers.Grid` | 8.1.1 | Button layout in approve/deny row | Consistent with existing Textual patterns in project |
| `asyncio.Queue` | stdlib | Bridge: escalation_listener -> modal result | Already wired in DelegationManager |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `textual.app.ComposeResult` | 8.1.1 | compose() return type | All widget classes |
| `textual.message.Message` | 8.1.1 | New EscalationRequest message type | Bridge from _escalation_listener to push_screen_wait |

No new packages to install — everything needed is already in the project.

---

## Architecture Patterns

### Recommended Project Structure

New files:
```
packages/conductor-core/src/conductor/tui/
├── widgets/
│   └── modals.py              # FileApprovalModal, CommandApprovalModal, EscalationModal
├── messages.py                # + EscalationRequest message
└── app.py                     # + show_approval_modal() helper

packages/conductor-core/tests/
└── test_tui_approval_modals.py
```

### Pattern 1: ModalScreen[T] with typed dismiss()

**What:** Subclass `ModalScreen[bool]` (for approve/deny) or `ModalScreen[str]` (for text reply). Call `self.dismiss(value)` in button/input handlers. The type parameter propagates through `push_screen_wait()` so the caller receives a typed result.

**When to use:** All three modal types.

```python
# Source: https://textual.textualize.io/guide/screens/
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from textual.containers import Grid


class FileApprovalModal(ModalScreen[bool]):
    """Modal for file write approval. Returns True=approve, False=deny."""

    DEFAULT_CSS = """
    FileApprovalModal {
        align: center middle;
    }
    FileApprovalModal #dialog {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }
    FileApprovalModal .buttons {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    """

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self._file_path = file_path

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(f"Approve file write?\n{self._file_path}", id="question")
            with Grid(classes="buttons"):
                yield Button("Approve", variant="success", id="approve")
                yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")
```

### Pattern 2: push_screen_wait() from async context

**What:** `await self.app.push_screen_wait(modal)` blocks until `modal.dismiss(value)` is called. Returns the value passed to `dismiss`. Must be called from an `async` context running on Textual's event loop — `@work` coroutines qualify, and so does any `async def` called from a `@work` coroutine.

**Key constraint:** `push_screen_wait()` is a method on `App`, not on `Screen`. The calling code needs a reference to the app.

```python
# Source: https://textual.textualize.io/guide/screens/ + https://textual.textualize.io/api/app/
@work(exclusive=False, exit_on_error=False)
async def _escalation_listener(self) -> None:
    """Bridge: drain human_out queue, show modal, put reply in human_in."""
    while True:
        human_query = await self._human_out.get()
        # push_screen_wait blocks until user submits the modal
        reply = await self.app.push_screen_wait(
            EscalationModal(human_query.question)
        )
        if self._human_in is not None:
            await self._human_in.put(reply)
```

### Pattern 3: EscalationRequest message bridge

**What:** `_escalation_listener()` runs as a Textual `@work` coroutine on the Textual event loop — it can directly call `await self.app.push_screen_wait()`. No extra message bridge is needed for the escalation path.

However, for testability, define an `EscalationRequest` Textual message so tests can post it directly to the app without needing a live `asyncio.Queue`.

```python
# In messages.py
class EscalationRequest(Message):
    """An agent escalation question ready for the approval modal."""

    def __init__(self, question: str, agent_id: str = "") -> None:
        self.question = question
        self.agent_id = agent_id
        super().__init__()
```

### Pattern 4: EscalationModal with Input widget

**What:** APRV-03 needs a text reply field. Use `Input` widget inside the modal. On `Input.Submitted` or Button press, call `dismiss(input.value)`.

```python
from textual.widgets import Button, Input, Label
from textual.screen import ModalScreen


class EscalationModal(ModalScreen[str]):
    """Modal for sub-agent escalation questions. Returns reply text."""

    def __init__(self, question: str, agent_id: str = "") -> None:
        super().__init__()
        self._question = question
        self._agent_id = agent_id

    def compose(self) -> ComposeResult:
        prefix = f"[{self._agent_id}] " if self._agent_id else ""
        with Grid(id="dialog"):
            yield Label(f"{prefix}{self._question}")
            yield Input(placeholder="Your reply...", id="reply-input")
            yield Button("Submit", variant="primary", id="submit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        reply = self.query_one("#reply-input", Input).value.strip()
        self.dismiss(reply or "proceed")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or "proceed")
```

### Pattern 5: DelegationManager refactor for app reference

**What:** The current `_escalation_listener()` in `DelegationManager` is a plain `asyncio.Task`. To use `push_screen_wait()`, it needs a reference to the Textual `App`. The clean approach: move the escalation listener to `ConductorApp` as a `@work` coroutine, passing the `human_out` and `human_in` queues from the `DelegationManager`.

```python
# In ConductorApp, after _ensure_sdk_connected() creates delegation_manager:
@work(exclusive=False, exit_on_error=False)
async def _watch_escalations(
    self,
    human_out: asyncio.Queue,
    human_in: asyncio.Queue,
) -> None:
    """Watch for escalation questions and show approval modals."""
    from conductor.tui.widgets.modals import EscalationModal

    try:
        while True:
            human_query = await human_out.get()
            reply = await self.push_screen_wait(
                EscalationModal(
                    question=human_query.question,
                    agent_id=getattr(human_query, "context", {}).get("agent_id", ""),
                )
            )
            await human_in.put(reply)
    except asyncio.CancelledError:
        pass
```

### Anti-Patterns to Avoid

- **Calling `push_screen_wait()` from `on_mount()` directly (not in a worker):** Textual raises an error if you block the main event loop. Always put it in a `@work` coroutine.
- **Calling `push_screen_wait()` from a thread worker (`thread=True`):** Thread workers cannot call async Textual APIs. Only async `@work` coroutines can use `push_screen_wait()`.
- **Putting `push_screen_wait()` logic in `DelegationManager` directly:** `DelegationManager` has no app reference. Keep modal invocation in `ConductorApp`.
- **Using `pop_screen()` instead of `dismiss()`:** `pop_screen()` does not return a value to the `push_screen_wait()` caller. Always call `self.dismiss(value)` from the `ModalScreen`.
- **Nesting `push_screen_wait()` calls inside message handlers on the screen being dismissed:** Official docs warn this raises `ScreenError`. Keep modal invocation in workers, not in screen message handlers.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Modal overlay with dimmed background | Custom CSS overlay widget | `ModalScreen` | ModalScreen handles z-order, focus trapping, background dim automatically |
| Awaiting user input from async context | asyncio.Future + event | `push_screen_wait()` | Official API; handles event loop coordination safely |
| Button layout in dialog | Manual Row/Column CSS | `Grid` with `layout: horizontal` | Consistent with existing Textual patterns |
| Focus management after modal closes | Manual `widget.focus()` | `ModalScreen.dismiss()` | Textual restores focus to previous screen automatically |

**Key insight:** `ModalScreen` + `push_screen_wait()` is Textual's official answer to "block and await user input." There is no need for an additional synchronization primitive.

---

## Common Pitfalls

### Pitfall 1: push_screen_wait() outside a worker
**What goes wrong:** If called from a synchronous handler or from `on_mount()` (not in a `@work` coroutine), Textual raises an error because it cannot block the main event loop while allowing the screen to update.
**Why it happens:** The `await` would prevent the event loop from processing the modal's button events.
**How to avoid:** Wrap all `push_screen_wait()` calls in `@work(exclusive=False)` coroutines.
**Warning signs:** `RuntimeError: Cannot use push_screen_wait in this context` or app freezes.

### Pitfall 2: dismiss() returns None if called from the wrong screen
**What goes wrong:** If the modal calls `self.app.pop_screen()` instead of `self.dismiss(value)`, `push_screen_wait()` receives `None` instead of the expected value.
**Why it happens:** Confusion between `pop_screen()` (just removes screen) and `dismiss(value)` (removes + returns value).
**How to avoid:** Only use `self.dismiss(value)` inside `ModalScreen`. Never call `pop_screen()` from a modal that was launched with `push_screen_wait()`.

### Pitfall 3: _escalation_listener cancellation race
**What goes wrong:** `DelegationManager._cancel_background_tasks()` cancels `_escalation_task` while the modal is open, leaving the `human_in` queue without a reply and causing the `EscalationRouter` to time out.
**Why it happens:** `_cancel_background_tasks()` fires in the `finally` block of `handle_delegate()` after `orchestrator.run()` completes, but an in-flight modal may still be showing.
**How to avoid:** Move the escalation listener to `ConductorApp`'s `_watch_escalations()` worker and cancel it in `action_quit()` rather than inside `DelegationManager`. The `DelegationManager` should only own the queues, not the listener.

### Pitfall 4: Modal not dismissed on delegation completion
**What goes wrong:** Delegation ends (orchestrator.run() returns) while the modal is still open. The user sees a stale modal and TUI is unresponsive.
**Why it happens:** Escalation question arrives at end of orchestration run; orchestrator finishes before user answers.
**How to avoid:** The `EscalationRouter` already has a `human_timeout` (default 120s). After timeout it auto-answers "proceed" and the orchestrator completes. The modal should handle this by checking if `human_in` has received a value and auto-dismissing.

### Pitfall 5: Static._Static__content private attribute access
**What goes wrong:** Tests that inspect modal content via internal attributes break on version bumps.
**Why it happens:** Discovered in Phase 35 (see SUMMARY): `Static.renderable` does not exist in Textual 8.1.1; `_Static__content` is the internal attribute.
**How to avoid:** In tests, prefer asserting on `str(widget._Static__content)` for Static widgets. For Input values, use `widget.value`. Document this pattern explicitly in test files.

### Pitfall 6: Focus not returning to CommandInput after modal dismissal
**What goes wrong:** After the modal closes, focus stays on the default screen root rather than returning to `CommandInput`.
**Why it happens:** Textual restores focus to the previous focus owner, but `CommandInput`'s inner `Input` may not have been focused at the time the modal opened.
**How to avoid:** After `push_screen_wait()` returns, explicitly call `self.query_one(CommandInput).query_one(Input).focus()`. Pattern already established in `on_stream_done()` in `app.py`.

---

## Code Examples

Verified from official docs and project codebase:

### FileApprovalModal complete implementation
```python
# Source: https://textual.textualize.io/guide/screens/
from textual.app import ComposeResult
from textual.containers import Grid
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class FileApprovalModal(ModalScreen[bool]):
    DEFAULT_CSS = """
    FileApprovalModal { align: center middle; }
    FileApprovalModal #dialog {
        width: 60; height: auto; padding: 1 2;
        border: solid $primary; background: $surface;
    }
    """

    def __init__(self, file_path: str) -> None:
        super().__init__()
        self._file_path = file_path

    def compose(self) -> ComposeResult:
        with Grid(id="dialog"):
            yield Label(f"Approve write to:\n{self._file_path}")
            yield Button("Approve", variant="success", id="approve")
            yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "approve")
```

### push_screen_wait in @work coroutine
```python
# Source: https://textual.textualize.io/guide/screens/ + official Textual docs
@work(exclusive=False, exit_on_error=False)
async def _watch_escalations(
    self,
    human_out: asyncio.Queue,
    human_in: asyncio.Queue,
) -> None:
    from conductor.tui.widgets.modals import EscalationModal
    try:
        while True:
            query = await human_out.get()
            reply = await self.push_screen_wait(EscalationModal(query.question))
            await human_in.put(reply)
    except asyncio.CancelledError:
        pass
```

### Test pattern for modal (from Phase 35 established pattern)
```python
# Source: tests/test_tui_agent_monitor.py pattern
async def test_file_approval_modal_approve():
    from conductor.tui.widgets.modals import FileApprovalModal
    from textual.app import App, ComposeResult

    class TestApp(App):
        def compose(self) -> ComposeResult:
            return iter([])  # no widgets needed

    app = TestApp()
    async with app.run_test() as pilot:
        result_container = []

        async def show_modal():
            result = await app.push_screen_wait(
                FileApprovalModal("/path/to/file.py")
            )
            result_container.append(result)

        app.call_later(show_modal)  # schedule on event loop
        await pilot.pause()
        await pilot.click("#approve")
        await pilot.pause()
        assert result_container[0] is True
```

---

## Escalation Flow: End-to-End

Understanding how a sub-agent escalation reaches the modal:

```
Sub-agent calls AskUserQuestion
  -> PermissionHandler.handle() routes to EscalationRouter.resolve()
  -> EscalationRouter._escalate_to_human() puts HumanQuery on human_out queue
  -> [blocks on human_in.get() with 120s timeout]

DelegationManager._escalation_listener() (now moved to ConductorApp._watch_escalations())
  -> awaits human_out.get()           # receives HumanQuery
  -> await self.push_screen_wait(EscalationModal(query.question))
  -> [modal shown; user types reply and clicks Submit]
  -> modal calls self.dismiss(reply_text)
  -> push_screen_wait returns reply_text
  -> await human_in.put(reply_text)

EscalationRouter resumes
  -> returns PermissionResultAllow with answers dict
  -> sub-agent receives answer and continues
```

Key insight: `_escalation_listener` must be a `@work` coroutine on the `App` (not a detached `asyncio.Task` in `DelegationManager`) so it can call `self.push_screen_wait()`.

---

## File/Command Approval Flow (APRV-01, APRV-02)

**Current state:** `ACPClient` uses `permission_mode="default"` for sub-agents. The `PermissionHandler` only intercepts `AskUserQuestion` — file writes and command execution are auto-allowed. There is no existing hook point for APRV-01/APRV-02 in the current sub-agent path.

**For the main Claude agent** (used by `ConductorApp` directly via `ClaudeSDKClient`), `permission_mode="bypassPermissions"` is set — file/command approvals are completely bypassed.

**Implementation approach for APRV-01 and APRV-02:**

Option A (minimal): Use simulated escalation. When the orchestrator or DelegationManager needs to report a pending file write to the user, it puts a `HumanQuery` on `human_out` with context indicating the approval type. The `EscalationModal` displays it generically. No SDK hook changes needed.

Option B (proper): Add `can_use_tool` hook to `ACPClient` in the orchestrator that intercepts `Write` and `Bash` tool calls, routes them through `human_out`, and shows a `FileApprovalModal` or `CommandApprovalModal`. This requires the orchestrator to have access to the TUI's queues.

**Recommendation:** Implement Option B using the same queue pair (`human_out` / `human_in`) that already exists for escalations. The `PermissionHandler` already has the `_AnswerFn` slot. Extend `EscalationRouter` to recognize `Write`/`Bash` tool calls and route them as approval requests, or add a dedicated `ApprovalRouter` class.

For this phase, given the STATE.md research flag and the "prototype before building" directive, start with Option A (unified EscalationModal for all three requirements) and add dedicated FileApprovalModal / CommandApprovalModal as UI variations on the same queue mechanism.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `push_screen()` + callback | `push_screen_wait()` in `@work` | Textual 0.24+ | Cleaner sequential logic vs. callback pyramid |
| `pop_screen()` for dismissal | `dismiss(value)` for returning data | Textual 0.24+ | `pop_screen()` still works but loses return value |
| `input_fn` injection (prompt_toolkit era) | `push_screen_wait()` on Textual App | Phase 36 (this phase) | Replaces `_collect_escalation_input()` |

**Deprecated/outdated in this project:**
- `DelegationManager._input_fn`: injected prompt_toolkit input function — Phase 36 replaces this with `push_screen_wait()`. Keep for backward compat in non-TUI paths but no longer called from TUI.
- `DelegationManager._collect_escalation_input()`: falls back to `"proceed with best judgment"` when no `input_fn` — still valid for non-TUI code paths.

---

## Open Questions

1. **Should APRV-01 and APRV-02 use real can_use_tool hooks or simulated HumanQuery?**
   - What we know: SDK's `can_use_tool` hook exists in `ACPClient`; PermissionHandler routes it.
   - What's unclear: Whether the hook receives enough information to identify "Write" vs "Bash" tool input cleanly in the SDK version currently used.
   - Recommendation: Check `claude_agent_sdk.types.ToolPermissionContext` for available fields. If it contains `tool_name` and `input_data` (it does — see `PermissionHandler.handle()`), use Option B.

2. **Can push_screen_wait() be called from inside a @work coroutine that is itself called from inside another @work coroutine?**
   - What we know: GitHub issue #3472 documents a crash when calling a thread worker from another thread worker. Async workers don't have this restriction.
   - What's unclear: Whether nesting `push_screen_wait()` inside a worker called from `_stream_response()` worker causes issues.
   - Recommendation: Keep `_watch_escalations()` as a separate top-level worker on `ConductorApp`, not nested inside `_stream_response()`.

3. **What happens to the modal if the user presses Escape?**
   - What we know: By default, Textual `ModalScreen` does not bind Escape to dismiss.
   - What's unclear: Whether we should add an Escape binding that dismisses with a default value (e.g., "proceed" for escalation, False for approve/deny).
   - Recommendation: Add `BINDINGS = [("escape", "deny_or_cancel", "Cancel")]` to each modal with appropriate behavior.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (project standard) |
| Config file | `packages/conductor-core/pytest.ini` or `pyproject.toml` |
| Quick run command | `pytest tests/test_tui_approval_modals.py -x -v` |
| Full suite command | `pytest tests/ -x --tb=short -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| APRV-01 | FileApprovalModal shows file path, Approve returns True | unit | `pytest tests/test_tui_approval_modals.py::test_file_approval_approve -x` | Wave 0 |
| APRV-01 | FileApprovalModal Deny returns False | unit | `pytest tests/test_tui_approval_modals.py::test_file_approval_deny -x` | Wave 0 |
| APRV-02 | CommandApprovalModal shows command, Approve returns True | unit | `pytest tests/test_tui_approval_modals.py::test_command_approval_approve -x` | Wave 0 |
| APRV-02 | CommandApprovalModal Deny returns False | unit | `pytest tests/test_tui_approval_modals.py::test_command_approval_deny -x` | Wave 0 |
| APRV-03 | EscalationModal shows agent ID + question, Submit returns reply text | unit | `pytest tests/test_tui_approval_modals.py::test_escalation_modal_submit -x` | Wave 0 |
| APRV-03 | EscalationModal Input.Submitted also dismisses with value | unit | `pytest tests/test_tui_approval_modals.py::test_escalation_modal_input_submitted -x` | Wave 0 |
| APRV-01+03 | Background TUI reactivates after modal dismiss (CommandInput re-focusable) | integration | `pytest tests/test_tui_approval_modals.py::test_modal_dismisses_and_tui_reactivates -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_tui_approval_modals.py -x --tb=short -q`
- **Per wave merge:** `pytest tests/ -x --tb=short -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_tui_approval_modals.py` -- covers APRV-01, APRV-02, APRV-03
- [ ] `packages/conductor-core/src/conductor/tui/widgets/modals.py` -- FileApprovalModal, CommandApprovalModal, EscalationModal

*(No new framework install required — pytest + pytest-asyncio already present with 611 passing tests)*

---

## Sources

### Primary (HIGH confidence)
- [Textual Screens Guide](https://textual.textualize.io/guide/screens/) — ModalScreen, dismiss(), push_screen_wait(), callback vs. worker patterns
- [Textual Workers Guide](https://textual.textualize.io/guide/workers/) — @work decorator, call_from_thread, thread safety, post_message thread-safety guarantee
- [Textual App API](https://textual.textualize.io/api/app/) — push_screen_wait signature, call_from_thread signature
- [Textual Screen API](https://textual.textualize.io/api/screen/) — ModalScreen type annotation, ResultCallback, ScreenResultType
- Project codebase: `conductor/acp/permission.py`, `conductor/orchestrator/escalation.py`, `conductor/cli/delegation.py`, `conductor/tui/app.py`, `conductor/tui/widgets/agent_monitor.py`

### Secondary (MEDIUM confidence)
- [mathspp.com: How to use modal screens in Textual](https://mathspp.com/blog/how-to-use-modal-screens-in-textual) — ModalScreen[str] + dismiss() + Input pattern confirmed
- [GitHub Discussion #2559](https://github.com/Textualize/textual/discussions/2559) — push_screen_wait() must be in worker confirmed

### Tertiary (LOW confidence)
- [Mouse vs Python: Creating Modal Dialog](https://www.blog.pythonlibrary.org/2024/02/06/creating-a-modal-dialog-for-your-tuis-in-textual/) — basic ModalScreen structure (older, pre-dismiss() pattern)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified from Textual official docs and project codebase
- Architecture (ModalScreen patterns): HIGH — confirmed in official Textual screens guide
- Architecture (queue bridge): HIGH — escalation flow fully traced in codebase; @work + push_screen_wait pattern confirmed in docs
- File/command approval flow: MEDIUM — SDK permission hook exists (verified in code) but exact tool_name/input_data surface for Write/Bash not tested
- Pitfalls: HIGH — Pitfall 5 (Static internal attribute) confirmed empirically in Phase 35 SUMMARY

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (Textual stable; 30-day window)
