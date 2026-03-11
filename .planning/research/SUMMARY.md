# Project Research Summary

**Project:** Conductor v2.0 — Textual TUI Redesign
**Domain:** Python multi-agent orchestration CLI — replacing prompt_toolkit + Rich with a full Textual widget-based terminal UI
**Researched:** 2026-03-11
**Confidence:** HIGH

## Executive Summary

Conductor v2.0 is a terminal UI redesign for an existing Python multi-agent coding orchestration framework. The v1.x foundation (Claude Agent SDK integration, session persistence, slash commands, smart delegation, web dashboard) is fully built and preserved; v2.0 replaces only the UI layer — `prompt_toolkit` + Rich inline output — with a full `Textual`-based TUI that delivers the same UX quality as OpenAI's Codex CLI. Research confirms this is a well-documented migration path with a clear build order: Textual v4+ takes ownership of the asyncio event loop, all existing business logic (orchestrator, state management, delegation, dashboard server) plugs in as workers or tasks on that loop, and the new widget tree maps directly onto already-built infrastructure.

The recommended approach is an 8-phase incremental migration that builds from the inside out: static TUI shell first, then SDK streaming, then agent monitoring, then modals, slash commands, dashboard coexistence, and session persistence polish. Each phase is independently testable and the existing `conductor run` batch mode is untouched throughout. The most critical architectural decision — that Textual owns the event loop and everything else runs inside it — must be settled in Phase 1 before any UI work begins. Failure to do this produces cascading runtime errors that are expensive to unwind later.

The primary risks are architectural, not feature-level. Three patterns from the current codebase conflict directly with Textual: `asyncio.run()` alongside `App.run()`, Rich `Console.print()` calls during TUI lifetime, and `prompt_toolkit` terminal ownership. All three must be eliminated in Phase 1. Once event loop ownership is clean, the remaining phases follow well-documented Textual patterns and are medium-complexity at worst. The reference UX target (Codex CLI) maps precisely to available Textual widgets — no novel widget engineering is required.

## Key Findings

### Recommended Stack

The stack adds exactly one new runtime dependency: `textual>=4.0`. The existing `claude-agent-sdk>=0.1.48`, `rich>=13`, `watchfiles>=1.1`, `fastapi`, `uvicorn`, and `pydantic v2` are all preserved and reused. The `prompt_toolkit` dependency (added in v1.1) is fully removed in v2.0 — it cannot coexist with Textual. The optional third-party library `textual-autocomplete` (authored by a Textual team member) is added for slash command dropdown popups. No database, no new server, no new CLI framework.

**Core technologies:**
- `textual>=4.0`: Full TUI framework — owns the event loop, widget tree, CSS layout, and screen stack; `MarkdownStream` (v4 feature) enables efficient token-by-token streaming into cells
- `claude-agent-sdk>=0.1.48` via `ClaudeSDKClient`: Persistent multi-turn session with streaming — already present, wired into `SDKStreamWorker` via `@work` decorator
- `watchfiles>=1.1`: File event-driven state updates — already present, reused in `StateWatchWorker` watching parent directory (not `state.json` directly) due to atomic inode swap behavior
- `uvicorn.Config` + `uvicorn.Server` pattern: Dashboard server runs as `asyncio.create_task(server.serve())` inside Textual's loop — replaces `uvicorn.run()` which conflicts with existing loop
- `textual-autocomplete` (third-party, Textual team): Fuzzy dropdown popup for slash command suggestions

**Critical version note:** `MarkdownStream` requires Textual v4+. This is the primary new feature of Textual v4 and is specifically designed for LLM streaming patterns. `prompt_toolkit` is fully removed — both frameworks claim terminal raw mode and cannot coexist.

### Expected Features

The v2.0 MVP must prove the Textual redesign is credibly better than the current prompt_toolkit implementation. Full details in `.planning/research/FEATURES.md`.

**Must have (table stakes — v2.0 core):**
- Cell-based conversation transcript — discrete user/assistant cells in `VerticalScroll`; missing this makes the redesign feel worse than what it replaces
- Streaming text into active cell — token-by-token via `MarkdownStream`; static "thinking then full display" is a regression
- Visual "thinking" indicator — `LoadingIndicator` or `widget.loading = True`; users need feedback before first token
- Status footer bar — model name, mode, context utilization %; docked `Static` widget wired to existing `ContextTracker`
- Slash command autocomplete popup — `/` triggers `textual-autocomplete` dropdown; existing `SLASH_COMMANDS` dict becomes candidate list
- Modal approval overlays — `ModalScreen[bool]` replacing `_escalation_input()` for agent file/command approvals
- Web dashboard coexistence — uvicorn as `asyncio.create_task` in `on_mount`; both surfaces active simultaneously

**Should have (competitive advantage — v2.0 polish, after core is stable):**
- Inline agent monitoring panels — collapsible per-agent panels wired to `StateWatchWorker`; differentiator vs Codex CLI which has no equivalent
- Syntax-highlighted diffs in transcript — `RichLog.write(Syntax(diff_text, "diff"))` inline in cells
- Collapsible tool activity within cells — tool calls in `Collapsible`; expands during streaming, collapses after
- Shimmer/pulse animation on in-progress cells — CSS animation or `LoadingIndicator` on active cell border

**Defer (v2.x+):**
- `/theme` command with live preview — Textual CSS variable swap at runtime; not blocking the redesign
- Adaptive light/dark color scheme detection — purely additive
- Session picker as Textual `ModalScreen` overlay — current terminal UI is functional

**Anti-features to reject:**
- Full raw log view inside Textual — information overload is the documented v1.x UX problem; web dashboard handles full logs
- Inline file editor (`TextArea`) — creates accidental edits and focus traps; open `$EDITOR` via `app.suspend()` instead
- Persistent split-screen layout — wastes space when no agents are running; collapsible panels on demand is correct

### Architecture Approach

The architecture preserves all existing business logic and adds a new `conductor/tui/` module isolated from `cli/`. `ConductorApp` (Textual App root) replaces `ChatSession.run()` as the process entry point. Background workers (`@work` coroutines) drive SDK streaming, state file watching, and the dashboard server — all on Textual's event loop. Custom `Message` subclasses in `tui/messages.py` form the internal event bus; workers never call widget methods directly. The `DelegationManager` is modified minimally: its `input_fn` callback changes from a `prompt_toolkit` prompt to `push_screen_wait(EscalationModal(...))`, and the polling `_status_updater` / ANSI cursor `_clear_status_lines` methods are deleted entirely.

**Major components:**
1. `ConductorApp` (`tui/app.py`) — Textual App root; owns event loop lifecycle; launches workers in `on_mount`; replaces `asyncio.run(_run_chat_with_dashboard(...))`
2. `TranscriptPane` + `MessageCell` (`tui/widgets/transcript.py`) — scrollable conversation history; each assistant cell wraps `MarkdownStream` while streaming; immutable after `StreamDone`
3. `SDKStreamWorker` (`tui/workers/sdk_stream.py`) — `@work` coroutine driving `ClaudeSDKClient`; posts `TokenChunk`, `ToolActivity`, `StreamDone`, `TokensUpdated` messages
4. `AgentMonitorPane` + `AgentStatusRow` (`tui/widgets/agent_monitor.py`) — right-side panel with reactive status per agent; fed by `StateWatchWorker` via `StateChanged` messages
5. `StateWatchWorker` (`tui/workers/state_watcher.py`) — `watchfiles.awatch` on state file parent directory; replaces `_status_updater` polling
6. `ApprovalModal` + `EscalationModal` (`tui/screens/`) — `ModalScreen[bool]` and `ModalScreen[str]` pushed via `push_screen_wait()` from `@work` workers
7. `CommandInput` (`tui/widgets/command_input.py`) — `Input` widget with `textual-autocomplete` slash command popup
8. `StatusFooter` (`tui/widgets/status_footer.py`) — bottom bar docked via CSS; reactive labels wired to `ContextTracker`
9. `DashboardWorker` (`tui/workers/dashboard.py`) — `asyncio.create_task(uvicorn_server.serve())` in `on_mount`

### Critical Pitfalls

All 11 pitfalls researched are HIGH confidence based on official Textual docs and GitHub issues. The top 5 require Phase 1 attention. Full details in `.planning/research/PITFALLS.md`.

1. **Textual owns the event loop — no `asyncio.run()` cohabitation** — Make `ConductorApp(...).run()` the sole process entry point; run uvicorn and SDK as tasks inside `on_mount`; never use `nest_asyncio` as a workaround
2. **Rich `Console.print()` calls corrupt the Textual renderer** — Remove all `Console.print()` from code paths active during TUI lifetime; `_status_updater` / `_clear_status_lines` ANSI cursor codes are fatal and must be deleted; route all output through Textual widget messages
3. **`prompt_toolkit` cannot coexist with Textual** — Both frameworks claim terminal raw mode; full removal of `prompt_toolkit` imports from all TUI code paths is required; reimplement input history with Python `deque` and `Up`/`Down` key bindings
4. **Per-token `widget.update()` causes TUI flicker and CPU saturation** — Buffer streaming tokens; flush to `RichLog` or `MarkdownStream` at 20fps via `set_interval(0.05, flush_buffer)`; never call `Static.update()` per-token
5. **`asyncio.create_task()` without stored reference causes silent GC-collected workers** — Establish `_background_tasks: set[asyncio.Task]` with `add_done_callback(discard)` convention in Phase 1; prefer Textual `@work` which holds references automatically
6. **`push_screen_wait()` deadlocks if called from an event handler** — Call only from `@work` coroutines; event handlers delegate to workers
7. **Reactive attributes set in `__init__` trigger watchers before mount** — Initialize reactives to sentinel values in `__init__`; set real values in `on_mount`; guard watchers with `if not self.is_attached: return`
8. **Textual test / pytest-asyncio fixture incompatibility** — Put `async with app.run_test() as pilot:` inline in test functions, not fixtures; keep Textual tests in separate files from non-Textual asyncio tests

## Implications for Roadmap

Based on combined research, the architecture already provides an explicit 8-phase build order. The roadmap should follow this order; test infrastructure setup is a prerequisite for Phase 1, not deferred.

### Phase 1: Architecture Foundation and Event Loop Ownership

**Rationale:** Three existing patterns (`asyncio.run()`, `Console.print()`, `prompt_toolkit`) conflict fatally with Textual. These must be resolved before any widget work begins — they cannot be fixed incrementally after the fact. Event loop architecture is the load-bearing decision the entire build depends on.

**Delivers:** `ConductorApp` entry point replacing `asyncio.run(_run_chat_with_dashboard(...))`; clean test infrastructure separating Textual from non-Textual asyncio tests; zero `prompt_toolkit` imports in TUI code paths; verified SDK subprocess fd inheritance; `_background_tasks` reference-holding convention established

**Addresses:** Entry-point architecture, test infrastructure, SDK subprocess output audit

**Avoids:** Pitfalls 1 (event loop conflict), 2 (console corruption), 3 (prompt_toolkit coexistence), 5 (task GC), 9 (pytest incompatibility)

### Phase 2: Static TUI Shell

**Rationale:** Layout and routing must be verified with hard-coded content before live data is connected. Discovering layout bugs with static widgets is cheap; discovering them after SDK streaming is wired in is expensive.

**Delivers:** `MainScreen` two-column layout with `TranscriptPane`, `CommandInput`, `StatusFooter`, `AgentMonitorPane` placeholder; `CommandInput.Submitted` creates user `MessageCell`; app exits cleanly on `/exit`; Textual confirmed wired to CLI entry point

**Uses:** `textual>=4.0`, Textual CSS (`conductor.tcss`), `tui/messages.py` message bus

**Implements:** `ConductorApp`, `MainScreen`, `TranscriptPane`, `CommandInput`, `StatusFooter` (structural only)

### Phase 3: SDK Streaming

**Rationale:** Streaming is the core value of the TUI — it must be built as the third phase to maximize time for performance tuning before polish is layered on. The token buffering strategy must be baked in from the start, not retrofitted.

**Delivers:** Real Claude responses streaming token-by-token into `MarkdownStream`-backed assistant cells; tool activity lines inline; `StatusFooter` token counter live; visual "thinking" indicator before first token

**Uses:** `ClaudeSDKClient` with `include_partial_messages=True`, `MarkdownStream` (Textual v4), `@work` decorator, `TokenChunk`/`ToolActivity`/`StreamDone`/`TokensUpdated` messages

**Implements:** `SDKStreamWorker`, streaming `MessageCell`, token buffering at 20fps, `StatusFooter` reactive wiring

**Avoids:** Pitfall 6 (streaming performance saturation)

### Phase 4: Agent Monitor Panel

**Rationale:** Agent monitoring is architecturally independent from transcript streaming. Building it as a separate phase isolates the `StateWatchWorker` integration complexity and verifies `watchfiles.awatch` on parent directory behavior before modal work begins.

**Delivers:** Right panel showing live agent status rows when delegation is active; panel empty when no agents running; reactive status/elapsed updates without ANSI codes

**Uses:** `watchfiles.awatch` on parent directory, `StateChanged` custom messages, `Reactive` attributes on `AgentStatusRow`

**Implements:** `AgentMonitorPane`, `AgentStatusRow`, `StateWatchWorker`

**Avoids:** Pitfall 2 (ANSI cursor code deletion confirmed), known watchfiles inode-swap gotcha

### Phase 5: Escalation and Approval Modals

**Rationale:** Modal approval overlays require the escalation queue bridge (`human_out` → `Message` → `push_screen_wait()`) to be redesigned around Textual's screen lifecycle. Isolated phase makes testing clean and ensures delegation infrastructure from Phase 4 is proven before modals depend on it.

**Delivers:** `EscalationModal` (`ModalScreen[str]`) wired as new `input_fn` for `DelegationManager`; `ApprovalModal` (`ModalScreen[bool]`) for file/command approvals; background TUI remains live during modal display

**Uses:** `ModalScreen[T]`, `push_screen_wait()` from `@work` workers, `asyncio.Queue` + `Message` bridge pattern

**Implements:** `EscalationModal`, `ApprovalModal`, `DelegationManager.input_fn` swap, `_status_updater` deletion

**Avoids:** Pitfall 7 (modal approval event loop blocking)

### Phase 6: Slash Commands and Autocomplete

**Rationale:** Slash command routing and autocomplete are self-contained input-layer features. Building after modals ensures command dispatch doesn't interfere with modal screen push/pop.

**Delivers:** All 5 existing slash commands (`/help`, `/exit`, `/status`, `/summarize`, `/resume`) working; `textual-autocomplete` dropdown popup on `/` keypress; tab or enter selects

**Uses:** `textual-autocomplete`, `Input` with custom `Suggester`, existing `SLASH_COMMANDS` dict as candidate list

**Implements:** `CommandInput` slash dispatch, autocomplete popup wiring

### Phase 7: Dashboard Coexistence and CLI Wiring

**Rationale:** Dashboard coexistence is the final integration milestone. `uvicorn.Server.serve()` as `asyncio.create_task` in `on_mount` is the known-correct pattern; verifying it with a real WebSocket connection closes the event loop ownership story.

**Delivers:** `conductor --dashboard-port 8000` starts both Textual TUI and WebSocket server in one process; web dashboard connects and shows live state; `conductor run "..."` batch mode confirmed unaffected; `--resume`/`--resume-id` flags wired to `ConductorApp` constructor

**Uses:** `uvicorn.Config` + `uvicorn.Server` + `await server.serve()`, `asyncio.create_task`, existing `create_app(state_path)` unchanged

**Implements:** `DashboardWorker`, `conductor/cli/__init__.py` final replacement

**Avoids:** Pitfall 10 (uvicorn.run() inside Textual)

### Phase 8: Session Persistence and Polish

**Rationale:** Session persistence hooks into already-built `ChatHistoryStore`. Polish features (diffs, collapsible tool activity, shimmer animation) add value once the core UX is validated. Zero architectural risk.

**Delivers:** `ChatHistoryStore.save_turn()` called on `StreamDone`; session picker `ModalScreen` for `--resume`; syntax-highlighted code blocks verified in `Markdown` widget; syntax-highlighted diffs via `RichLog.write(Syntax(diff_text, "diff"))`; collapsible tool activity in cells; shimmer animation on active cells

**Uses:** Existing `ChatHistoryStore`, `RichLog.write(Syntax(...))`, `Collapsible` widget, CSS animation

**Implements:** Session persistence wire-up, session picker modal, v2.0 polish pass

### Phase Ordering Rationale

- Phases 1-2 are prerequisites for everything: event loop architecture determines whether Phases 3-8 work at all; the static shell verifies the framework is wired before live data is connected
- Phases 3-4 (streaming + agent monitor) are architecturally independent and could be parallelized; sequential ordering is recommended to keep integration complexity manageable
- Phase 5 (modals) must follow Phase 4 because `DelegationManager._status_updater` deletion spans the Phase 4/5 boundary
- Phases 6-7 are independent of each other and of Phase 5; they can be reordered without risk
- Phase 8 is additive polish — only begin after Phase 7 is fully validated

### Research Flags

Phases needing deeper research during planning:

- **Phase 3 (SDK Streaming):** `MarkdownStream` API is new in Textual v4 — verify `Markdown.get_stream()` and `await stream.append(chunk)` API surface against actual v4 release notes before coding; token buffering strategy needs validation against actual SDK streaming throughput numbers
- **Phase 5 (Escalation and Approval Modals):** The `asyncio.Queue` bridge from `DelegationManager._escalation_listener` to `push_screen_wait()` has no direct precedent in Textual docs — prototype this pattern before building the full modal stack; confirm `push_screen_wait()` from a `@work` coroutine vs direct event handler deadlock behavior is correctly understood

Phases with standard patterns (skip research-phase):

- **Phase 2 (Static Shell):** Standard Textual app composition; well-documented in official anatomy blog and widget gallery
- **Phase 4 (Agent Monitor):** `watchfiles.awatch` + `Reactive` attribute pattern is proven and replicates existing `dashboard/watcher.py`
- **Phase 6 (Slash Commands):** `textual-autocomplete` is well-documented; existing slash command dict is the candidate list
- **Phase 7 (Dashboard):** `uvicorn.Config` + `uvicorn.Server` is the documented correct approach; existing `create_app()` is unchanged

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Single new dependency (Textual v4); all others existing; versions confirmed from PyPI and official docs 2026-03-11 |
| Features | HIGH | Textual widget gallery + Codex CLI feature set directly mapped to Textual equivalents; anti-features explicitly documented from UX analysis of v1.x |
| Architecture | HIGH | 8-phase build order derived from official Textual patterns; integration points mapped from direct codebase review; component boundaries match Textual's documented architectural model |
| Pitfalls | HIGH | All 11 pitfalls sourced from official Textual docs, GitHub issues with root cause analysis, and direct codebase review; prevention patterns are official recommendations |

**Overall confidence:** HIGH

### Gaps to Address

- **`MarkdownStream` exact API surface:** ARCHITECTURE.md uses `Markdown.get_stream()` and `await stream.append(chunk)` — verify against actual Textual v4 release notes before Phase 3 begins; if API differs, `MessageCell` implementation needs adjustment
- **Claude Agent SDK subprocess fd inheritance:** PITFALLS.md flags that the SDK subprocess may write to inherited terminal stdout, bypassing Textual; must be verified in Phase 1 with a test delegation run; fix requires investigation of `ClaudeAgentOptions` pipe settings if output leaks
- **`textual-autocomplete` Textual v4 compatibility:** Documented as Textual 2.0+ compatible — verify no breaking changes at v4 before Phase 6

## Sources

### Primary (HIGH confidence)

- [Textual official docs](https://textual.textualize.io/) — widget gallery, workers guide, screens guide, `MarkdownStream`, `RichLog`, `LoadingIndicator`, CSS layout, `ModalScreen` pattern
- [Textual blog](https://textual.textualize.io/blog/) — anatomy of a Textual UI (cell-based chat pattern), high-performance compositor algorithms, Heisenbug (task GC), `MarkdownStream` v4 release
- [Textual GitHub issues](https://github.com/Textualize/textual/issues/) — #4998 (pytest fixture incompatibility), #5788 (event loop contamination), #600 (event loop ownership), #4691/#4570 (reactive before mount), #2952 (print capture), #3254 (Textual vs prompt_toolkit)
- [Claude Agent SDK official docs](https://platform.claude.com/docs/en/agent-sdk/) — `ClaudeSDKClient`, `include_partial_messages`, streaming output, subprocess architecture
- [PyPI: textual](https://pypi.org/project/textual/) — version confirmation
- [PyPI: claude-agent-sdk](https://pypi.org/project/claude-agent-sdk/) — version 0.1.48 confirmed 2026-03-07
- Existing Conductor codebase — `cli/chat.py`, `cli/delegation.py`, `cli/__init__.py`, `dashboard/server.py`, `dashboard/watcher.py` — direct code review for integration points

### Secondary (MEDIUM confidence)

- [darrenburns/textual-autocomplete](https://github.com/darrenburns/textual-autocomplete) — Textual 2.0+ compatible; authored by Textual team member; actively maintained
- [Uvicorn maintainer discussion: running inside existing loop](https://github.com/Kludex/uvicorn/discussions/2457) — `uvicorn.Server` + `Config` pattern for async contexts
- [Codex CLI official docs/changelog](https://developers.openai.com/codex/) — reference UX target; feature set comparison
- [prompt_toolkit official docs](https://python-prompt-toolkit.readthedocs.io/) — removal/migration reference

---
*Research completed: 2026-03-11*
*Ready for roadmap: yes*
