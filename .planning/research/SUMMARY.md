# Project Research Summary

**Project:** Conductor v2.1 — TUI UX Polish
**Domain:** Textual TUI polish — incremental UX milestone on existing v2.0 foundation
**Researched:** 2026-03-11
**Confidence:** HIGH

## Executive Summary

Conductor v2.1 is a focused UX polish pass on an existing, working Textual TUI. The v2.0 foundation is solid: 641 passing tests, a fully functional `ConductorApp` with streaming, session replay, agent monitoring, and slash command autocomplete. V2.1 adds five targeted improvements — auto-focus input, full alt-screen with clean exit, borderless/minimal chrome design, smooth cell animations, and Ctrl-G external editor integration — to bring the TUI to the standard set by OpenAI Codex CLI. Critically, all five features are implemented using APIs already present in `textual==8.1.1`. Zero new dependencies are required.

The recommended approach is to implement all five features in a single, low-risk milestone delivered in four sequential phases that respect dependency order. The three lowest-effort features (auto-focus, alt-screen verification, borderless CSS) establish a clean baseline before the two medium-complexity features (external editor, smooth animations) are added. Every feature is a targeted addition of roughly 5–30 lines to existing files — no new modules, no structural refactoring, no component tree changes.

The key risks are well-understood and avoidable. The Phase 38 codebase confirmed a production bug where `Widget.animate("styles.tint", ...)` fails at runtime with `AttributeError` because Textual's animator does not resolve dot-path attribute names; the shimmer was correctly fixed to use `set_interval`, and that precedent must hold for all new animation work. The external editor's `App.suspend()` call must run from a synchronous action or `@work(thread=True)` — using `async def` with `asyncio.create_subprocess_exec` instead leaves the terminal in a broken state. Both risks are fully documented and the mitigations are straightforward.

## Key Findings

### Recommended Stack

All v2.1 features are served by `textual==8.1.1` already installed. No new packages are needed. The five implementation surfaces are: `App.AUTO_FOCUS` class variable (auto-focus), `App.run()` default behavior (alt-screen), Textual CSS `border: none` (borderless design), `Widget.animate("opacity", ...)` (cell fade-in), and `App.suspend()` + `subprocess.run` inside a synchronous action (external editor).

**Core technologies:**
- `textual==8.1.1` — all five v2.1 APIs verified against the installed package source via `inspect`; zero new dependencies
- `asyncio` stdlib — existing `@work` worker threading model; no changes needed
- `tempfile` + `subprocess` stdlib — editor integration; no third-party deps
- `conductor.tcss` — single CSS file controls all layout borderless changes via Textual's specificity cascade

### Expected Features

**Must have (table stakes — v2.1 core):**
- **Auto-focus input on startup** — without this, users must Tab or click before typing; every reference tool (Codex CLI, aider, OpenCode) activates input immediately
- **Full alt-screen with clean exit** — TUI must own the terminal completely and restore it cleanly on any exit path; leaving escape code artifacts is a usability failure
- **Ctrl-G external editor** — power users composing multi-line prompts need a real editor; this is the standard Unix pattern (used by git commit, readline `edit-and-execute-command`)

**Should have (differentiators — v2.1 core):**
- **Borderless/minimal chrome design** — removes box-border visual clutter so content flows naturally; matches Codex CLI's content-first aesthetic
- **Smooth cell fade-in animations** — `Widget.animate("opacity", ...)` on `AssistantCell` and `UserCell` mount; makes the TUI feel alive rather than static

**Defer to v2.1 polish (P2 — add if time permits):**
- Responsive layout breakpoints — hide `AgentMonitorPane` below ~100 columns via CSS `@media` or `on_resize()`
- `CONDUCTOR_NO_ANIMATIONS=1` env var toggle — disables all `animate()` calls for CI/SSH use

**Defer to v2.2+ (P3):**
- Command history (up-arrow) across sessions — requires custom `Input` subclass, significant scope
- `/theme` live switching — CSS variable swap at runtime with modal picker
- Session picker as Textual `ModalScreen` — upgrade from plain-text session list

**Anti-features to explicitly reject:**
- Inline mode (`inline=True`) — conflicts with alt-screen goal; known Textual bug with command palette
- Animated splash/loading screen — adds startup latency when auto-focus already solves the "start typing immediately" need
- Full vim keybindings in `Input` — Ctrl-G to real vim covers the actual use case

### Architecture Approach

V2.1 makes surgical additions to four existing files and one new message type. The component tree is unchanged. `ConductorApp` receives `AUTO_FOCUS`, a new `Binding`, and `action_open_editor()`. `conductor.tcss` gets borderless Screen and container rules. `CommandInput` receives `on_editor_content_ready()`. `messages.py` gets `EditorContentReady`. The external editor flow uses the existing message bus pattern (consistent with `StreamDone`, `TokensUpdated`) rather than direct cross-widget method calls.

**Modified components and scope:**
1. `ConductorApp` (`app.py`) — `AUTO_FOCUS = "Input"`, `BINDINGS` entry, `action_open_editor()` method (~30 lines added)
2. `conductor.tcss` — remove `background: $surface` from Screen; remove layout container borders (~5 lines changed)
3. `CommandInput` (`command_input.py`) — soften `border-top`; add `on_editor_content_ready()` handler (~10 lines changed)
4. `messages.py` — add `EditorContentReady(Message)` (~6 lines added)
5. `transcript.py` — optionally add `on_mount` fade-in to `AssistantCell` and `UserCell` (~8 lines, fully additive)

**No new files needed.** No changes to `TranscriptPane`, `AgentMonitorPane`, `StatusFooter`, `modals.py`, or any streaming/replay workers.

### Critical Pitfalls

1. **`animate("styles.tint")` AttributeError (confirmed production bug, Phase 38)** — Textual's animator uses `getattr(widget, attribute)` and does not resolve dot-paths. Never use `animate("styles.tint", ...)` or `animate("tint", ...)`; all tint/shimmer animation must use `set_interval` + direct `self.styles.tint` assignment. Only use `animate()` for top-level style properties: `opacity`, `offset`.

2. **`App.suspend()` must be called synchronously** — Making `action_open_editor` an `async def` and using `asyncio.create_subprocess_exec` breaks terminal control; the editor and Textual fight over the terminal simultaneously. The action must be `def` (sync) calling `with self.suspend(): subprocess.run(...)` directly, OR wrapped in `@work(thread=True)`.

3. **CSS specificity — compound selectors required for borderless overrides** — `Input { border: none; }` in `conductor.tcss` does NOT override `CommandInput Input { border: none; }` in `CommandInput.DEFAULT_CSS` because the compound selector has higher specificity. Override rules must match or exceed the specificity of the `DEFAULT_CSS` rule being replaced. Verify with `textual console` CSS inspector.

4. **Auto-focus timing — use `AUTO_FOCUS` class var, not `on_mount` `focus()`** — Textual v2.0+ evaluates the focus chain before `on_mount` handlers run; a `focus()` call during `on_mount` is silently ignored if the widget is disabled or not yet registered. `AUTO_FOCUS = "Input"` fires on Screen activation (the correct timing). This is also the mechanism that correctly restores focus after modal dismissal.

5. **Shimmer timer leak on finalization** — `set_interval` timers run independently of widget state. `finalize()` must call `_shimmer_timer.stop()` before clearing `_is_streaming`; incorrect order causes the timer to fire indefinitely on completed cells. Current implementation is correct; new animation phases must replicate the stop-before-clear sequence.

## Implications for Roadmap

All five v2.1 features fit cleanly into four sequential phases that respect the dependency order confirmed in ARCHITECTURE.md. Each phase is independently testable and does not require the next phase to function.

### Phase 1: Foundation Fixes (Auto-focus + Alt-screen)

**Rationale:** These two features are zero-risk additions that establish the correct startup and exit baseline. Auto-focus must land before the external editor is implemented, as both touch focus management. Alt-screen verification — confirming no `inline=True` and adding a `try/finally` terminal cleanup at the CLI entry point — is a precondition for safely testing the editor's `suspend()` integration.

**Delivers:** TUI that starts with input immediately active; terminal fully taken over on launch; terminal restored cleanly on any exit path including SIGKILL.

**Addresses:** Auto-focus input on startup; full alt-screen with clean exit.

**Avoids:** Auto-focus timing pitfall (use `AUTO_FOCUS` class var, not `on_mount` focus); alt-screen mouse escape code leak on crash (add `try/finally` at CLI entry point writing `\033[?1003l\033[?1006l\033[?1000l` to stdout).

### Phase 2: Borderless Design

**Rationale:** Pure CSS changes with no Python logic; the lowest-risk phase. Should land before animations so the visual baseline is settled before motion is layered on top.

**Delivers:** Layout with no box-border chrome on Screen, `#app-body`, or `CommandInput`; `AgentMonitorPane` keeps its `border-left` as column separator; all modal borders intact; content-first aesthetic matching Codex CLI.

**Addresses:** Borderless/minimal chrome design.

**Avoids:** CSS specificity pitfall — use compound selectors matching DEFAULT_CSS specificity; audit each widget's `DEFAULT_CSS` for compound selectors before writing override rules; verify with `textual console`. Keep cell `border-left` as semantic role indicator — only remove chrome borders on layout containers.

### Phase 3: Ctrl-G External Editor

**Rationale:** Medium-complexity feature that depends on Phase 1 (stable alt-screen and terminal lifecycle) but is independent of Phase 2. Should land before animations because it has more surface area for terminal-state bugs that need thorough testing.

**Delivers:** Ctrl-G binding on `ConductorApp` that suspends the TUI, opens `$VISUAL`/`$EDITOR` (vim fallback) with current input content pre-populated, reads the result back, and fills `CommandInput` via the `EditorContentReady` message. Includes: guard for Ctrl-G during session replay (input locked); `SuspendNotSupported` catch for CI/non-Unix; `try/except` around the suspend block for editor crash recovery; `$VISUAL` honored before `$EDITOR` (POSIX convention).

**Addresses:** Ctrl-G external editor integration.

**Avoids:** Async `action_open_editor` pitfall (synchronous `def` action with blocking `subprocess.run`); Ctrl-G key routing conflict with `SlashAutocomplete` (verify with `textual console` key event log before wiring editor plumbing); terminal state not restored after editor crash (wrap suspend block in `try/except`).

### Phase 4: Smooth Animations

**Rationale:** Fully additive — no existing behavior changes. Lands last so the visual baseline (Phase 2) is settled. The simplest phase to revert: removing `on_mount` fade-in is a one-line revert. Include the `CONDUCTOR_NO_ANIMATIONS` env var toggle since it requires ~3 lines and prevents CI/SSH regressions.

**Delivers:** `AssistantCell` and `UserCell` fade in via `animate("opacity", 1.0, duration=0.25, easing="out_cubic")` on mount; existing shimmer unchanged; `CONDUCTOR_NO_ANIMATIONS=1` env var skips all `animate()` calls.

**Addresses:** Smooth animations and transitions; animation env var toggle (P2).

**Avoids:** `animate("styles.tint")` AttributeError — only use `animate("opacity")`; shimmer stays on `set_interval`. No new `set_interval` timers introduced; existing cleanup (stop-before-clear) is correct and need not change.

### Phase Ordering Rationale

- Phases 1 and 2 are both low-risk and establish the stable baseline that phases 3 and 4 build on.
- Phase 3 (external editor) before Phase 4 (animations) because Phase 3 has more terminal-state surface area; it should be thoroughly validated before animation complexity is added.
- Alt-screen verification (Phase 1) precedes external editor (Phase 3) because `App.suspend()` behavior in a broken alt-screen setup can mask subtle terminal state issues.
- Borderless design (Phase 2) before animations (Phase 4) because removing borders changes widget dimensions, which can affect animation offset calculations; settled layout first, then motion.

### Research Flags

Phases with well-documented patterns — standard implementations, skip additional research-phase:
- **Phase 1:** `AUTO_FOCUS` class variable and `App.run()` default behavior are official Textual APIs with confirmed signatures in `textual==8.1.1`.
- **Phase 2:** CSS borderless rules are straightforward; the only risk (specificity) is fully documented with a tested mitigation (compound selectors + `textual console` inspection).
- **Phase 4:** `Widget.animate("opacity", ...)` is a documented, well-tested Textual API; the constraint (no dot-paths) is internalized from Phase 38's confirmed bug.

Phase that warrants a focused pre-implementation prototype before full build:
- **Phase 3 (Ctrl-G editor):** The `App.suspend()` interaction with the specific terminal environment (tmux, Kitty edge cases documented in PITFALLS.md) should be verified with a 20-line spike — write to a tempfile, open the editor, read it back — before wiring the full message bus. Catching terminal-state bugs at the prototype stage is cheaper than mid-implementation.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All five APIs verified by direct `inspect` against installed `textual==8.1.1`; zero new dependencies confirmed |
| Features | HIGH | Direct codebase review of v2.0 source plus Textual official docs; feature scope is narrow and well-bounded |
| Architecture | HIGH | Changes are surgical additions to existing files; component boundaries and message bus patterns proven in v2.0 |
| Pitfalls | HIGH | Multiple pitfalls backed by confirmed project history (Phase 38 bug log) and official Textual issue tracker entries with root cause analysis |

**Overall confidence:** HIGH

### Gaps to Address

- **`$VISUAL` vs `$EDITOR` precedence inconsistency:** STACK.md specifies honoring `$VISUAL` before `$EDITOR` (POSIX convention); ARCHITECTURE.md's code sample only checks `$EDITOR`. Implementation in Phase 3 must honor `$VISUAL` first — reconcile before coding.

- **`action_open_editor` threading model:** STACK.md recommends `@work(thread=True)` wrapping the suspend call; ARCHITECTURE.md uses a synchronous `def` action calling `suspend()` directly. Both are valid but have different focus-restoration behaviors post-suspend. Decide on one pattern in Phase 3 and document the choice explicitly.

- **Kitty terminal compatibility with `App.suspend()`:** PITFALLS.md flags known edge cases with Kitty and stdin after suspend/resume. Test on Kitty if it is in the expected user base; otherwise accept that a follow-up fix may be needed.

- **Responsive layout breakpoints via CSS `@media`:** FEATURES.md references this as a P2 item but the `@media` syntax for width queries was not verified against `textual==8.1.1`. Verify the syntax before implementing in Phase 2 polish, or use the `on_resize()` handler approach instead.

## Sources

### Primary (HIGH confidence)

- `textual==8.1.1` installed at `.venv` — all APIs verified by `inspect` on the live package; `App.run()`, `App.AUTO_FOCUS`, `App.suspend()`, `Widget.animate()`, `@work(thread=True)`, `Binding("ctrl+g", ...)` all confirmed
- Conductor codebase: `app.py`, `conductor.tcss`, `command_input.py`, `transcript.py`, `messages.py`, `modals.py` — direct code inspection confirming v2.0 seams
- `.planning/phases/38/38-01-SUMMARY.md` — Phase 38 bug log confirming `animate("styles.tint")` AttributeError in production; `set_interval` fix
- [Textual App guide](https://textual.textualize.io/guide/app/) — `suspend()`, `inline` mode, `AUTO_FOCUS`
- [Textual App API](https://textual.textualize.io/api/app/) — `AUTO_FOCUS`, `suspend()`, `run()` signatures and defaults
- [Textual Animation Guide](https://textual.textualize.io/guide/animation/) — `animate()`, easing functions, animatable properties (`opacity`, `offset`)
- [Textual CSS Guide](https://textual.textualize.io/guide/CSS/) — specificity rules, DEFAULT_CSS cascade order
- [Textual Border styles](https://textual.textualize.io/styles/border/) — `none` vs `hidden` vs `blank` semantics; `none` collapses to zero width
- [Textual issue #1093](https://github.com/Textualize/textual/issues/1093) — `App.suspend()` pattern for external editors; race condition fixed in PR #4064
- [Textual issue #82](https://github.com/Textualize/textual/issues/82) — alt-screen escape code cleanup on crash

### Secondary (MEDIUM confidence)

- [Textual discussion #4143](https://github.com/Textualize/textual/discussions/4143) — `AUTO_FOCUS` class variable behavior; community-verified
- [Textual issue #5605](https://github.com/Textualize/textual/issues/5605) — `can_focus` set in `on_mount` ignored in Textual v2.0+; `allow_focus()` override required
- [Textual issue #4385](https://github.com/Textualize/textual/issues/4385) — inline mode conflicts with command palette; confirms full alt-screen is the correct choice for Conductor

---
*Research completed: 2026-03-11*
*Ready for roadmap: yes*
