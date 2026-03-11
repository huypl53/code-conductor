# Phase 38: Session Persistence & Polish — Research

**Researched:** 2026-03-11
**Domain:** Textual TUI — session replay, CSS animation, streaming polish
**Confidence:** HIGH

## Summary

Phase 38 is the final v2.0 milestone phase. It has two concrete requirements (STAT-02 and STAT-03)
plus an implicit end-to-end smoke test requirement. Both requirements can be satisfied entirely
within the existing codebase — no new dependencies are needed.

For STAT-03 (session replay), the `ChatHistoryStore` in `chat_persistence.py` already stores turns
as `{"role": "user"|"assistant", "content": "...", "timestamp": "...", "token_count": int}`. The
CLI entry point already passes `resume_session_id` to `ConductorApp.__init__`, which stores it as
`self._resume_session_id`. The gap is that `ConductorApp.on_mount` does not load or replay those
turns — it only sets the `StatusFooter.session_id`. The fix is to call
`ChatHistoryStore.load_session()` in `on_mount` and replay turns as static cells before enabling
input.

For STAT-02 (shimmer animation), Textual 8.1.1 does NOT support CSS `@keyframes` — the TCSS
parser has no keyframe rules. All animation in Textual is done through `Widget.animate()` (which
tweens numeric/CSS properties) or through `auto_refresh` with a time-based `render()` override.
The `tint` CSS property is animatable. The practical shimmer implementation is: in
`AssistantCell.start_streaming()`, begin a ping-pong tint animation (transparent → faint accent →
transparent) using `animate('styles.tint', ...)` with `on_complete` callback that re-triggers; in
`AssistantCell.finalize()`, call `stop_animation('styles.tint')` and reset tint to transparent.

**Primary recommendation:** Implement STAT-03 via a `_replay_session()` `@work` coroutine in
`ConductorApp.on_mount`, and STAT-02 via ping-pong `Widget.animate('styles.tint', ...)` on
`AssistantCell` during the streaming lifecycle.

---

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|-----------------|
| STAT-02 | In-progress cells show a shimmer/spinner animation | `tint` is in `StylesBase.ANIMATABLE`; `Widget.animate()` + `on_complete` ping-pong pattern confirmed; `AssistantCell.start_streaming()` / `finalize()` are the correct lifecycle hooks |
| STAT-03 | Resumed sessions replay previous conversation history in the transcript before the input activates | `ChatHistoryStore.load_session()` returns full turn list; `TranscriptPane.add_user_message()` and `add_assistant_message()` are the replay APIs; `CommandInput.disabled = True` before replay, `False` after is the activation gate |

</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| textual | 8.1.1 | TUI framework (already installed) | Project baseline — all prior phases use it |
| conductor.cli.chat_persistence | N/A (internal) | Session JSON store | Already implemented in Phase 20 — `ChatHistoryStore.load_session()` is the read API |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| textual.color.Color | bundled | Typed color value for `tint` animation | Used in `Widget.animate('styles.tint', Color(...), ...)` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tint` ping-pong via `animate()` | `auto_refresh` + time-based `render()` | `auto_refresh` forces full widget repaint every frame — heavier; `animate()` is Textual's native property tweening path |
| `tint` ping-pong | CSS class toggle with `set_interval` | CSS class toggle gives instant switch, not smooth fade; `animate()` gives gradual pulse |
| Static cell replay in `on_mount` | Streaming replay showing tokens sequentially | Streaming replay adds latency and complexity with no UX benefit for history |

**Installation:** No new packages needed.

---

## Architecture Patterns

### Session Replay Flow

```
ConductorApp.on_mount()
  ├── set StatusFooter.session_id (existing)
  ├── IF self._resume_session_id is not None:
  │     CommandInput.disabled = True   ← lock input before replay
  │     self._replay_session()          ← @work coroutine
  └── start dashboard if configured (existing)

@work _replay_session():
  conductor_dir = Path(self._cwd) / ".conductor"
  session = ChatHistoryStore.load_session(conductor_dir, self._resume_session_id)
  IF session is None: show error cell, re-enable input, return
  turns = session.get("turns", [])
  pane = self.query_one(TranscriptPane)
  # SUPPRESS the default welcome cell on resume (pass resume_mode=True)
  FOR turn in turns:
    IF turn["role"] == "user":   await pane.add_user_message(turn["content"])
    ELSE:                        await pane.add_assistant_message(turn["content"])
  CommandInput.disabled = False  ← unlock input after replay
  Input.focus()
```

### Shimmer Animation Pattern

```python
# In AssistantCell.start_streaming():
#   Start ping-pong tint: transparent -> faint accent -> transparent
from textual.color import Color

SHIMMER_TINT = Color(150, 150, 255, 0.12)   # faint accent tint
CLEAR_TINT   = Color(0, 0, 0, 0.0)          # transparent

def _shimmer_forward(self):
    self.animate(
        "styles.tint",
        SHIMMER_TINT,
        duration=0.7,
        easing="in_out_sine",
        on_complete=self._shimmer_back,
    )

def _shimmer_back(self):
    if not self._is_streaming:    # guard: stop if finalized
        return
    self.animate(
        "styles.tint",
        CLEAR_TINT,
        duration=0.7,
        easing="in_out_sine",
        on_complete=self._shimmer_forward,
    )

# In AssistantCell.finalize():
#   Stop shimmer and clear tint
self.stop_animation("styles.tint", complete=False)
self.styles.tint = CLEAR_TINT
```

### TranscriptPane Welcome Cell Suppression on Resume

`TranscriptPane.on_mount` currently always mounts a welcome cell. On resume, this cell would
appear before the replayed history, which is wrong. Two valid approaches:

**Option A — Constructor flag (preferred):**
```python
class TranscriptPane(VerticalScroll):
    def __init__(self, *, resume_mode: bool = False, **kwargs):
        super().__init__(**kwargs)
        self._resume_mode = resume_mode

    def on_mount(self) -> None:
        if not self._resume_mode:
            self.mount(AssistantCell("Welcome to Conductor..."))
```
`ConductorApp.compose()` passes `resume_mode=bool(self._resume_session_id)` to `TranscriptPane`.

**Option B — Remove and remount:**
Clear welcome cell in `_replay_session()` before mounting history cells.

Option A is cleaner: no post-mount widget removal needed.

### Recommended Project Structure (changes only)

```
src/conductor/tui/
├── app.py                      # add _replay_session() @work, update compose() for resume_mode
├── widgets/
│   └── transcript.py           # add resume_mode flag to TranscriptPane;
│                               # add shimmer methods to AssistantCell
tests/
└── test_tui_persistence.py     # NEW — Phase 38 tests
```

### Anti-Patterns to Avoid

- **Blocking on_mount with synchronous replay:** `on_mount` must remain async-safe; do replay
  in a `@work` coroutine so the screen renders before history cells mount.
- **Calling `add_assistant_streaming()` during replay:** History is complete text — use
  `add_assistant_message()` (static cells). Only streaming mode uses the
  `start_streaming()` / `append_token()` / `finalize()` lifecycle.
- **animate() on a non-mounted widget:** `animate()` requires the widget to be in the DOM.
  `_shimmer_forward()` must only be called from `start_streaming()`, which is called after
  `AssistantCell` is already mounted in `add_assistant_streaming()`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Session JSON storage | Custom file format | `ChatHistoryStore` (already exists) | Full crash-safe atomic-write implementation already in `cli/chat_persistence.py` |
| Looping CSS animation | Manual timer loop | `Widget.animate()` + `on_complete` ping-pong | Textual animator is frame-aware and respects `animation_level`; manual timer loop fights the event loop |
| Session picker UI | TUI modal picker | `pick_session()` in `cli/chat.py` (called before TUI starts) | Already implemented; runs in normal terminal mode before `ConductorApp.run()` is called |

**Key insight:** The persistence layer, session picker, and Textual animator are all already built.
Phase 38 is integration work, not infrastructure work.

---

## Common Pitfalls

### Pitfall 1: Animating tint Before Widget is Mounted
**What goes wrong:** `animate()` silently no-ops if the widget is not yet in the DOM.
**Why it happens:** `start_streaming()` is called from `_stream_response()` which runs in a `@work`
coroutine — the cell is already mounted by `add_assistant_streaming()` before `start_streaming()`
is awaited, so this is safe in the current flow. But tests that call `start_streaming()` directly
on a not-yet-mounted cell will see no animation.
**How to avoid:** In tests, always create cells inside a running app with `run_test()`.
**Warning signs:** `stop_animation` raises no error but tint never clears — indicates widget
was never in DOM when animate was called.

### Pitfall 2: Replay Cells Interleaved with Welcome Cell
**What goes wrong:** `TranscriptPane.on_mount` mounts the welcome cell unconditionally.
On resume, history cells are added after, making the transcript show welcome + history.
**How to avoid:** Add `resume_mode` constructor flag to `TranscriptPane`; pass it from
`ConductorApp.compose()` when `self._resume_session_id` is set.

### Pitfall 3: Input Enabled Before Replay Completes
**What goes wrong:** If `CommandInput.disabled = True` is set in `on_mount` but the `@work`
replay coroutine has scheduling lag, a fast user can submit before replay mounts.
**How to avoid:** Set `disabled = True` synchronously in `on_mount` before starting the
`@work` coroutine. The `@work` decorator ensures the coroutine runs in Textual's managed
worker pool, not as a raw asyncio task.

### Pitfall 4: `styles.tint` vs `tint` as animate() attribute
**What goes wrong:** Calling `self.animate("tint", ...)` may not work — the correct attribute
path for CSS properties accessed through `styles` is `"styles.tint"` in Textual's animator.
**How to avoid:** Use `self.animate("styles.tint", Color(...), ...)`. Confirm by checking
`StylesBase.ANIMATABLE` — `"tint"` is in the set, and Textual resolves `styles.<prop>` via
the bound animator.
**Warning signs:** Animation completes callback fires but widget color never changes visually.

### Pitfall 5: Shimmer Continues After finalize()
**What goes wrong:** The `on_complete` callback in `_shimmer_back` calls `_shimmer_forward`
in an infinite loop. If `_is_streaming` is set to `False` by `finalize()` mid-animation, the
next `on_complete` must check `_is_streaming` before re-queuing.
**How to avoid:** Guard every `_shimmer_*` callback with `if not self._is_streaming: return`.
Also call `stop_animation("styles.tint", complete=False)` in `finalize()` as belt-and-suspenders.

### Pitfall 6: ChatHistoryStore base_dir Path
**What goes wrong:** `ChatHistoryStore.load_session(base_dir, id)` expects `base_dir` to be the
`.conductor/` directory (it appends `chat_sessions/` internally). If the wrong path is passed
(e.g., the project root or `cwd`), the session file will not be found.
**How to avoid:** Always construct `conductor_dir = Path(self._cwd) / ".conductor"` and pass
that as `base_dir`.

---

## Code Examples

Verified patterns from codebase and Textual 8.1.1 source:

### Session Replay Worker

```python
# In ConductorApp (app.py)
@work(exclusive=False, exit_on_error=False)
async def _replay_session(self) -> None:
    """Replay prior conversation history as immutable cells."""
    from pathlib import Path
    from conductor.cli.chat_persistence import ChatHistoryStore
    from conductor.tui.widgets.transcript import TranscriptPane
    from conductor.tui.widgets.command_input import CommandInput
    from textual.widgets import Input

    conductor_dir = Path(self._cwd) / ".conductor"
    session = ChatHistoryStore.load_session(conductor_dir, self._resume_session_id)

    pane = self.query_one(TranscriptPane)
    if session is None:
        await pane.add_assistant_message(
            f"Session `{self._resume_session_id}` not found."
        )
    else:
        for turn in session.get("turns", []):
            if turn.get("role") == "user":
                await pane.add_user_message(turn["content"])
            else:
                await pane.add_assistant_message(turn["content"])

    cmd = self.query_one(CommandInput)
    cmd.disabled = False
    cmd.query_one(Input).focus()
```

### Shimmer Start/Stop in AssistantCell

```python
# textual.color.Color is the correct type for styles.tint
from textual.color import Color

_SHIMMER_ON  = Color(150, 150, 255, 0.12)
_SHIMMER_OFF = Color(0, 0, 0, 0.0)

async def start_streaming(self) -> None:
    # ... existing LoadingIndicator removal and Markdown mount ...
    self._shimmer_forward()   # start shimmer after cell is in DOM

def _shimmer_forward(self) -> None:
    if not self._is_streaming:
        return
    self.animate(
        "styles.tint", _SHIMMER_ON,
        duration=0.7, easing="in_out_sine",
        on_complete=self._shimmer_back,
    )

def _shimmer_back(self) -> None:
    if not self._is_streaming:
        self.animate("styles.tint", _SHIMMER_OFF, duration=0.2)
        return
    self.animate(
        "styles.tint", _SHIMMER_OFF,
        duration=0.7, easing="in_out_sine",
        on_complete=self._shimmer_forward,
    )

async def finalize(self) -> None:
    # ... existing stream stop ...
    self._is_streaming = False        # set BEFORE stopping animation
    self.stop_animation("styles.tint", complete=False)
    self.styles.tint = _SHIMMER_OFF
```

### Disabling Input During Replay (on_mount integration)

```python
async def on_mount(self) -> None:
    from conductor.tui.widgets.status_footer import StatusFooter
    from conductor.tui.widgets.command_input import CommandInput

    footer = self.query_one(StatusFooter)
    if self._resume_session_id:
        footer.session_id = self._resume_session_id
        # Lock input BEFORE starting replay worker
        self.query_one(CommandInput).disabled = True
        self._replay_session()
    else:
        footer.session_id = uuid.uuid4().hex[:8]

    if self._dashboard_port is not None:
        await self._start_dashboard()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CSS `@keyframes` for animation | `Widget.animate()` + `on_complete` ping-pong | Textual never supported keyframes | No CSS animation — must be done programmatically |
| `auto_refresh` + time-based render | `Widget.animate()` for smooth property tweening | Textual 0.x → current | `animate()` is frame-rate-aware; `auto_refresh` causes full repaints |

**Confirmed not available in Textual TCSS:**
- `@keyframes`: Not in TCSS tokenizer or parser — zero references to "keyframe" in textual/css source
- CSS `animation:` property: Not in `StylesBase.ANIMATABLE` or parsed TCSS properties
- CSS `transition:` property: Not in TCSS

---

## Open Questions

1. **`animate("styles.tint", ...)` vs `animate("tint", ...)`**
   - What we know: `"tint"` is in `StylesBase.ANIMATABLE`; `styles.tint` is the DOM path
   - What's unclear: Textual's animator may resolve `"tint"` directly without the `styles.` prefix via internal path resolution
   - Recommendation: Implement as `self.styles.tint = value` in a reactive-watch if `animate("styles.tint", ...)` does not visually tween. The watch pattern is: `reactive tint_phase: float = 0.0`, `watch_tint_phase` sets `self.styles.tint`, and `set_interval` increments `tint_phase` in a sine wave.

2. **Smoke test scope**
   - What we know: Success criterion 3 requires a full end-to-end smoke test covering launch, submit, stream, agent monitor, modal, slash command, resume
   - What's unclear: Whether this can realistically run headless without mocking the SDK and agents
   - Recommendation: The smoke test should be a headless Textual pilot test that mocks `_stream_response`, `_watch_escalations`, and the agent state path. It verifies each surface mounts correctly without crashing, not full live SDK integration.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 (mode=AUTO) + textual pytest plugin |
| Config file | `packages/conductor-core/pyproject.toml` |
| Quick run command | `/home/huypham/code/digest/claude-auto/.venv/bin/python -m pytest packages/conductor-core/tests/test_tui_persistence.py -v` |
| Full suite command | `/home/huypham/code/digest/claude-auto/.venv/bin/python -m pytest packages/conductor-core/tests/ -v` |

**Important pattern from prior phases:** Never put `run_test()` inside a fixture — always inline
in the test function. (Textual contextvars/pytest-asyncio incompatibility — tracked upstream.)

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STAT-03 | `ConductorApp(resume_session_id=X)` replays turns from JSON as UserCell + AssistantCell before input activates | integration (headless Textual) | `pytest packages/conductor-core/tests/test_tui_persistence.py::test_resume_replays_history -x` | ❌ Wave 0 |
| STAT-03 | Empty/missing session shows error cell, does not crash | unit | `pytest packages/conductor-core/tests/test_tui_persistence.py::test_resume_missing_session -x` | ❌ Wave 0 |
| STAT-03 | Input remains disabled until replay completes | integration (headless Textual) | `pytest packages/conductor-core/tests/test_tui_persistence.py::test_input_disabled_during_replay -x` | ❌ Wave 0 |
| STAT-02 | `AssistantCell._is_streaming=True` cell has non-zero tint | integration (headless Textual) | `pytest packages/conductor-core/tests/test_tui_persistence.py::test_streaming_cell_has_shimmer -x` | ❌ Wave 0 |
| STAT-02 | After `finalize()`, tint returns to transparent | integration (headless Textual) | `pytest packages/conductor-core/tests/test_tui_persistence.py::test_finalized_cell_clears_shimmer -x` | ❌ Wave 0 |
| End-to-end smoke | Full app lifecycle without crash | smoke (headless Textual, mocked SDK) | `pytest packages/conductor-core/tests/test_tui_persistence.py::test_e2e_smoke -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest packages/conductor-core/tests/test_tui_persistence.py -x`
- **Per wave merge:** `pytest packages/conductor-core/tests/test_tui_streaming.py packages/conductor-core/tests/test_tui_persistence.py -x`
- **Phase gate:** Full 634+ tests green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `packages/conductor-core/tests/test_tui_persistence.py` — covers STAT-02 and STAT-03 (all 6 tests above)

---

## Sources

### Primary (HIGH confidence)
- Codebase: `packages/conductor-core/src/conductor/tui/app.py` — full app lifecycle, `on_mount`, `_stream_response`, `@work` patterns
- Codebase: `packages/conductor-core/src/conductor/tui/widgets/transcript.py` — `AssistantCell` and `TranscriptPane` full source
- Codebase: `packages/conductor-core/src/conductor/cli/chat_persistence.py` — `ChatHistoryStore.load_session()` API
- Codebase: `packages/conductor-core/src/conductor/cli/__init__.py` — confirms `pick_session()` is called before `ConductorApp.run()`
- Textual 8.1.1 source: `StylesBase.ANIMATABLE` — confirmed `tint`, `opacity`, `background`, `color` are animatable
- Textual 8.1.1 source: TCSS parser — confirmed zero `@keyframes` or CSS `animation` support
- Textual 8.1.1 source: `LoadingIndicator` — reference implementation for `auto_refresh + render()` approach
- Textual 8.1.1 source: `Widget.animate()` — signature confirmed, `on_complete` callback confirmed

### Secondary (MEDIUM confidence)
- Textual demo `game.py` — reference `animate("offset", ...)` call pattern using simple string attribute names
- Prior phase tests (`test_tui_streaming.py`) — inline `run_test()` pattern, `pilot.pause()` for async settling

### Tertiary (LOW confidence)
- `animate("styles.tint", ...)` vs `animate("tint", ...)` exact attribute path — inferred from Textual internals but not tested in a running app

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are already installed and used in prior phases
- Architecture patterns (STAT-03 replay): HIGH — `ChatHistoryStore.load_session()` and `TranscriptPane.add_*` APIs are verified existing code
- Architecture patterns (STAT-02 shimmer): MEDIUM — `tint` animatability confirmed, exact `animate()` attribute path has LOW-confidence caveat (see Open Questions)
- Pitfalls: HIGH — derived from reading actual source code, not assumptions

**Research date:** 2026-03-11
**Valid until:** 2026-04-10 (Textual 8.x is stable; no major API churn expected)
