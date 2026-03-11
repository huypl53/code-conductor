# Pitfalls Research

**Domain:** Adding UX polish (alt-screen, borderless CSS, animations, external editor) to existing Textual TUI — Conductor v2.1
**Researched:** 2026-03-11
**Confidence:** HIGH (codebase analysis + Textual official docs + confirmed Phase 38 bug log)

---

## Critical Pitfalls

### Pitfall 1: Widget.animate("styles.tint", ...) Fails — Dot-Path Attribute Not Resolved

**What goes wrong:**
`Widget.animate("styles.tint", Color(...), ...)` raises `AttributeError` at runtime. Textual's animator calls `getattr(self, attribute)` internally, and the dot-path `"styles.tint"` is not resolved — only top-level attribute names work. The animation callback fires but the tint never changes.

**Why it happens:**
This was the exact bug hit in Phase 38 (documented in `38-01-SUMMARY.md`, commit `cb4d868`). The research doc for Phase 38 recommended `animate("styles.tint", ...)` as the pattern, but live execution showed that Textual's `animate()` does a simple `getattr(widget, "styles.tint")` which fails since Python attribute access does not resolve dot paths. The fix was a `set_interval` + sine wave on `self.styles.tint` directly.

**How to avoid:**
Use `set_interval` + a manual sine-wave tick function that writes to `self.styles.tint` directly. Do not attempt `animate("styles.tint", ...)` or `animate("tint", ...)` unless the Textual version explicitly documents dot-path support in `ANIMATABLE`. The current implementation in `transcript.py` already uses the correct pattern:
```python
self._shimmer_timer = self.set_interval(_SHIMMER_INTERVAL, self._shimmer_tick)

def _shimmer_tick(self) -> None:
    self._shimmer_phase += _SHIMMER_INTERVAL
    t = (math.sin(2 * math.pi * self._shimmer_phase / _SHIMMER_PERIOD) + 1) / 2
    alpha = _SHIMMER_ON.a * t
    self.styles.tint = Color(_SHIMMER_ON.r, _SHIMMER_ON.g, _SHIMMER_ON.b, alpha)
```

**Warning signs:**
- `AttributeError: 'Styles' object has no attribute 'styles'` in logs
- Animation `on_complete` callback fires but widget color never visually changes
- Shimmer appears to work in unit tests (where `styles.tint` assignment is direct) but not in running app

**Phase to address:**
Any phase adding CSS property animations — verify against Textual source before choosing `animate()` over `set_interval`.

---

### Pitfall 2: Shimmer Timer Not Stopped on Widget Finalization — Timer Leak

**What goes wrong:**
`AssistantCell.finalize()` must stop the `set_interval` shimmer timer. If `_shimmer_timer.stop()` is not called before `self._is_streaming = False`, the timer callback keeps firing after the cell is finalized. Each tick checks `_is_streaming` and tries to clear the tint, but the timer itself runs indefinitely, consuming CPU and producing spurious widget refreshes on an immutable cell.

**Why it happens:**
`set_interval` returns a `Timer` object that runs independently of widget state. Unlike `animate()` which has built-in completion callbacks, `set_interval` has no automatic stop condition. If the finalization code path is interrupted by an exception, or if `_is_streaming` is set before `_shimmer_timer.stop()`, the orphaned timer continues ticking.

**How to avoid:**
In `finalize()`, always stop the timer first, then clear `_is_streaming`:
```python
async def finalize(self) -> None:
    if self._stream is not None:
        await self._stream.stop()
        self._stream = None
    # Stop timer BEFORE clearing streaming flag
    if self._shimmer_timer is not None:
        self._shimmer_timer.stop()
        self._shimmer_timer = None
    self.styles.tint = _SHIMMER_OFF
    self._is_streaming = False
```
The current implementation in `transcript.py` already does this correctly. New phases adding animations must replicate the same cleanup sequence.

**Warning signs:**
- CPU usage remains elevated after a response finishes streaming
- `_shimmer_tick` appears in profiling output on cells that are not actively streaming
- Timer count grows with each exchange (visible via `app._workers`)

**Phase to address:**
Phase adding shimmer or any `set_interval`-based animation — enforce stop-before-clear in code review.

---

### Pitfall 3: app.suspend() Race Condition — Textual Driver Eats Vim Keystrokes

**What goes wrong:**
When launching an external editor (vim) via `app.suspend()`, Textual's input driver thread continues reading stdin for a brief window after `suspend()` is called and before the editor takes terminal ownership. Keystrokes typed in the terminal during this race window are consumed by Textual and discarded. In practice: the user types in vim's normal mode but some characters go to Textual's input handler instead.

**Why it happens:**
This is a documented race in Textual issue #1093, fixed by PR #4064 (which introduced `app.suspend()`). The `suspend()` context manager is the correct approach, but the race window is not zero on all terminals. On Kitty terminal, escape sequences can still interfere with input handling even with `suspend()`.

**How to avoid:**
- Use `app.suspend()` as the context manager (not a manual termios save/restore). This is the only supported path for external editor integration.
- Do not spawn `subprocess.run(["vim", ...])` directly without `app.suspend()`. The terminal will be in raw mode when Textual runs; vim will receive a broken terminal.
- After the editor exits, read the temp file content inside the `with app.suspend():` block, before the block exits and Textual recaptures the terminal.
- Test on Kitty specifically if supporting that terminal — it has known edge cases.

```python
import tempfile, subprocess, os
async def _open_in_editor(self) -> str | None:
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        path = f.name
    with self.app.suspend():
        subprocess.run([os.environ.get("EDITOR", "vim"), path])
        content = open(path).read()
    os.unlink(path)
    return content.strip() or None
```

**Warning signs:**
- Vim opens but character input is garbled or missing on first keypress
- Terminal left in broken state (no echo, no line wrap) after vim exits
- Cursor remains hidden after returning to Textual

**Phase to address:**
Phase implementing Ctrl-G external editor integration — use `app.suspend()` from the start; do not prototype with raw `subprocess.run`.

---

### Pitfall 4: Terminal State Not Restored After Editor Crash or SIGKILL

**What goes wrong:**
If vim crashes (SIGSEGV, OOM kill, or user sends SIGKILL to the process), the `with app.suspend():` block exits without vim having restored terminal state. The terminal may be left in raw mode, no-echo, or with mouse tracking enabled. Textual recaptures the terminal and renders correctly — but if Textual itself then crashes or exits uncleanly, the user's shell is left broken (no echo, no line wrapping).

**Why it happens:**
`app.suspend()` saves terminal settings and restores them on block exit via a `try/finally`. But if the block exit itself raises an exception (e.g., the temp file write fails after vim exits), the `finally` may not complete. Additionally, `app.suspend()` does not catch SIGKILL — no cleanup runs on process kill.

**How to avoid:**
- Wrap the entire `app.suspend()` block in its own `try/except` inside the Textual event handler. Log errors; do not let them propagate up to crash the app.
- After exiting `suspend()`, immediately call `self.app.refresh()` to force Textual to re-assert its terminal state.
- For Ctrl-G integration, disable the Ctrl-G binding while the editor is open to prevent double-launch.

**Warning signs:**
- Terminal shows no echo after `conductor` exits following a vim crash
- Running `stty sane` is required to recover the terminal after testing
- Textual's `cursor_visible` flag is out of sync with terminal state

**Phase to address:**
Phase implementing external editor — add `try/except` around suspend block and post-exit `refresh()` call before merging.

---

### Pitfall 5: Borderless Design — CSS Specificity Fights with Widget DEFAULT_CSS

**What goes wrong:**
Removing borders from existing widgets via `conductor.tcss` (app-level CSS file) requires understanding Textual's CSS cascade. A rule like `Input { border: none; }` in `conductor.tcss` will win over `CommandInput Input { border: none; }` in `CommandInput.DEFAULT_CSS`. But a rule like `Input { border: tall $accent; }` in `Input.DEFAULT_CSS` (Textual's built-in widget CSS) will lose to any app-level rule. The failure mode is: a seemingly correct `border: none;` rule in `conductor.tcss` appears to do nothing because a compound selector in a widget's own `DEFAULT_CSS` has higher specificity.

**Why it happens:**
Textual's specificity rules: App-level CSS (CSS_PATH or CSS class var) wins over any widget `DEFAULT_CSS`. Within the same level, more-specific selectors win (IDs > classes > types). The existing `conductor.tcss` uses only ID and type selectors (`#app-body`, `Screen`). The widget `DEFAULT_CSS` uses compound type selectors like `CommandInput Input`. To remove a border declared in `CommandInput.DEFAULT_CSS`, the app-level rule must be at least as specific: `CommandInput Input { border: none; }` — not just `Input { border: none; }`.

There is also a known Textual bug (issue #1335, fixed in PR #1336) where DEFAULT_CSS from a widget's ancestor can override the widget's own DEFAULT_CSS when the widget has no instances mounted in other screens. This is fixed in Textual 8.x.

**How to avoid:**
- Use compound selectors in `conductor.tcss` that match the widget hierarchy: `CommandInput Input { border: none; }` not just `Input { border: none; }`.
- When making something borderless, target `border: none;` and also `padding: 0;` — padding is often set alongside border in DEFAULT_CSS and causes visual indentation even when the border is removed.
- Use `!important` only as a last resort for Textual built-in widgets with deeply nested DEFAULT_CSS rules.
- Test with `textual console` + CSS inspector to verify which rule is winning.

**Warning signs:**
- `border: none;` in `conductor.tcss` appears to have no effect on a widget
- Removing a widget's border leaves a gap/padding where the border was
- CSS rule works in isolation but not when the widget is inside a container

**Phase to address:**
Phase implementing borderless/minimal chrome design — audit each widget's `DEFAULT_CSS` for compound selectors before writing override rules.

---

### Pitfall 6: Input Auto-Focus Timing — focus() Before Widget Enters Focus Chain

**What goes wrong:**
Calling `self.query_one(CommandInput).query_one(Input).focus()` in `on_mount()` may not work if the widget has not yet entered Textual's focus chain. In Textual v2.0+, `allow_focus()` is evaluated during the focus chain update, which happens after `on_mount` completes — not during it. A `focus()` call during `on_mount` may be silently ignored if the widget's focusability state has not yet been registered.

**Why it happens:**
Textual issue #5605 (March 2025) documents that `can_focus` set in `on_mount` is no longer respected in v2.0+ because the focus chain is evaluated before mount handlers run. The same timing issue affects explicit `focus()` calls: if the widget has `disabled=True` at the time `focus()` is called, focus is rejected but no error is raised.

In the current code, `CommandInput` is disabled during session replay. After replay, `_replay_session()` calls `cmd.query_one(Input).focus()`. This works because `disabled` is set to `False` just before `focus()` — the sequence is correct. But any new phase that calls `focus()` during `on_mount` (before `disabled` state is resolved) will silently fail.

**How to avoid:**
- Always set `disabled = False` before calling `.focus()`.
- For auto-focus on startup, use Textual's built-in `FOCUS_ON_MOUNT` or `auto_focus` Screen attribute (a CSS selector) instead of manual `focus()` calls in `on_mount`:
  ```python
  class ConductorApp(App):
      AUTO_FOCUS = "#command-input Input"
  ```
- If overriding `allow_focus()` instead of `can_focus`, ensure the method returns the correct value before `focus()` is called — not after.
- Prefer `call_after_refresh(self.focus_input)` if `focus()` must be called during mount to defer it until after the focus chain is updated.

**Warning signs:**
- Input widget is visible but not focused on startup (cursor not blinking in the input)
- `widget.has_focus` is `False` immediately after calling `widget.focus()` in `on_mount`
- Focus lands on wrong widget after modal dismissal

**Phase to address:**
Phase adding auto-focus input on TUI start — use `AUTO_FOCUS` class attribute, not manual `focus()` in `on_mount`.

---

### Pitfall 7: Focus Stolen After Modal Dismissal

**What goes wrong:**
After an `EscalationModal` or approval modal is dismissed via `push_screen_wait()`, focus may return to Textual's default focus target (the first focusable widget) rather than `CommandInput`. This means the user must click or Tab to the input before they can type.

**Why it happens:**
Textual restores focus to the widget that had focus before the modal was pushed. If `CommandInput` was disabled during streaming when the modal opened, it was not in the focus chain — so there is no "previous focus" to restore. Textual falls back to its `AUTO_FOCUS` selector or the first widget in the FOCUS chain.

The current code in `app.py` already handles this manually:
```python
# Restore focus to CommandInput after modal dismissal
cmd = self.query_one(CommandInput)
cmd.query_one(Input).focus()
```
But this code is inside a `try/except` that silently swallows failures. If the widget is still disabled when this code runs, focus is silently dropped.

**How to avoid:**
- After `push_screen_wait()` returns, always check that `CommandInput.disabled == False` before calling `focus()`.
- Use Textual's `Screen.FOCUS_NEXT` or return focus explicitly by saving the focused widget before push and restoring it after.
- Do not rely on Textual's automatic focus restoration after modal dismissal — it is unreliable when widget `disabled` state changes during the modal's lifetime.

**Warning signs:**
- After dismissing a modal, the cursor is not in the input field
- User must press Tab to re-focus the input after every escalation
- Focus appears to be on a panel widget that is not interactive

**Phase to address:**
Same phase as modal approval overlay work — the focus restoration pattern must be verified for each modal type.

---

### Pitfall 8: alt-screen Mode — Mouse Escape Codes Printed to Terminal on Crash

**What goes wrong:**
If Textual crashes (unhandled exception in a worker or in `on_mount`) while in full alt-screen mode, Textual's cleanup may not run. Mouse tracking escape sequences (`\033[?1003l`, `\033[?1006l`) remain active in the terminal. The user's shell shows mouse movement as raw escape codes (`^[[M...`). Running `reset` or `stty sane` is required.

**Why it happens:**
Textual enables mouse tracking and alt-screen via terminal escape sequences. The driver registers a signal handler for SIGTERM and SIGINT to restore state, but unhandled exceptions in coroutines bypass this cleanup. This is a known issue (Textual #82 — "Mouse codes are printed to the terminal on exit").

**How to avoid:**
- Wrap the top-level `ConductorApp(...).run()` call in a `try/finally`:
  ```python
  try:
      ConductorApp(...).run()
  finally:
      # Belt-and-suspenders: ensure terminal cleanup
      import sys
      sys.stdout.write("\033[?1003l\033[?1006l\033[?1000l")
      sys.stdout.flush()
  ```
- Use `@work(exit_on_error=False)` on all workers that can raise exceptions, so Textual handles exceptions gracefully rather than crashing.
- Never use bare `asyncio.create_task()` for Textual background work — use `@work` so exceptions propagate through Textual's error handling path.

**Warning signs:**
- After a crash, mouse movements show as `^[[M` in the terminal
- Terminal remains in no-echo mode after `conductor` exits unexpectedly
- `stty -a` shows `raw` mode after a crash

**Phase to address:**
Phase implementing alt-screen mode — add the `try/finally` cleanup wrapper at the CLI entry point before any alt-screen features are enabled.

---

### Pitfall 9: Ctrl-G Binding Conflicts With Existing Textual Key Handling

**What goes wrong:**
Textual's `Input` widget has built-in keybindings that may intercept keys before app-level bindings run. Ctrl-G (`\x07`, BEL character) is not a standard Textual binding, but the key routing path is: widget bindings → screen bindings → app bindings. If `CommandInput` or the inner `Input` widget has an `on_key` handler that consumes all unrecognized keys (returning early), Ctrl-G will never reach the app-level `action_open_editor` binding.

**Why it happens:**
Textual's key routing: keys are first offered to the focused widget, then bubble up. A key is "consumed" if a handler calls `event.stop()` or if Textual matches it to a local binding. Since `CommandInput` uses a plain `Input` widget and does not override key handling, Ctrl-G should bubble up. But if `SlashAutocomplete` (textual-autocomplete) consumes key events to update its dropdown, it may intercept Ctrl-G before the app sees it.

**How to avoid:**
- Define Ctrl-G as an `App`-level binding: `BINDINGS = [Binding("ctrl+g", "open_editor", "Open editor")]`.
- Verify the binding reaches the app by testing with `textual console` and watching the key event log. If autocomplete intercepts it, add an explicit `on_key` handler in `CommandInput` that checks for `ctrl+g` before yielding to autocomplete.
- Do not use `ctrl+g` as the binding name — use `ctrl+g` (lowercase, with plus), not `C-g` or `^G`.

**Warning signs:**
- Pressing Ctrl-G in the input field does nothing (no log output, no editor opens)
- The binding appears in the footer help but does not activate
- Ctrl-G only works when the input is not focused

**Phase to address:**
Phase implementing Ctrl-G external editor — verify key routing with `textual console` before building editor plumbing.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `animate("styles.tint", ...)` instead of `set_interval` | Reads like declarative animation | `AttributeError` at runtime — dot-path not resolved by Textual animator | Never — use `set_interval` + direct `styles.tint` assignment |
| Manual `focus()` in `on_mount` without `disabled` check | Simple, obvious | Silent focus failure when widget is disabled; requires debugging to find | Never — always check `disabled == False` before calling `focus()` |
| `subprocess.run(["vim", ...])` without `app.suspend()` | One-liner | Terminal left in raw mode; Vim receives broken terminal input | Never — must use `app.suspend()` context manager |
| `border: none;` in TCSS without matching specificity | Quick visual change | Rule ignored when widget has higher-specificity DEFAULT_CSS | Never — match compound selector of the DEFAULT_CSS rule being overridden |
| Bare `try/except: pass` around `focus()` calls | Suppresses noise | Silent focus failures never investigated; UX regression ships undetected | Only in non-critical paths with explicit comment explaining why |
| Alt-screen without `try/finally` terminal cleanup | Simpler entry point | Mouse codes in terminal after crash; user must run `reset` | Never in production — always add belt-and-suspenders cleanup |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| vim via Ctrl-G | `subprocess.run(["vim", ...])` without suspending Textual | `with app.suspend(): subprocess.run(["vim", path])` |
| vim exit and file read | Reading temp file after `suspend()` block exits | Read file inside the `with app.suspend():` block, before Textual recaptures terminal |
| `app.suspend()` in async context | `await asyncio.create_subprocess_exec(...)` inside suspend | `suspend()` is synchronous — use blocking `subprocess.run()`; do not mix async subprocess inside it |
| Border removal in TCSS | `Input { border: none; }` targeting Textual built-in widgets | Use compound selector: `CommandInput Input { border: none; }` to match DEFAULT_CSS specificity |
| `AUTO_FOCUS` vs manual `focus()` | Calling `Input.focus()` in `on_mount` before widget enters focus chain | Set `AUTO_FOCUS = "#command-input Input"` on `ConductorApp` class; remove manual `focus()` from `on_mount` |
| Shimmer + finalize order | Set `_is_streaming = False` before stopping timer | Stop timer first (`_shimmer_timer.stop()`), then clear tint, then set `_is_streaming = False` |
| Modal focus restoration | Rely on Textual's automatic post-modal focus restoration | Explicitly call `cmd.query_one(Input).focus()` after `push_screen_wait()` returns, with `disabled` check |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `set_interval` at > 30fps for shimmer | CPU spike; other widget updates lag | Use `_SHIMMER_INTERVAL = 1/15` (15fps max for tint animation) | > 30fps on low-end hardware or tmux with 60Hz refresh |
| Multiple shimmer timers per session | Timer count grows across exchanges; memory creep | Verify `_shimmer_timer is None` before calling `set_interval`; stop old timer if somehow active | After 10+ exchanges without restart |
| `app.refresh()` after every `app.suspend()` return | Full TUI repaint on every Ctrl-G press | Already handled by Textual — do not add manual `refresh()` unless cursor state is visually broken | Every editor open/close |
| Borderless design forcing 1px height reductions | Layout calculation changes cause off-by-one in height math | After removing borders, verify `height: 1fr` calculations still account for removed border space | After removing any border from a widget with explicit height |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| External editor opens but input field still shows content | Confusing state — content in input and editor | Clear `CommandInput` input field before opening editor; fill it with editor content on return |
| Ctrl-G binding not shown in status bar | User does not discover the feature | Add `Binding("ctrl+g", "open_editor", "Open editor", show=True)` — `show=True` makes it appear in footer |
| Borderless design removes visual input affordance | User cannot tell where to type | Keep a bottom border or background color on `CommandInput` to indicate the input region |
| Alt-screen hides terminal history above TUI | User cannot scroll back to pre-TUI output | This is expected and correct — document it; provide `/history` or similar to re-surface transcript |
| Focus auto-set to wrong widget on startup | User starts typing and input lands in wrong field | Use `AUTO_FOCUS` selector that targets the inner `Input` widget by ID, not the wrapper widget |
| Shimmer on too many cells simultaneously | Visual noise; performance hit | Only the currently-streaming cell should shimmer; all finalized cells are static |

---

## "Looks Done But Isn't" Checklist

- [ ] **Shimmer animation:** Verify `_shimmer_timer.stop()` is called in `finalize()` before `_is_streaming = False`. Check timer count after 5 exchanges.
- [ ] **External editor:** Test with `EDITOR=vim` and `EDITOR=nano`. Verify terminal state is clean after normal exit AND after Ctrl-C inside vim. Run `stty -a` after each test.
- [ ] **Borderless design:** Verify no compound-selector DEFAULT_CSS rules are being silently ignored. Use `textual console` CSS inspector to confirm winning rule for each changed widget.
- [ ] **Auto-focus:** Verify cursor is in the input field immediately on startup without any Tab press. Test with `ConductorApp` launched both fresh and in resume mode.
- [ ] **Focus after modal:** Dismiss an escalation modal, then immediately type — verify characters go to `CommandInput`, not to the transcript or agent panel.
- [ ] **Alt-screen crash cleanup:** Kill the process with `kill -9 <pid>` while TUI is running. Verify terminal is usable afterward (no raw mode, no escape code output).
- [ ] **Ctrl-G key routing:** Verify Ctrl-G works when focus is in `CommandInput` AND when focus is elsewhere (agent panel, etc.).
- [ ] **animate() not used:** Grep confirms no `self.animate("styles.tint"` or `self.animate("tint"` in the codebase — all shimmer is via `set_interval`.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Timer leak from unfinalised shimmer | LOW | Add `if self._shimmer_timer is not None: self._shimmer_timer.stop()` guard in `finalize()`; run existing shimmer tests |
| Terminal broken after editor crash | LOW | Add `try/except` around `app.suspend()` block; call `app.refresh()` on exit; add `try/finally` terminal cleanup at CLI entry point |
| Borderless CSS rule not applying | LOW | Inspect with `textual console`; add compound selector matching DEFAULT_CSS specificity; add `!important` only if compound selector fails |
| Focus not landing on input | LOW | Replace manual `focus()` in `on_mount` with `AUTO_FOCUS = "#command-input Input"` on `ConductorApp` |
| Ctrl-G intercepted by autocomplete | MEDIUM | Add explicit `on_key` in `CommandInput` to intercept and re-post Ctrl-G before autocomplete processes it |
| Modal dismissal loses focus | LOW | Ensure `disabled = False` before `focus()` call in post-modal handler; add explicit focus restoration in each `on_button_pressed` |
| Alt-screen mouse codes on crash | LOW | Add `try/finally` at CLI entry point; write escape codes to stdout in `finally` block |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| `animate("styles.tint")` AttributeError | Any new animation phase | Grep: zero `animate("styles.tint"` or `animate("tint"` in codebase |
| Shimmer timer leak | Phase adding shimmer/animations | Timer count stays constant across 10 exchanges; CPU stable after streaming ends |
| Ctrl-G / editor subprocess without suspend | Phase adding external editor | `stty -a` shows cooked mode after vim exits; no garbled input on first vim keystroke |
| Terminal state after editor crash | Phase adding external editor | `kill -TERM <vim-pid>` while in editor; TUI recovers; terminal clean after TUI exit |
| Borderless CSS specificity fight | Phase implementing borderless design | `textual console` confirms correct rule wins; no unintended widget gaps |
| Auto-focus timing | Phase adding auto-focus | Cursor in input on startup; no Tab required; works in both fresh and resume mode |
| Focus stolen after modal | Phase adding modal approval or Ctrl-G | Immediately type after modal dismissal; keystrokes land in input |
| Alt-screen cleanup on crash | Phase enabling full alt-screen mode | `kill -9` test; terminal clean; no mouse codes in output |

---

## Sources

- Codebase: `packages/conductor-core/src/conductor/tui/widgets/transcript.py` — confirmed `set_interval` shimmer implementation (Phase 38 bug fix) (HIGH confidence — direct code)
- Codebase: `.planning/phases/38/38-01-SUMMARY.md` — "Widget.animate('styles.tint') fails with AttributeError" confirmed in production (HIGH confidence — project history)
- [Textual issue #1093: Launching subprocesses like Vim from Textual apps](https://github.com/Textualize/textual/issues/1093) — `app.suspend()` race condition with stdin; fixed by PR #4064 (HIGH confidence — official repo)
- [Textual issue #5605: The moment of setting the focus has changed after 2.0.0](https://github.com/Textualize/textual/issues/5605) — `can_focus` set in `on_mount` ignored in v2.0+; `allow_focus()` override required (HIGH confidence — official repo, March 2025)
- [Textual issue #1335: Default CSS overrides more specific rules](https://github.com/Textualize/textual/issues/1335) — DEFAULT_CSS specificity bug; fixed in PR #1336 (HIGH confidence — official repo)
- [Textual issue #82: Mouse codes are printed to the terminal on exit](https://github.com/Textualize/textual/issues/82) — alt-screen escape code cleanup on crash (HIGH confidence — official repo)
- [Textual issue #5140: Gracefully handle termination signals](https://github.com/Textualize/textual/issues/5140) — SIGTERM/SIGKILL cleanup path (MEDIUM confidence — official repo)
- [Textual CSS Guide — Specificity](https://textual.textualize.io/guide/CSS/) — DEFAULT_CSS has lower specificity than app CSS; compound selectors for override (HIGH confidence — official docs)
- [Textual Animation Guide](https://textual.textualize.io/guide/animation/) — `Widget.animate()` signature; `set_interval` alternative (HIGH confidence — official docs)
- [Textual App Basics — app.suspend()](https://textual.textualize.io/guide/app/) — suspend() context manager behavior; Unix-only support (HIGH confidence — official docs)
- [Textual Discussion #4143: Input widget and auto focus disabling](https://github.com/Textualize/textual/discussions/4143) — `disabled` widget not receiving focus (MEDIUM confidence — official repo discussion)

---
*Pitfalls research for: v2.1 UX Polish — alt-screen, borderless CSS, animations, external editor on existing Textual TUI*
*Researched: 2026-03-11*
