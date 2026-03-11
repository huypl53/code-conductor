# Phase 39: Auto-Focus & Alt-Screen - Research

**Researched:** 2026-03-11
**Domain:** Textual TUI terminal lifecycle — `App.AUTO_FOCUS`, alt-screen default, SIGINT/Ctrl-C routing, post-modal focus restoration
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FOCUS-01 | Input is immediately active when the TUI starts — no Tab press or click needed | `AUTO_FOCUS = "CommandInput Input"` class variable on `ConductorApp`; fires on screen activation before user interaction |
| TERM-01 | Terminal switches to alt-screen on launch and restores prior scrollback completely on exit | Textual `App.run()` without `inline=True` already uses `LinuxDriver` which emits `\x1b[?1049h` at start and `\x1b[?1049l` at exit — verify CLI call site has no `inline=True` |
| TERM-02 | Pressing Ctrl-C triggers clean shutdown with terminal restored and shell prompt appearing normally | Textual's SIGINT handler calls `action_quit()`; `action_quit()` already implemented in `ConductorApp` — verify signal handler path and add `try/finally` terminal cleanup at CLI entry point |

</phase_requirements>

---

## Summary

Phase 39 is a focused, low-risk polish phase. The three requirements map to three distinct, independently implementable changes: a single class variable addition for auto-focus, a verification + fallback for alt-screen, and a signal/cleanup verification for clean exit. No new dependencies are needed — all APIs are already in `textual==8.1.1`.

The most critical finding is that **alt-screen is already the default** in Textual when `App.run()` is called without `inline=True`. The CLI entry at `packages/conductor-core/src/conductor/cli/__init__.py` line 55 calls `ConductorApp(...).run()` with no `inline=True` flag — so TERM-01 is already satisfied structurally. The work is verification and adding crash-cleanup safety.

**Auto-focus** is a single line: `AUTO_FOCUS = "CommandInput Input"` on `ConductorApp`. This handles both startup focus (FOCUS-01) and post-modal focus return (Success Criterion 4) because Textual re-evaluates `AUTO_FOCUS` when the main Screen reactivates after a modal is dismissed.

**Primary recommendation:** Add `AUTO_FOCUS`, verify no `inline=True` exists in the codebase, add `try/finally` terminal cleanup at the CLI call site, and verify SIGINT routes through `action_quit()`. All four changes fit in a single plan.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `textual` | `8.1.1` | TUI framework — `App.AUTO_FOCUS`, alt-screen via `App.run()`, SIGINT handling | Already installed; all Phase 39 APIs are in this version |

### Supporting

No additional libraries needed. Phase 39 uses only:
- `App.AUTO_FOCUS` (class variable on `ConductorApp`)
- `App.run()` default (no `inline=True`)
- Textual's built-in SIGINT handler → `action_quit()`
- Python stdlib `sys.stdout.write` for belt-and-suspenders terminal cleanup

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `AUTO_FOCUS = "CommandInput Input"` | `self.query_one(Input).focus()` in `on_mount` | `on_mount` focus call can silently fail if the widget's `disabled` state isn't resolved yet (Textual issue #5605). `AUTO_FOCUS` is the official API, fires after the focus chain is built, and also handles post-modal re-focus automatically. |
| `AUTO_FOCUS = "CommandInput Input"` | `AUTO_FOCUS = "Input"` | `"Input"` matches any Input widget in the tree (including modal inputs if a modal is somehow active). `"CommandInput Input"` is more specific and pins focus to the correct widget. |
| Textual's built-in SIGINT → `action_quit()` | Custom `signal.signal(SIGINT, handler)` | Textual registers its own SIGINT handler during `App.run()`. Adding a competing `signal.signal` call races with Textual's handler. Use `action_quit()` within Textual's lifecycle. |

**Installation:** No new packages needed.

```bash
# Verify textual version — no uv add required
uv run python -c "import textual; print(textual.__version__)"
# Expected: 8.1.1
```

---

## Architecture Patterns

### Recommended Change Set

All Phase 39 changes land in two existing files. No new modules needed.

```
conductor/tui/
├── app.py          # MODIFIED: add AUTO_FOCUS class variable
└── conductor.tcss  # OPTIONALLY MODIFIED: remove background: $surface from Screen (cosmetic)

conductor/cli/
└── __init__.py     # MODIFIED: add try/finally terminal cleanup around ConductorApp().run()
```

### Pattern 1: AUTO_FOCUS Class Variable

**What:** `App.AUTO_FOCUS` is a class variable that Textual evaluates as a CSS selector when any Screen activates. It focuses the first widget matching the selector. The default is `"*"` (first focusable widget).

**When to use:** Startup focus and post-modal focus restoration. Setting it once on `ConductorApp` covers all cases.

**Current gap:** `ConductorApp` has no `AUTO_FOCUS` declaration. The default `"*"` focuses the first focusable widget, which may not be the `Input` inside `CommandInput` if other widgets happen to be first in the focus chain.

**Implementation:**

```python
# packages/conductor-core/src/conductor/tui/app.py
class ConductorApp(App):
    CSS_PATH = Path(__file__).parent / "conductor.tcss"
    AUTO_FOCUS = "CommandInput Input"  # focus the Input inside CommandInput on screen activation
```

**Why `"CommandInput Input"` not `"Input"`:** Specificity. The app contains a `SlashAutocomplete` component that wraps an `Input`. Using the compound selector `"CommandInput Input"` ensures only the primary input bar is targeted.

**Post-modal behavior:** When an `EscalationModal` or approval modal is dismissed, the main Screen reactivates and Textual re-evaluates `AUTO_FOCUS`. This covers Success Criterion 4 (focus returns to input after modal dismissal) without any additional code. The existing explicit `cmd.query_one(Input).focus()` calls in `_watch_escalations` become redundant but harmless — leave them.

**Session replay interaction:** During session replay, `CommandInput.disabled = True` is set in `on_mount` before the `_replay_session` worker runs. `AUTO_FOCUS` fires during Screen activation, but Textual will not focus a `disabled` widget. Focus silently skips it. After replay completes, `_replay_session` already calls `cmd.disabled = False` then `cmd.query_one(Input).focus()` explicitly — this remains the correct pattern for the replay-done focus restoration.

**Source:** `App.AUTO_FOCUS` — documented Textual class variable. Default `"*"`, custom selector pins to specific widget. Screen re-evaluates on activation (confirmed in Textual App API docs). [HIGH confidence]

### Pattern 2: Alt-Screen Verification

**What:** Textual's `LinuxDriver` emits `\x1b[?1049h` (alt-screen enter) at startup and `\x1b[?1049l` (alt-screen exit) on clean exit. This is automatic when `App.run()` is called without `inline=True`.

**Current state:** CLI entry at `cli/__init__.py:55` calls `ConductorApp(...).run()` with no arguments — already correct.

**What to verify:** No `inline=True` appears anywhere in the TUI launch path. Run:

```bash
grep -r "inline=True" packages/conductor-core/src/conductor/tui/
grep -r "\.run(" packages/conductor-core/src/conductor/cli/
```

If either grep finds `inline=True`, remove it. Otherwise no code change is needed for TERM-01.

**Cosmetic improvement (optional):** The `conductor.tcss` Screen rule has `background: $surface`. This overrides the user's terminal background color, making the TUI look like a colored panel rather than a native terminal. Removing this rule makes the TUI feel more native:

```css
/* conductor.tcss — before */
Screen {
    layers: base overlay;
    background: $surface;  /* remove this line for native terminal background */
}

/* conductor.tcss — after */
Screen {
    layers: base overlay;
}
```

This is cosmetic (Phase 40 territory) but noted here because "restores prior scrollback completely" in TERM-01's success criterion is about the `\x1b[?1049` escape codes, not the background color. The alt-screen itself already works.

**Source:** Textual App guide — `inline=True` description and alt-screen default. `LinuxDriver.start_application_mode()` confirmed to emit `\x1b[?1049h`. [HIGH confidence]

### Pattern 3: Ctrl-C Clean Shutdown (SIGINT)

**What:** Textual registers a SIGINT handler during `App.run()`. When Ctrl-C is pressed, Textual calls `App.action_quit()` via its internal signal handling.

**Current state:** `ConductorApp.action_quit()` is already implemented (lines 426–434 in `app.py`). It disconnects the SDK, cancels background tasks, and calls `self.exit()`. This is the correct implementation.

**Gap — terminal cleanup on crash:** If the app crashes (unhandled exception in a worker, OOM kill, or SIGKILL) rather than exiting cleanly, Textual may not restore the terminal. Mouse tracking escape codes can be left active, causing the user's shell to show raw escape sequences.

**Fix — belt-and-suspenders terminal cleanup at CLI entry point:**

```python
# packages/conductor-core/src/conductor/cli/__init__.py
# in _default_callback:
try:
    ConductorApp(resume_session_id=session_id, dashboard_port=dashboard_port).run()
finally:
    # Belt-and-suspenders: ensure terminal is restored even on crash.
    # Textual handles this on clean exit; this covers crash/kill scenarios.
    import sys
    sys.stdout.write("\033[?1003l\033[?1006l\033[?1000l")
    sys.stdout.flush()
```

These three escape codes disable mouse tracking protocols (X10, extended coordinates, button-event). Textual's `LinuxDriver.stop_application_mode()` already emits these on clean exit, so writing them again on clean exit is harmless (idempotent).

**SIGINT routing verification:** Textual's internal SIGINT handler is registered during `Driver.start()`. It posts a `Quit` message to the App, which calls `action_quit()`. Since `ConductorApp.action_quit()` is defined and does clean teardown, Ctrl-C correctly flows through this path. No additional signal handling code is needed.

**Source:** Textual issue #82 (mouse codes printed on exit), Textual issue #5140 (graceful termination). `LinuxDriver.stop_application_mode()` source confirmed to emit `\033[?1003l\033[?1006l`. [HIGH confidence for escape codes, MEDIUM for full SIGINT routing path]

### Anti-Patterns to Avoid

- **`focus()` in `compose()`:** Widgets are not yet mounted during `compose()`. Any `focus()` call there is silently ignored.
- **`focus()` in `on_mount()` without disabled check:** If `CommandInput.disabled = True` when `on_mount` fires (resume mode), focus is silently rejected. The `AUTO_FOCUS` class variable respects disabled state correctly.
- **`set_timer` delayed focus call:** Using `self.set_timer(0.1, self._focus_input)` to defer focus is fragile — the delay is arbitrary and breaks under load. Use `AUTO_FOCUS`.
- **`signal.signal(SIGINT, handler)` competing with Textual:** Registering a custom SIGINT handler outside Textual's lifecycle races with Textual's own handler. `action_quit()` is the correct hook.
- **`inline=True` on `App.run()`:** This is the opposite of alt-screen — it renders the app inline under the shell prompt. Never use `inline=True` for the production TUI.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Auto-focus on startup | Custom `on_mount` timer or deferred `focus()` | `App.AUTO_FOCUS = "CommandInput Input"` | Textual's built-in handles focus chain timing, disabled state, and Screen reactivation (post-modal) all correctly |
| Alt-screen enter/exit | Manual `\x1b[?1049h`/`\x1b[?1049l` escape code emission | `App.run()` default (no `inline=True`) | Textual's `LinuxDriver` manages the full alt-screen lifecycle including bracketed paste, mouse tracking, and cursor visibility |
| SIGINT terminal restore | `signal.signal(SIGINT, ...)` with `termios.tcsetattr(...)` | `action_quit()` + `try/finally` cleanup at CLI entry | Textual's signal handler integrates with the asyncio event loop — a competing handler can deadlock or race |

**Key insight:** Terminal lifecycle management in Textual is owned entirely by the driver layer. Any manual escape code emission outside the `try/finally` cleanup safety net creates state divergence on crash paths.

---

## Common Pitfalls

### Pitfall 1: AUTO_FOCUS Fires Before CommandInput is Enabled in Resume Mode

**What goes wrong:** `AUTO_FOCUS = "CommandInput Input"` fires when the Screen activates, which happens before `on_mount` runs. In resume mode, `on_mount` sets `CommandInput.disabled = True` — but if `AUTO_FOCUS` has already tried to focus the widget at a different point, the disabled state may prevent it.

**Why it happens:** Textual evaluates `AUTO_FOCUS` during Screen activation. The Screen activates before `on_mount` handlers complete. The `disabled` flag is set inside `on_mount`.

**How to avoid:** This is actually fine in practice — Textual will not focus a disabled widget regardless of `AUTO_FOCUS`. When `_replay_session` finishes, it explicitly calls `cmd.disabled = False` then `cmd.query_one(Input).focus()`. The explicit call after replay is the correct and necessary path for resume-mode focus. `AUTO_FOCUS` handles the non-resume startup case.

**Warning signs:** In resume mode, if focus lands on the Input before replay completes and `disabled=True` is not effective, the user can type during replay. Test: launch with `--resume-id`, verify input is locked during replay.

### Pitfall 2: Terminal Escape Codes After Crash Leave Shell Broken

**What goes wrong:** SIGKILL or an unhandled exception in a Textual worker causes the process to exit without calling `Driver.stop_application_mode()`. Mouse tracking escape codes remain active. Shell shows `^[[M` on mouse movement.

**Why it happens:** Textual's cleanup is in `Driver.stop_application_mode()` which is called from `App.run()`'s `finally` block. SIGKILL bypasses all Python `finally` blocks. Unhandled exceptions in `@work` workers propagate to Textual's worker manager, which should call `App.exit()`, but if the exception is severe enough (e.g., in the event loop itself), `App.run()`'s `finally` may not run.

**How to avoid:** The `try/finally` wrapper at the CLI entry point (Pattern 3 above) covers this. It runs in the Python process `finally`, which executes even after most exception paths (but not SIGKILL).

**Warning signs:** After testing with `kill -9 <pid>`, run `stty -a | grep echo`. If echo is off, the terminal is broken. Run `stty sane` to recover.

### Pitfall 3: Focus Not Restored After Approval Modals

**What goes wrong:** After `FileApprovalModal` or `CommandApprovalModal` is dismissed, focus may land on a non-interactive widget instead of `CommandInput`.

**Why it happens:** `AUTO_FOCUS` fires on the main Screen reactivation after modal dismissal. But if `CommandInput.disabled = True` at the time (e.g., streaming is active when the modal closes), `AUTO_FOCUS` skips the disabled widget and focuses whatever is next in the focus chain.

**How to avoid:** The `_watch_escalations` worker in `app.py` already has explicit focus restoration after `push_screen_wait()` returns (lines 327–332). The approval modal handlers in Phase 36 need the same pattern verified. The `AUTO_FOCUS` approach does not replace this explicit check — it supplements it for the non-disabled case.

**Warning signs:** After dismissing any modal, immediately type a character — verify it appears in the CommandInput, not the transcript or agent panel.

### Pitfall 4: Ctrl-G Binding Intercepted Before Reaching App (Phase 42 Preview)

**What goes wrong:** If `Ctrl-G` binding is placed on `CommandInput` instead of `ConductorApp`, the `Input` widget's key handling may consume the key before it reaches the binding. App-level bindings have higher priority than widget-level bindings.

**Why it happens:** Textual key routing: focused widget first, then Screen, then App. `Input` widgets are in text-entry mode and pass unrecognized keys up. But `SlashAutocomplete` wraps the input and may intercept some keys.

**How to avoid:** This is a Phase 42 concern, not Phase 39. Noted here because Phase 39 establishes the terminal lifecycle that Phase 42 depends on. Phase 39 does NOT implement Ctrl-G — that is Phase 42.

---

## Code Examples

Verified patterns from official sources and codebase inspection:

### Adding AUTO_FOCUS to ConductorApp

```python
# packages/conductor-core/src/conductor/tui/app.py
# Source: Textual App API docs — App.AUTO_FOCUS class variable

class ConductorApp(App):
    CSS_PATH = Path(__file__).parent / "conductor.tcss"
    AUTO_FOCUS = "CommandInput Input"  # ADD THIS LINE

    # ... rest of class unchanged
```

### Belt-and-Suspenders Terminal Cleanup at CLI Entry

```python
# packages/conductor-core/src/conductor/cli/__init__.py
# Source: Textual issue #82 / PITFALLS.md Pattern 8

@app.callback(invoke_without_command=True)
def _default_callback(ctx: typer.Context, ...) -> None:
    """Launch interactive TUI when no subcommand is given."""
    if ctx.invoked_subcommand is not None:
        return

    from conductor.cli.chat import pick_session
    from conductor.tui.app import ConductorApp

    session_id = resume_id
    if resume and session_id is None:
        session_id = pick_session()
        if session_id is None:
            return

    try:
        ConductorApp(resume_session_id=session_id, dashboard_port=dashboard_port).run()
    finally:
        # Restore terminal state if Textual exited uncleanly (crash, kill).
        # On clean exit, Textual already emits these — idempotent to repeat.
        import sys
        sys.stdout.write("\033[?1003l\033[?1006l\033[?1000l")
        sys.stdout.flush()
```

### Verifying No inline=True

```bash
# Run from repo root — both should return no matches
grep -r "inline=True" packages/conductor-core/src/conductor/tui/
grep -r "\.run(" packages/conductor-core/src/conductor/cli/
```

Expected: the only `.run(` match is `ConductorApp(...).run()` with no `inline=True` argument.

### Existing Focus Restoration (Already Correct — Keep As-Is)

```python
# packages/conductor-core/src/conductor/tui/app.py — lines 161-168
# This pattern is already correct for post-stream focus
def on_stream_done(self, event: "StreamDone") -> None:
    cmd = self.query_one(CommandInput)
    cmd.disabled = False
    cmd.query_one(Input).focus()  # explicit focus after disabling ends

# lines 220-222 — also already correct for post-replay focus
cmd = self.query_one(CommandInput)
cmd.disabled = False
cmd.query_one(Input).focus()
```

These explicit `.focus()` calls are belt-and-suspenders alongside `AUTO_FOCUS`. They handle the case where the Screen was not deactivated (no modal push), which means `AUTO_FOCUS` does not re-fire. Keep them.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `focus()` in `on_mount()` | `App.AUTO_FOCUS = "selector"` class variable | Textual v0.40+ | `on_mount` focus can silently fail when widget is disabled or focus chain not yet built (issue #5605, March 2025) |
| Manual alt-screen escape codes | `App.run()` default (no `inline=True`) | Textual v0.1+ | Never write `\x1b[?1049h` manually — Textual owns the driver lifecycle |
| Custom SIGINT handler | Textual's built-in SIGINT → `action_quit()` | Textual v0.1+ | Competing signal handlers race with Textual's asyncio event loop integration |

**Deprecated/outdated:**
- Manual `focus()` in `on_mount` for startup focus: issue #5605 confirms timing problems in Textual 2.0+. `AUTO_FOCUS` is the replacement.
- `allow_focus()` override for startup focus: unnecessary for this use case — `AUTO_FOCUS` is cleaner.

---

## Open Questions

1. **SIGINT routing through action_quit() — complete verification**
   - What we know: Textual registers a SIGINT handler in `Driver.start()`. `ConductorApp.action_quit()` is implemented and does clean teardown.
   - What's unclear: Whether the SIGINT handler in Textual 8.1.1 specifically calls `action_quit()` or a lower-level `App.exit()`. The end result is similar but `action_quit()` also disconnects the SDK.
   - Recommendation: Test manually — run `conductor`, press Ctrl-C, verify SDK disconnect logs appear and shell prompt returns cleanly. If SDK disconnect doesn't happen on Ctrl-C, add explicit SIGINT handling that calls `asyncio.create_task(self.action_quit())`.

2. **AUTO_FOCUS with SlashAutocomplete widget**
   - What we know: `SlashAutocomplete` extends `AutoComplete` from `textual-autocomplete` and wraps the `Input`. The `AUTO_FOCUS = "CommandInput Input"` selector targets the `Input` inside `CommandInput`.
   - What's unclear: Whether `textual-autocomplete`'s `AutoComplete` wraps or replaces the `Input` in the widget tree, potentially changing the selector path.
   - Recommendation: Verify with a headless test that after app mount, `app.query_one("CommandInput Input")` resolves to the expected `Input` widget and `app.focused` is that widget.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8 + pytest-asyncio 0.23 + Textual `run_test()` pilot |
| Config file | `packages/conductor-core/pyproject.toml` — `asyncio_mode = "auto"` |
| Quick run command | `cd packages/conductor-core && uv run pytest tests/test_tui_focus_altscreen.py -x` |
| Full suite command | `cd packages/conductor-core && uv run pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOCUS-01 | Input receives focus on startup — no Tab needed | unit (headless pilot) | `pytest tests/test_tui_focus_altscreen.py::test_input_focused_on_startup -x` | ❌ Wave 0 |
| FOCUS-01 | AUTO_FOCUS selector resolves to CommandInput Input | unit (headless pilot) | `pytest tests/test_tui_focus_altscreen.py::test_auto_focus_selector_resolves -x` | ❌ Wave 0 |
| FOCUS-01 (SC4) | Focus returns to input after modal dismissal | unit (headless pilot) | `pytest tests/test_tui_focus_altscreen.py::test_focus_restored_after_modal -x` | ❌ Wave 0 |
| TERM-01 | No inline=True in TUI launch path | static grep | `pytest tests/test_tui_focus_altscreen.py::test_no_inline_true_in_launch -x` | ❌ Wave 0 |
| TERM-02 | action_quit() disconnects SDK and calls exit | unit (headless pilot) | `pytest tests/test_tui_focus_altscreen.py::test_ctrl_c_routes_through_action_quit -x` | ❌ Wave 0 |
| TERM-02 | try/finally terminal cleanup exists in CLI entry | static code inspection | `pytest tests/test_tui_focus_altscreen.py::test_cli_has_terminal_cleanup -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd packages/conductor-core && uv run pytest tests/test_tui_focus_altscreen.py -x`
- **Per wave merge:** `cd packages/conductor-core && uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_tui_focus_altscreen.py` — covers FOCUS-01, TERM-01, TERM-02 (all 6 test cases above)

**Note:** Existing test infrastructure covers all other phase concerns. Only the new test file needs creating in Wave 0.

**Test patterns to follow** (from `test_tui_foundation.py` and `test_tui_session_polish.py`):
- Use `async with app.run_test() as pilot:` inline in each test function — never in fixtures (Textual contextvars/pytest-asyncio incompatibility, GitHub #4998)
- Access `pilot.app.focused` to check which widget has focus
- Use `await pilot.pause()` after mount to let Textual process events

---

## Sources

### Primary (HIGH confidence)

- Textual installed at `.venv` (`textual==8.1.1`) — `App.AUTO_FOCUS` class variable confirmed, default `"*"`, evaluates as CSS selector on Screen activation
- Textual official App guide — `inline=True` runs inline mode; default (no `inline`) is alt-screen via `LinuxDriver`
- `packages/conductor-core/src/conductor/tui/app.py` — direct code read; `AUTO_FOCUS` absent; `action_quit()` implemented at lines 426–434; SIGINT hooks into Textual's driver
- `packages/conductor-core/src/conductor/cli/__init__.py` — direct code read; `ConductorApp(...).run()` at line 55, no `inline=True`
- `packages/conductor-core/src/conductor/tui/conductor.tcss` — direct code read; `background: $surface` on Screen confirmed
- `.planning/research/STACK.md` — v2.1 milestone pre-research confirming all APIs in textual 8.1.1
- `.planning/research/PITFALLS.md` — confirmed pitfalls: auto-focus timing (Pitfall 6), mouse escape codes on crash (Pitfall 8), focus stolen after modal (Pitfall 7)
- `.planning/research/ARCHITECTURE.md` — `AUTO_FOCUS = "Input"` pattern, CSS cascade, data flow diagrams

### Secondary (MEDIUM confidence)

- Textual issue #5605 (March 2025) — `can_focus` set in `on_mount` ignored in v2.0+; `AUTO_FOCUS` recommended replacement
- Textual GitHub issue #82 — mouse codes printed to terminal on crash; `\033[?1003l\033[?1006l\033[?1000l` as cleanup sequence
- Textual GitHub issue #1093 (resolved PR #4064) — `app.suspend()` pattern for external editors (Phase 42 dependency)
- Textual GitHub discussion #4143 — `AUTO_FOCUS = "Input"` pins focus to Input widget (community-verified)

### Tertiary (LOW confidence)

None — all claims are backed by official docs, direct code inspection, or project history.

---

## Metadata

**Confidence breakdown:**

- AUTO_FOCUS implementation: HIGH — class variable with documented semantics, confirmed in installed version
- Alt-screen status: HIGH — verified via CLI code read and Textual driver architecture; already working
- SIGINT routing: MEDIUM — Textual's SIGINT → `action_quit()` path is standard behavior but specific version confirmation requires manual test
- Terminal cleanup escape codes: HIGH — codes from Textual issue #82 and official driver source
- Post-modal focus via AUTO_FOCUS: HIGH — Screen reactivation re-evaluates AUTO_FOCUS (documented behavior)

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable Textual API — 30 day window)
