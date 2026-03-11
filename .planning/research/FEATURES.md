# Feature Research

**Domain:** Interactive conversational coding TUI (chat-mode coding agent)
**Researched:** 2026-03-11
**Confidence:** HIGH (primary sources: Claude Code official docs, Aider docs, OpenCode TUI docs, Codex CLI docs, practitioner post-mortems)

---

## Context: This Is a Subsequent Milestone

This research focuses exclusively on **what's needed for v1.1's interactive chat TUI**. The v1.0 multi-agent orchestration features (orchestrator, ACP, state file, sub-agents, web dashboard, escalation, session persistence) are already built and out of scope here.

The new surface: `conductor` (no args) launches an interactive REPL where the user chats with the orchestrator, which can handle tasks directly or delegate to sub-agent teams.

Existing infrastructure the new TUI layer sits on top of:
- ACP client/server runtime (orchestrator communication)
- Shared `.conductor/state.json` (coordination backbone)
- Shared `.memory/` folder (persistent knowledge)
- `conductor run "task"` batch mode (non-interactive reference implementation)
- CLI intervention commands (cancel, redirect, feedback — v1.0)
- Web dashboard with real-time WebSocket updates (v1.0)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist when they run a `conductor` command. Missing these = product feels like a prototype.

| Feature | Why Expected | Complexity | Existing Dependency |
|---------|--------------|------------|---------------------|
| REPL input loop | The entire premise — persistent interactive session, not one-shot | LOW | None — new |
| Streaming response output | Every modern coding agent streams; waiting for full response feels broken | MEDIUM | ACP streaming exists; wire into display |
| Ctrl+C to interrupt running agent | Claude Code, Codex, Aider all support this; users muscle-memory it | MEDIUM | v1.0 cancel/redirect exists; needs signal handler in REPL |
| Graceful Ctrl+C semantics (stop agent, don't quit TUI) | Codex uses double-Ctrl+C pattern; first press stops agent, second exits; single press should not kill session | MEDIUM | None — new |
| Input history (arrow keys) | Shell muscle memory — up/down arrows to recall prior prompts | LOW | prompt_toolkit supports this natively |
| Multiline input | Code snippets, file paths with context, complex task descriptions need wrapping | LOW | prompt_toolkit supports this natively |
| Display tool use as it happens | Users expect to see what the agent is doing (file reads, edits, shell commands) — Claude Code does this | MEDIUM | ACP tool call events exist; needs display layer |
| Conversation context persistence across turns | Agent must remember what was said earlier in session; not stateless per message | MEDIUM | `.memory/` and ACP session exist; wire into chat loop |
| Session resumption | Close and re-open TUI; pick up where you left off. Claude Code, Codex, OpenCode all do this | MEDIUM | State file + memory exist; needs session ID tracking |
| Clear "thinking/working" indicator | User must know agent is running, not frozen. Spinner or live activity | LOW | Rich Live already used in v1.0 batch mode |
| `/help` command | Users expect a discoverable help system | LOW | None — new |
| `/exit` or `quit` command | Clean way to exit without killing terminal | LOW | None — new |

### Differentiators (Competitive Advantage)

Features that make Conductor's chat TUI meaningfully better than typing `claude` or `aider`.

| Feature | Value Proposition | Complexity | Existing Dependency |
|---------|-------------------|------------|---------------------|
| Smart delegation — direct vs spawn | Orchestrator judges: simple file edit = handle directly; "build auth module" = spawn sub-agent team. No other TUI has this | HIGH | Orchestrator intelligence (v1.0); direct tool use is new |
| Transparent delegation announcement | When spawning sub-agents, TUI says "Spinning up a team for this..." and links to web dashboard for visibility | LOW | Web dashboard (v1.0); state file (v1.0) |
| Orchestrator direct tool use (file read/edit/shell) | Orchestrator can do quick tasks without spawning agents. Reduces latency and cost for simple work | HIGH | Orchestrator currently orchestration-only; needs tool access in chat mode |
| Live sub-agent activity feed in TUI | While sub-agents work, TUI shows brief status lines (not full logs) — you see progress without noise | MEDIUM | State file watch (v1.0); needs TUI display component |
| `/status` command shows agent team | Quick view of what agents are doing right now, directly in TUI | LOW | State file (v1.0); new display command |
| Escalation from sub-agents surfaces in TUI | When a sub-agent escalates, the TUI interrupts with a question rather than silently stalling | MEDIUM | Escalation logic (v1.0); needs interrupt-to-chat-loop bridge |
| Per-task GSD scope flexibility announced | TUI shows whether orchestrator is planning full phases vs executing directly — user sees the decision | LOW | Per-task GSD scope (v1.1 target); display layer only |
| Quality review loop visible in TUI | "Reviewing sub-agent output..." status line; user sees orchestrator is actually checking work | LOW | Review loop (v1.1 target); display layer only |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full-screen TUI (curses-style) | "Looks professional" | Loses terminal scrollback buffer — must re-implement custom scrolling and search. Mouse scrolling feels off. Adds ~500+ lines of layout code for zero functional gain. (Source: practitioner post-mortem) | Inline streaming output using Rich. Users already have a terminal with scrollback. |
| Syntax-highlighted inline diffs in TUI | "Show me the file changes" | Diffs can be large; inline display bloats conversation; hard to review in terminal | Show brief change summary in TUI ("Edited auth.py: +12 -3 lines"); detailed review in web dashboard or git |
| Real-time token/cost tracking per message | "I want to see what I'm spending" | Provider APIs report tokens inconsistently; accurate billing-grade tracking is non-trivial; creates vendor coupling | Display turn count and session duration instead. Link to provider console for billing. |
| Voice input | "Hands-free coding" | Substantial platform-specific complexity (mic access, transcription). Aider has it; rarely used feature. Scope explosion for niche use case | Text only for v1.1. Not a requested feature in PROJECT.md. |
| Built-in to-do / plan display inside chat | "Show me the plan before executing" | Confuses models more than helps. Plan state in chat history creates redundant context. (Source: minimal agent post-mortem) | Orchestrator writes plans to `.conductor/` files if needed; state file tracks task status |
| MCP server integration in TUI | "Plug in external tools" | MCP context overhead is 7-9% of context window per server. Adds integration complexity for unclear benefit in chat mode. | Orchestrator inherits project's MCP config from `.claude/` naturally; no new TUI surface needed |
| Multiple concurrent chat sessions | "Run two things at once" | Session state conflicts with single shared `.conductor/state.json`. Requires session namespacing across all v1.0 infrastructure. v2 feature. | One TUI session at a time. Use `conductor run` for fire-and-forget batch tasks in parallel. |
| Raw log streaming as primary chat view | "I want to see everything" | Information overload is the #1 identified UX problem. Raw ACP logs destroy the conversational feel. | Layered: TUI shows summarized activity; web dashboard has full log access. |

---

## Feature Dependencies

```
[Interactive REPL loop]
    └──requires──> [Streaming response display]
    └──requires──> [Input history (prompt_toolkit)]
    └──requires──> [Ctrl+C interrupt handler]
    └──requires──> [Session ID tracking]

[Session resumption]
    └──requires──> [Session ID tracking]
    └──requires──> [State file (.conductor/state.json)] (already built)
    └──requires──> [.memory/ folder] (already built)

[Streaming response display]
    └──requires──> [ACP streaming] (already built)
    └──requires──> [Rich Live display] (already used in v1.0 batch mode)

[Ctrl+C interrupt handler]
    └──requires──> [REPL loop] (signal handler in input loop)
    └──requires──> [Cancel/redirect logic] (already built v1.0)

[Orchestrator direct tool use]
    └──requires──> [REPL loop] (chat mode activates tool access)
    └──requires──> [Smart delegation logic]

[Smart delegation (direct vs spawn)]
    └──requires──> [Orchestrator direct tool use] (option A of decision)
    └──requires──> [Sub-agent spawning] (already built v1.0, option B)
    └──requires──> [Orchestrator intelligence] (already built v1.0, decides which)

[Live sub-agent activity feed in TUI]
    └──requires──> [State file watch] (already built v1.0)
    └──requires──> [REPL loop] (needs non-blocking display component)

[Escalation surfaces in TUI]
    └──requires──> [Escalation logic] (already built v1.0)
    └──requires──> [REPL loop] (async interrupt into input prompt)

[/status command]
    └──requires──> [State file] (already built v1.0)
    └──requires──> [Slash command parser] (new)
```

### Dependency Notes

- **Orchestrator direct tool use requires smart delegation:** Direct tool use only makes sense in the context of the orchestrator deciding whether to handle a task itself or spawn agents. These are co-developed.
- **Ctrl+C semantics require careful design:** First Ctrl+C should interrupt the running agent (cancel signal, already in v1.0) but keep the TUI session alive. Second Ctrl+C (or `/exit`) closes the TUI. Mixing these signals is a known bug in Claude Code (reported GitHub issue #3455).
- **Streaming display requires non-blocking output:** The input prompt and streaming output must coexist. `prompt_toolkit` provides `patch_stdout` for this. Full-screen TUI is not needed.
- **Session resumption is additive:** The state file and memory already persist. What's new is tracking a session_id in the TUI and loading the right context on startup.

---

## MVP Definition

### Launch With (v1.1)

Minimum set to make the interactive TUI actually useful.

- [ ] REPL input loop with `prompt_toolkit` — without this nothing works
- [ ] Streaming response display with activity indicator — without this agent feels frozen
- [ ] Ctrl+C interrupt (stop agent, not quit TUI) — without this users will kill the process
- [ ] Input history (arrow keys) — without this input is painful for anything longer than one turn
- [ ] Orchestrator direct tool use (read/edit files, run shell) — core new capability for v1.1
- [ ] Smart delegation (direct vs spawn) with transparency — core new behavior for v1.1
- [ ] Slash commands: `/help`, `/exit`, `/status` — minimum discoverability
- [ ] Session resumption — without this every `conductor` invocation starts cold

### Add After Validation (v1.x)

Features to add once the core chat loop is working.

- [ ] Live sub-agent activity feed in TUI — add when smart delegation is working; depends on state file watch stability
- [ ] Escalation interrupt surfaces in TUI — add when base TUI is stable; requires async interrupt handling
- [ ] Per-task GSD scope flexibility display — add when orchestrator judgment for scope is tuned
- [ ] Quality review loop status in TUI — add when review loops are implemented

### Future Consideration (v2+)

- [ ] Multi-session support — defer; requires session namespacing across all shared state
- [ ] Voice input — defer; niche use case, high platform complexity
- [ ] Inline diff review in TUI — defer; evaluate demand after v1.1 ships; web dashboard covers this

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| REPL input loop | HIGH | LOW | P1 |
| Streaming display + activity indicator | HIGH | LOW | P1 |
| Ctrl+C interrupt semantics | HIGH | MEDIUM | P1 |
| Input history | HIGH | LOW | P1 |
| Orchestrator direct tool use | HIGH | HIGH | P1 |
| Smart delegation (direct vs spawn) | HIGH | HIGH | P1 |
| `/help`, `/exit`, `/status` slash commands | HIGH | LOW | P1 |
| Session resumption | MEDIUM | MEDIUM | P1 |
| Live sub-agent activity feed in TUI | MEDIUM | MEDIUM | P2 |
| Escalation interrupt in TUI | MEDIUM | MEDIUM | P2 |
| Per-task GSD scope display | LOW | LOW | P2 |
| Quality review loop status display | LOW | LOW | P2 |
| Multi-session support | LOW | HIGH | P3 |
| Voice input | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v1.1 launch
- P2: Add when P1 is stable; same milestone if time permits
- P3: Defer to v2+

---

## Competitor Feature Analysis

| Feature | Claude Code CLI | Codex CLI | Aider | OpenCode | Conductor v1.1 (planned) |
|---------|----------------|-----------|-------|----------|--------------------------|
| REPL loop | Yes (core UX) | Yes (core UX) | Yes | Yes | Yes |
| Streaming output | Yes | Yes (PTY/streaming) | Yes | Yes | Yes |
| Ctrl+C semantics | Buggy (issue #3455 — agent continues) | Fixed (double-Ctrl+C pattern) | Works | Works | Stop agent, keep TUI alive |
| Input history | Yes | Yes (Up/Down draft history) | Yes | Yes | Yes (prompt_toolkit) |
| Slash commands | Yes (extensive: /clear, /compact, /review, etc.) | Yes (/exit, /fork, /review) | Yes (/add, /undo, /model, /mode) | Yes (/thinking, /undo, /redo) | /help, /exit, /status (MVP set) |
| Direct tool use (file/shell) | Yes | Yes | Yes | Yes | Yes — new for v1.1 |
| Session resumption | Yes | Yes (resume subcommand) | Partial (via git history) | Yes (session list/resume) | Yes — v1.1 |
| Sub-agent delegation | Yes (spawn sub-agents) | No | No | No | Yes (+ smart delegation decision) |
| Chat modes | No (single mode) | No | Yes (code/architect/ask) | No | No (single mode; delegation is implicit) |
| Undo/redo changes | No (use git) | No (use git) | Yes (/undo via git) | Yes (file + git restore) | No (use git — same approach) |
| Activity feed while agent runs | Partial (tool calls inline) | Partial | No | No | Yes — live sub-agent status |
| Multi-agent visibility | No | No | No | No | Yes (via web dashboard link) |

---

## Sources

- [Claude Code overview — Official Docs](https://code.claude.com/docs/en/overview) — HIGH confidence, official Anthropic documentation
- [Codex CLI features — OpenAI Docs](https://developers.openai.com/codex/cli/features/) — HIGH confidence, official OpenAI documentation
- [Aider usage — Official Docs](https://aider.chat/docs/usage.html) — HIGH confidence, official Aider documentation
- [OpenCode TUI — Official Docs](https://opencode.ai/docs/tui/) — HIGH confidence, official OpenCode documentation
- [What I learned building an opinionated and minimal coding agent — mariozechner.at](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/) — HIGH confidence, detailed practitioner post-mortem
- [Building AI Coding Agents for the Terminal — arXiv 2603.05344](https://arxiv.org/html/2603.05344v1) — HIGH confidence, peer-reviewed engineering paper
- [Interrupt signals don't stop agent — Claude Code GitHub issue #3455](https://github.com/anthropics/claude-code/issues/3455) — HIGH confidence, official issue tracker
- [Double Ctrl+C to quit — OpenCode GitHub issue #9041](https://github.com/anomalyco/opencode/issues/9041) — MEDIUM confidence, community issue discussion
- [Claude Code vs Codex CLI vs Gemini CLI comparison — codeant.ai 2025](https://www.codeant.ai/blogs/claude-code-cli-vs-codex-cli-vs-gemini-cli-best-ai-cli-tool-for-developers-in-2025) — MEDIUM confidence, comparative analysis

---
*Feature research for: interactive chat TUI (Conductor v1.1)*
*Researched: 2026-03-11*
