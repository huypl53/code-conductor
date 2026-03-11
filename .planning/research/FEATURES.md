# Feature Research

**Domain:** Textual TUI redesign — replacing prompt_toolkit + Rich with a full widget-based terminal UI for a multi-agent coding orchestration framework (Conductor v2.0)
**Researched:** 2026-03-11
**Confidence:** HIGH (Textual official docs, Codex CLI official docs, direct code review of existing CLI, practitioner blog posts)

---

## Context: This Is a Subsequent Milestone

This research focuses exclusively on **what's needed for v2.0's Textual TUI redesign**. All v1.0–v1.2 features are already built and remain functional. The v2.0 goal is to replace `prompt_toolkit` + `Rich` with a full `Textual`-based TUI that matches the UX quality of Codex CLI.

**Existing infrastructure this new TUI sits on top of (all built, no changes needed):**
- Interactive chat REPL with prompt_toolkit (to be replaced)
- Rich-based streaming output (to be replaced/enhanced)
- Slash commands: `/help`, `/exit`, `/status`, `/resume`, `/summarize`
- Session persistence and resume (`ChatHistoryStore`, `.conductor/sessions/`)
- Smart delegation — orchestrator decides direct handling vs sub-agent teams
- Sub-agent status display (Rich tables via `/status` command)
- Web dashboard with real-time WebSocket updates (coexists with TUI)
- Context tracking (token utilization warnings)

**Reference UX:** OpenAI Codex CLI (Ratatui/Rust) — the target is to achieve equivalent UX in Python using Textual.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist when upgrading to a "proper TUI." Missing these = the redesign feels worse than the current prompt_toolkit implementation.

| Feature | Why Expected | Complexity | Textual Mechanism | Existing Dependency |
|---------|--------------|------------|-------------------|---------------------|
| Cell-based conversation transcript | Modern chat TUIs (Codex, OpenCode) all use discrete message cells, not a raw scrolling log. Each turn is visually distinct. | MEDIUM | Custom widget extending `Markdown`; `VerticalScroll` container with auto-scroll; `append()` per cell | `ChatHistoryStore` for session history; streaming events from SDK |
| Streaming text into active cell | Token-by-token text arrival is expected; a static "thinking then full display" feels broken | MEDIUM | `MarkdownStream` (coalesces rapid updates) or `RichLog.write()` appending chunks; `@work(thread=True)` for async streaming | Existing streaming in `_process_message()` — wire into Textual widget |
| Syntax-highlighted code blocks in transcript | Code output without highlighting is unreadable; users expect what Codex CLI delivers | LOW | `Markdown` widget natively syntax-highlights code fences; `RichLog.write(Syntax(...))` for standalone code blocks | None — purely additive |
| Visual "thinking" indicator before first token | Users need feedback that the agent is running, not frozen | LOW | `LoadingIndicator` widget (pulsating dots); or `widget.loading = True` property swaps any widget to loading state temporarily | Replaces current `[dim]Thinking...[/dim]` hack |
| Status footer bar | Codex CLI shows model/path in header; users expect current model, mode, token context info permanently visible | MEDIUM | Custom `Static` widget docked to bottom via CSS `dock: bottom`; reactive attributes auto-update display | `ContextTracker` already tracks token utilization — wire into footer |
| Slash command autocomplete popup | Users expect `/` to trigger visible suggestions; typing without a popup means guessing what commands exist | MEDIUM | `textual-autocomplete` library (fuzzy dropdown, Textual 2.0+ compatible) OR `Input` widget with built-in `suggester` parameter + `SuggestFromList` | Existing `SLASH_COMMANDS` dict becomes the candidate list |
| Modal approval overlays | Agent file changes and command execution require approval; a proper modal that grays out the background is the expected pattern | MEDIUM | `ModalScreen` class — push/pop screen stack; `dismiss(result)` returns approval decision; semi-transparent background built in | Existing escalation logic in `DelegationManager` — needs new UI surface |
| Keyboard-navigable approval dialogs | Arrow keys or Y/N hotkeys in approval modals; mouse-only dialogs feel wrong in a TUI | LOW | `Button` widgets in `ModalScreen`; `BINDINGS` class variable for Y/N keys | Part of modal approval implementation |

### Differentiators (Competitive Advantage)

Features that make the Textual TUI meaningfully better than both the current prompt_toolkit implementation and peer tools.

| Feature | Value Proposition | Complexity | Textual Mechanism | Existing Dependency |
|---------|-------------------|------------|-------------------|---------------------|
| Inline agent monitoring panels | While sub-agents work, dedicated collapsible panels show each agent's status, current tool, and live output — "dashboard-in-terminal." Codex CLI doesn't have this; the web dashboard does, but requires a browser. | HIGH | `Collapsible` widget per agent; `RichLog` inside each panel streaming tool activity; `DataTable` for compact multi-agent status view; updated via message-passing from state file watcher | `StatefulWatcher` (v1.0) already watches state file — wire events into Textual `post_message()` |
| Syntax-highlighted diffs in transcript | File change diffs inline in the conversation, not just "Edited auth.py: +12/-3". Codex CLI does this. | MEDIUM | `RichLog.write(Syntax(diff_text, "diff", theme=...))` — Rich's `Syntax` accepts language="diff"; `RichLog` accepts Rich renderables directly | Diff text available from ACP tool results — needs extraction and display |
| Shimmer/pulse animation on in-progress agent cells | Visual differentiation between completed cells (static) and cells that are still receiving streamed content (animated) | MEDIUM | `LoadingIndicator` CSS animation; or custom CSS `animation` keyframes on a border element; Textual supports CSS transitions on reactive properties | Part of cell-based transcript implementation — cells transition from "loading" to "complete" state |
| Collapsible tool activity within cells | Tool calls (file reads, edits, shell commands) shown as collapsible detail inside a response cell — not polluting the main transcript | MEDIUM | `Collapsible` widget nested inside response cells; expanded by default while streaming, collapsed after completion | Existing `format_tool_activity()` in `stream_display.py` — wrap in Collapsible |
| `/theme` command with live preview | Switch color themes without restarting; Codex CLI has this. Makes the TUI feel polished. | MEDIUM | Textual CSS variables can be swapped at runtime via `app.theme` or reactive CSS rewrites; `ModalScreen` for theme picker | New feature — no existing dependency |
| Adaptive color scheme (light/dark detection) | TUI respects the terminal's color scheme rather than hardcoding dark-mode colors | LOW | Textual has built-in `dark` property on `App`; CSS media queries for `@media (prefers-color-scheme: light/dark)` work in Textual | None — purely additive |
| Web dashboard coexistence with TUI open | Both surfaces active simultaneously — TUI for terminal interaction, web dashboard for remote/detailed/mobile monitoring | MEDIUM | Dashboard HTTP/WebSocket server runs in a background asyncio task; Textual app runs in foreground — both share the same event loop via `asyncio.create_task()` | Dashboard server already asyncio-based — needs clean startup from Textual `App.on_mount()` |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full raw log view inside Textual app | "I want to see everything the agents are doing" | Information overload is the #1 identified UX problem in v1.x. Raw ACP logs destroy the conversational feel and overwhelm the layout. | Layered model: TUI shows summarized activity per agent cell; web dashboard has full log access with filters and search. |
| Mouse-based text selection in transcript | "I want to copy text from agent responses" | Textual's mouse handling intercepts events; implementing cross-widget selection is complex and fragile. Terminal native selection works fine if TUI doesn't capture mouse on static content. | Disable mouse capture on completed (non-interactive) cells so the terminal's native selection works. |
| Inline file editor inside TUI | "Open the changed file in-place for review" | `TextArea` in Textual is a full editor widget — adding it inline creates accidental edits, focus traps, and layout complexity. | Show diff inline (already a differentiator). For editing, open `$EDITOR` via existing Ctrl+G binding or a `/edit` slash command. |
| Persistent split-screen layout (chat left, agents right) | "Always show agent panels alongside the conversation" | Fixed split wastes screen space when no agents are running; forces minimum terminal width (>100 cols) for readability. | Collapsible agent panels that appear only when agents are active and fold away when idle. |
| Real-time token cost counter in footer | "Show me what this session is costing" | Provider APIs report tokens inconsistently at streaming time; accurate billing-grade tracking requires post-turn reconciliation. Creates vendor coupling. | Display context utilization % (already tracked in `ContextTracker`) and turn count. Link to provider console for billing. |
| Custom syntax themes configurable per language | "I want different themes for Python vs shell output" | Per-language theme management creates a config system just for aesthetics. High implementation cost, low user value for a CLI tool. | Single theme per session. `/theme` command to switch globally. Rich/Pygments themes work uniformly across languages. |
| Drag-and-drop widget rearrangement | "Let me customize my layout" | Textual CSS-based layout doesn't support runtime rearrangement without full re-compose. Complex to implement, rarely used in practice. | Fixed but responsive layout. Terminal width determines panel arrangement via CSS `@media` queries. |

---

## Feature Dependencies

```
[Textual App shell]
    └──requires──> [Textual installed (textual >= 2.0)]
    └──enables──> [All Textual widgets below]

[Cell-based conversation transcript]
    └──requires──> [Textual App shell]
    └──requires──> [ChatHistoryStore] (already built — session replay on resume)
    └──enables──> [Streaming text into active cell]
    └──enables──> [Syntax-highlighted diffs in transcript]
    └──enables──> [Shimmer animation on in-progress cells]
    └──enables──> [Collapsible tool activity within cells]

[Streaming text into active cell]
    └──requires──> [Cell-based conversation transcript]
    └──requires──> [MarkdownStream or RichLog] (Textual built-in)
    └──requires──> [SDK streaming events] (already wired in _process_message())

[Modal approval overlays]
    └──requires──> [Textual App shell]
    └──requires──> [ModalScreen] (Textual built-in)
    └──requires──> [DelegationManager.escalation_input()] (already built — replace implementation)

[Status footer bar]
    └──requires──> [Textual App shell]
    └──requires──> [ContextTracker] (already built — provides token utilization data)
    └──enhances──> [Streaming text into active cell] (live token count during streaming)

[Slash command autocomplete popup]
    └──requires──> [Textual App shell]
    └──requires──> [textual-autocomplete library] OR [Input.suggester built-in]
    └──requires──> [SLASH_COMMANDS dict] (already built — becomes candidate list)

[Inline agent monitoring panels]
    └──requires──> [Textual App shell]
    └──requires──> [StatefulWatcher] (already built — state file events)
    └──requires──> [Collapsible widget] (Textual built-in)
    └──requires──> [RichLog widget] (Textual built-in)
    └──enhances──> [Cell-based conversation transcript] (agents visible alongside conversation)

[Web dashboard coexistence]
    └──requires──> [Textual App shell]
    └──requires──> [Dashboard asyncio server] (already built)
    └──conflicts──> [prompt_toolkit patch_stdout()] — removing prompt_toolkit resolves this conflict

[Syntax-highlighted diffs in transcript]
    └──requires──> [Cell-based conversation transcript]
    └──requires──> [RichLog.write(Syntax(...))] (Textual/Rich built-in)
    └──requires──> [Diff text extraction from ACP tool results] (new — parse tool output)
```

### Dependency Notes

- **Cell-based transcript is the foundational widget:** Everything visual in the TUI flows from this. Build it first, then add streaming, then tool activity, then diffs.
- **MarkdownStream vs RichLog:** `MarkdownStream` is ideal for rich markdown rendering (handles update coalescing). `RichLog` is better when you need to mix Rich renderables (Syntax objects, Tables) with text in the same widget. The transcript cell will likely need `RichLog` for its flexibility, with a `Markdown` sub-widget for the response text.
- **Modal approval replaces `_escalation_input()`:** The existing `prompt_toolkit`-based escalation input method needs to be replaced with a Textual `ModalScreen`. The `DelegationManager` interface stays the same — only the UI surface changes.
- **`textual-autocomplete` vs built-in `suggester`:** The built-in `Input.suggester` shows inline ghost text (single suggestion at cursor), not a popup list. For slash commands where users want to browse options, `textual-autocomplete` dropdown is the right choice. Both can coexist: ghost text for command completion, dropdown popup when `/` is typed.
- **Removing prompt_toolkit resolves stdout conflict:** Current TUI uses `patch_stdout()` to let Rich print during prompt_toolkit input — a known fragile hack. Textual manages all I/O itself, eliminating this problem entirely.

---

## MVP Definition

### Launch With (v2.0 core)

Minimum set to prove the Textual redesign is better than the current implementation.

- [ ] **Textual app shell** — replaces `prompt_toolkit.PromptSession`; all existing slash commands continue to work
- [ ] **Cell-based transcript** — scrollable, distinct user/assistant cells, markdown rendering in assistant cells
- [ ] **Streaming into active cell** — token-by-token text arrives; cell expands; auto-scroll to bottom
- [ ] **Visual "thinking" indicator** — spinner/pulse before first token; transitions to content when streaming starts
- [ ] **Status footer** — model name, current mode (`--auto` vs interactive), context utilization %
- [ ] **Slash command autocomplete popup** — `/` triggers dropdown; tab or enter selects; existing 5 commands populated
- [ ] **Modal approval overlays** — replace `_escalation_input()` escalation for agent file/command approvals
- [ ] **Web dashboard coexistence** — dashboard server starts in background alongside Textual app

### Add After Core Is Working (v2.0 polish)

Features to add once the core transcript and input are stable.

- [ ] **Syntax-highlighted code blocks** — native to `Markdown` widget; verify fenced code block rendering looks correct
- [ ] **Syntax-highlighted diffs** — extract diff text from ACP tool results; display via `RichLog.write(Syntax(...))`
- [ ] **Inline agent monitoring panels** — collapsible per-agent panels wired to `StatefulWatcher` events
- [ ] **Collapsible tool activity within cells** — tool calls in `Collapsible`; expanded during streaming, collapsed after
- [ ] **Shimmer animation on in-progress cells** — CSS animation on active cell border or loading indicator overlay

### Future Consideration (v2.x+)

- [ ] **`/theme` command with live preview** — swap Textual CSS variables at runtime; modal theme picker
- [ ] **Adaptive color scheme detection** — Textual `dark` property; CSS light/dark media queries
- [ ] **Session picker as Textual overlay** — current session list is a plain terminal UI; upgrade to `ModalScreen` with `ListView`

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Textual app shell | HIGH | MEDIUM | P1 |
| Cell-based transcript | HIGH | MEDIUM | P1 |
| Streaming into active cell | HIGH | MEDIUM | P1 |
| Visual "thinking" indicator | HIGH | LOW | P1 |
| Status footer | MEDIUM | MEDIUM | P1 |
| Slash command autocomplete popup | HIGH | MEDIUM | P1 |
| Modal approval overlays | HIGH | MEDIUM | P1 |
| Web dashboard coexistence | MEDIUM | MEDIUM | P1 |
| Syntax-highlighted code blocks | MEDIUM | LOW | P2 |
| Syntax-highlighted diffs | MEDIUM | MEDIUM | P2 |
| Inline agent monitoring panels | HIGH | HIGH | P2 |
| Collapsible tool activity within cells | MEDIUM | MEDIUM | P2 |
| Shimmer animation on in-progress cells | LOW | MEDIUM | P2 |
| `/theme` command with live preview | LOW | MEDIUM | P3 |
| Adaptive color scheme detection | LOW | LOW | P3 |
| Session picker as Textual overlay | LOW | LOW | P3 |

**Priority key:**
- P1: Required for v2.0 to be a credible replacement for the current TUI
- P2: Polish pass — makes v2.0 distinctly better than the current TUI
- P3: Defer to v2.x; worth doing but not blocking the redesign

---

## Codex CLI Reference Patterns Mapped to Textual

| Codex CLI UX Pattern | Textual Equivalent | Confidence | Notes |
|----------------------|--------------------|------------|-------|
| Cell-based transcript (discrete message blocks) | `VerticalScroll` + custom `Markdown`-subclass cells added via `mount()` | HIGH | Textual anatomy blog confirms this exact pattern; `on_input` appends cells |
| Shimmer animation on streaming cells | `LoadingIndicator` widget or CSS `animation` property on cell border | MEDIUM | Textual has `LoadingIndicator` (pulsating dots); true shimmer gradient requires custom CSS animation — achievable but undocumented in Textual |
| Modal approval overlay (grayed background) | `ModalScreen` with semi-transparent CSS background | HIGH | Built-in; `ModalScreen` automatically applies semi-transparent overlay on background |
| Slash command autocomplete popup | `textual-autocomplete` dropdown (fuzzy, arrow-key navigation) | HIGH | Library exists, Textual 2.0+ compatible, actively maintained |
| Syntax-highlighted diffs inline | `RichLog.write(Syntax(diff_text, "diff"))` | HIGH | `RichLog` accepts Rich `Syntax` objects directly; Rich supports "diff" as a Pygments lexer |
| Status footer (model, path, context) | Custom `Static` widget with `dock: bottom` CSS; reactive attributes for live updates | HIGH | Textual standard pattern; built-in `Footer` is keybindings-only so custom is needed |
| Agent monitoring sub-panels | `Collapsible` widget + `RichLog` inside; wired to state file events via `post_message()` | MEDIUM | Collapsible built-in; state file event wiring is new integration work |
| `/theme` live color swap | Textual `app.theme` property (if using named themes) or CSS variable reassignment | MEDIUM | Textual has basic theme support; runtime CSS variable swap is possible but less documented |

---

## Complexity Assessment Per Feature

| Feature | Complexity | Why |
|---------|------------|-----|
| Textual app shell (replace PromptSession) | MEDIUM | New framework setup; porting all slash commands; async integration with existing SDK client |
| Cell-based transcript widget | MEDIUM | Custom widget composition; scroll anchoring; session replay on resume needs cell reconstruction |
| Streaming text (MarkdownStream/RichLog) | MEDIUM | Coalescing rapid updates; transitions between loading/complete cell state; async producer-consumer |
| Status footer (custom Static widget) | MEDIUM | Custom widget; reactive state wiring to `ContextTracker`; CSS docking |
| Slash command autocomplete | MEDIUM | `textual-autocomplete` integration; trigger on `/` specifically vs any input |
| Modal approval overlays | MEDIUM | `ModalScreen` is straightforward; wiring `dismiss()` back to `DelegationManager.input_fn` callback |
| Web dashboard coexistence | MEDIUM | Starting the asyncio HTTP/WebSocket server from inside Textual's event loop (`on_mount`); port conflict handling |
| Syntax-highlighted code blocks | LOW | Native to `Markdown` widget; verify rendering is correct |
| Syntax-highlighted diffs | MEDIUM | Requires extracting diff text from ACP tool results; `RichLog.write(Syntax(...))` call is simple |
| Inline agent monitoring panels | HIGH | State file watcher events → Textual message bus → per-agent panel widget updates; panel lifecycle (create/destroy as agents start/finish) |
| Collapsible tool activity | MEDIUM | Wrapping `format_tool_activity()` output in `Collapsible`; state transition from expanded to collapsed on turn completion |
| Shimmer animation | MEDIUM | `LoadingIndicator` is low complexity; true shimmer gradient requires custom CSS animation knowledge |

---

## Competitor Feature Analysis

| Feature | Codex CLI | Claude Code CLI | OpenCode | Conductor v2.0 (planned) |
|---------|-----------|----------------|----------|---------------------------|
| Cell-based transcript | Yes (Ratatui cells) | No (inline streaming to terminal) | Yes | Yes (Textual cells) |
| Streaming into cells | Yes | Yes (inline) | Yes | Yes |
| Modal approval overlay | Yes (inline in cell flow) | Yes (interactive permission prompts) | Yes | Yes (`ModalScreen`) |
| Slash command autocomplete | Yes (/theme, /review, /clear, /model, /permissions) | Yes (extensive) | Yes | Yes (existing 5 + /theme) |
| Syntax-highlighted code | Yes (markdown code fences) | Yes | Yes | Yes (Markdown widget) |
| Syntax-highlighted diffs | Yes (/theme-able) | Partial | Partial | Yes (RichLog + Rich Syntax) |
| Status bar/footer | Yes (header: working path) | No visible status bar | Yes | Yes (custom footer widget) |
| Agent monitoring panels | No | No | No | Yes (differentiator) |
| Web dashboard coexistence | No | No | No | Yes (differentiator) |
| Shimmer animation | Yes | No | Partial | Yes (LoadingIndicator / CSS) |
| Live theme switching | Yes (/theme) | No | No | Deferred (v2.x) |

---

## Sources

- [Textual widget gallery — Official Docs](https://textual.textualize.io/widget_gallery/) — HIGH confidence, official Textualize documentation
- [Textual Markdown widget — Official Docs](https://textual.textualize.io/widgets/markdown/) — HIGH confidence; confirms MarkdownStream for coalesced streaming updates
- [Textual RichLog widget — Official Docs](https://textual.textualize.io/widgets/rich_log/) — HIGH confidence; confirms Rich Syntax objects accepted as renderables
- [Textual Screens guide (ModalScreen) — Official Docs](https://textual.textualize.io/guide/screens/) — HIGH confidence; confirms push/pop/dismiss pattern with callback
- [Textual Footer widget — Official Docs](https://textual.textualize.io/widgets/footer/) — HIGH confidence; confirms Footer is keybinding-only → custom static widget needed
- [Textual LoadingIndicator — Official Docs](https://textual.textualize.io/widgets/loading_indicator/) — HIGH confidence; pulsating dots; `widget.loading` property for inline replacement
- [Textual content/markup guide — Official Docs](https://textual.textualize.io/guide/content/) — HIGH confidence; Rich renderables supported alongside Textual markup
- [textual-autocomplete — GitHub (darrenburns)](https://github.com/darrenburns/textual-autocomplete) — HIGH confidence; fuzzy dropdown, Textual 2.0+ compatible, actively maintained
- [Anatomy of a Textual User Interface — Textual Blog](https://textual.textualize.io/blog/2024/09/15/anatomy-of-a-textual-user-interface/) — HIGH confidence; official blog showing exact cell-based chat pattern with VerticalScroll + Markdown cells
- [Codex CLI features — OpenAI Official Docs](https://developers.openai.com/codex/cli/features/) — HIGH confidence; confirms syntax-highlighted diffs, /theme, approval workflows
- [Codex CLI changelog — OpenAI](https://developers.openai.com/codex/changelog/) — HIGH confidence; multi-agent sub-agent monitoring features added 2025
- Existing Conductor source: `packages/conductor-core/src/conductor/cli/chat.py` — HIGH confidence; direct code review of features being replaced

---
*Feature research for: Textual TUI redesign (Conductor v2.0)*
*Researched: 2026-03-11*
