# Project Research Summary

**Project:** Conductor v1.1 — Interactive Chat TUI
**Domain:** Interactive conversational coding agent TUI added to existing multi-agent orchestration CLI
**Researched:** 2026-03-11
**Confidence:** HIGH

## Executive Summary

Conductor v1.1 adds an interactive chat REPL on top of a fully operational v1.0 multi-agent orchestration foundation. The core problem being solved is giving users a persistent conversational entry point (`conductor` with no args) rather than forcing every task through the fire-and-forget `conductor run "task"` batch mode. The recommended approach closely mirrors how Claude Code, Codex CLI, and Aider are built: a persistent SDK session (`ClaudeSDKClient`) with streaming token output, `prompt_toolkit` for input handling, and an explicit delegation boundary that distinguishes between tasks the orchestrator handles directly (file read/edit/shell in-context) versus tasks it escalates to sub-agent teams. Only one new runtime dependency is required — `prompt-toolkit>=3.0.52` — because `ClaudeSDKClient`, `include_partial_messages`, `rich.markdown`, and `rich.syntax` are already present in the existing stack.

The recommended architecture adds three new modules under `cli/` (`chat.py`, `chat_persistence.py`, `commands/chat.py`) and one small modification to `cli/__init__.py`. All v1.0 components — the orchestrator, ACP client, state manager, session registry, and dashboard — are used unchanged. The delegation pattern is clean: the orchestrator's chat session defines a `Delegate` custom in-process tool; when Claude calls it, a `PostToolUse` hook runs `Orchestrator.run()` with a fresh instance and returns a summary as the tool result. This separates the LLM's decision about when to delegate from the Python code that executes the delegation.

The highest-risk area is the input/display layer, not the business logic. Three pitfalls can corrupt or hang the terminal before a single chat turn completes: mixing `Rich.Live` concurrent refresh with streaming output, using `asyncio.to_thread(input)` for a persistent session (uncancellable thread), and failing to restore terminal raw mode on crash or exception. These must be addressed in Phase 1 before any feature work begins. Context window exhaustion from unbounded chat history is the second major risk and must be addressed in Phase 2 before the system is usable beyond 20-30 turns.

## Key Findings

### Recommended Stack

The existing v1.0 stack (claude-agent-sdk, rich, typer, asyncio, pydantic, fastapi, watchfiles) requires only one addition: `prompt-toolkit>=3.0.52`. This library provides `PromptSession.prompt_async()` for cancellable async input, `patch_stdout()` to serialize concurrent Rich output safely alongside the active input prompt, and `FileHistory` for persistent arrow-key recall across restarts. Replacing `asyncio.to_thread(input)` with `PromptSession.prompt_async()` is the single most important foundation decision; the existing `_ainput()` in `input_loop.py` must remain unchanged (batch mode still uses it), and the new chat loop is built in a separate module.

**Core technologies:**
- `ClaudeSDKClient` (already in claude-agent-sdk 0.1.48): persistent multi-turn session for the orchestrator — the correct API for chat/REPL, not `query()` which closes and reopens the session per call
- `include_partial_messages=True` (ClaudeAgentOptions field, no new dep): token-by-token streaming output; without this users see nothing until Claude finishes the entire response
- `prompt_toolkit 3.0.52` (only new dep): cancellable async input with history, multiline support, and `patch_stdout()` for concurrent-output-safe prompt rendering
- `rich.markdown.Markdown` + `rich.syntax.Syntax` (already in rich>=13): render assistant text responses with proper headings, code fences, and syntax highlighting
- `Delegate` custom in-process tool (new, no dep): signals the orchestrator SDK session when to spawn sub-agents; intercepted by a `PostToolUse` hook that calls `Orchestrator.run()`

### Expected Features

**Must have (table stakes for v1.1):**
- REPL input loop with `prompt_toolkit` — the entire premise; nothing works without this
- Streaming response output with activity indicator — waiting for full response feels broken
- Ctrl+C to interrupt running agent (stop agent, not quit TUI) — users muscle-memory this
- Input history (arrow keys via `FileHistory("~/.conductor_history")`) — standard shell expectation
- Orchestrator direct tool use (read/edit files, run shell) — the new capability in v1.1
- Smart delegation (direct vs. spawn sub-agents) with visible announcement — the key differentiator
- Slash commands: `/help`, `/exit`, `/status` — minimum discoverability
- Session resumption via `resume=session_id` — every restart should pick up prior context

**Should have (competitive, add when P1 is stable):**
- Live sub-agent activity feed in TUI during delegation — progress visibility
- Escalation interrupt from sub-agents surfacing in TUI — requires async interrupt bridge
- Per-task GSD scope display — low effort, depends on orchestrator judgment being tuned
- Quality review loop status line — display only, depends on review loop implementation

**Defer (v2+):**
- Multi-session support — requires session namespacing across all shared state
- Voice input — niche use case, high platform complexity
- Inline diff review in TUI — web dashboard already covers this

### Architecture Approach

Three new files under `cli/` implement the entire chat TUI. `cli/chat.py` contains `ChatSession` (the async REPL, streaming renderer, and `PostToolUse` delegation hook). `cli/chat_persistence.py` handles reading and writing `.conductor/chat_session.json` for session resumption. `cli/commands/chat.py` wires the Typer command. The single modification to `cli/__init__.py` switches from `no_args_is_help=True` to `invoke_without_command=True` with a callback that routes no-args invocation to chat mode. Every other module in the codebase is unchanged.

**Major components:**
1. `cli/chat.py` (`ChatSession`) — owns the async REPL loop, `ClaudeSDKClient` lifetime, streaming output rendering, and the `PostToolUse` hook that calls `Orchestrator.run()` for delegation
2. `cli/chat_persistence.py` — reads/writes `.conductor/chat_session.json`; mirrors the existing `SessionRegistry` pattern; enables `resume=session_id` on startup
3. `Delegate` custom tool + `PostToolUse` hook — the delegation bridge; Claude calls the tool when it decides to spawn agents; the hook executes a fresh `Orchestrator` instance and returns a text summary as the tool result
4. Chat system prompt — defines the orchestrator's identity in chat mode (direct-tool engineer vs. batch decomposer), delegation heuristics, and structured "decisions made" section; requires iterative tuning

### Critical Pitfalls

1. **Rich Live + streaming terminal corruption** — Do not run `Rich.Live` concurrent with streaming token output in chat mode. Drop the `_display_loop`/Live layer entirely in chat mode; route all output through `prompt_toolkit`'s `patch_stdout()`. Establish this in Phase 1 before any streaming work.

2. **`asyncio.to_thread(input)` is uncancellable** — Never use `asyncio.to_thread(input)` for the chat input loop. The thread cannot be cancelled from Python (CPython #107505); on Ctrl+C the process hangs until Enter is pressed. Replace with `PromptSession.prompt_async()` as the first implementation step.

3. **Terminal raw mode left dirty on crash** — Wrap the entire chat session entry point in `try/finally` catching `BaseException` (not just `Exception`) to restore terminal state. Test explicitly by force-crashing mid-prompt and verifying `stty -a` shows `echo` on.

4. **Chat history grows unbounded, silently exhausting context** — Track approximate token count client-side after each turn. Warn at 60% utilization; offer session summarization at 75%. Store full history to `.conductor/chat_history.json` separately from what is sent to the API. Must be designed in Phase 2 before any real usage.

5. **Smart delegation is non-deterministic and leaks Orchestrator state** — Define an explicit rule-based delegation policy for the system prompt. Always construct a fresh `Orchestrator` instance per delegation call (never reuse; `__init__` initializes mutable `_active_clients` and `_active_tasks`). Use separate state namespaces for chat-triggered tasks vs. batch tasks.

## Implications for Roadmap

Based on research, the build order follows a clear dependency chain: fix the CLI entry point and input layer first (nothing else is testable until `conductor` with no args reaches the chat loop), then implement the streaming display and session lifecycle (prerequisites for any real interaction), then add the delegation logic (requires the REPL and display to already work), then tune the orchestrator's intelligence.

### Phase 1: CLI Foundation and Input Layer

**Rationale:** Three pitfalls (Rich Live corruption, uncancellable input, terminal dirty state, Typer no-args conflict) all share the same root cause — the input/display infrastructure — and must be solved together before any feature work. Nothing else is testable until `conductor` alone reaches the chat loop and accepts input cleanly.

**Delivers:** `conductor` (no args) enters an interactive REPL with safe input handling, clean terminal lifecycle, and proof that streaming output and the input prompt can coexist without corruption.

**Addresses:** REPL input loop (table stakes), Ctrl+C interrupt semantics, input history, slash commands MVP (`/help`, `/exit`)

**Avoids:** Pitfalls 1 (Rich Live corruption), 2 (uncancellable input), 5 (terminal dirty state), 7 (Typer no-args conflict)

**Files:** `cli/__init__.py` (modify), `cli/chat.py` (skeleton with `PromptSession`), `cli/commands/chat.py` (new), `cli/chat_persistence.py` (new skeleton)

**Research flag:** Standard patterns — `prompt_toolkit` integration is fully documented with official examples. HIGH confidence. No additional research needed.

### Phase 2: Streaming Display and Session Lifecycle

**Rationale:** Streaming output and session persistence are co-dependent: streaming requires correct handling of all SDK message types (including `ToolUseBlock`), and session persistence requires capturing `session_id` from the `SystemMessage(subtype="init")` that fires on the first streaming turn. Context management must also be addressed here because it silently degrades quality after 20-30 turns.

**Delivers:** Real-time token streaming with human-readable tool activity indicators, session resumption across restarts, and client-side context utilization tracking with user warning.

**Addresses:** Streaming response display, session resumption, clear working indicator, tool use display in chat

**Avoids:** Pitfalls 3 (context exhaustion), 6 (streaming blocks event loop), 9 (tool call JSON in chat display)

**Uses:** `include_partial_messages=True`, `ClaudeSDKClient`, `chat_persistence.py`, `rich.markdown.Markdown`

**Research flag:** The distinction between text stream events, tool use events, and result events requires deliberate mapping to UX states. Reference `ARCHITECTURE.md` data flow diagrams for all four flow types. SDK streaming docs are HIGH confidence but the display mapping requires careful design.

### Phase 3: Smart Delegation and Orchestrator Integration

**Rationale:** Delegation depends on the chat loop and streaming display both being stable (Phases 1 and 2). A fresh `Orchestrator` must be instantiated per delegation call. The `Delegate` custom tool and `PostToolUse` hook must be registered before the SDK session starts. The delegation system prompt heuristics require iterative tuning that can only happen once the basic dispatch works.

**Delivers:** Orchestrator direct tool use for simple tasks, sub-agent spawning for complex tasks via the `Delegate` tool, transparent delegation announcement ("Spinning up a team for this..."), and `/status` slash command.

**Addresses:** Smart delegation (direct vs. spawn), orchestrator direct tool use, transparent delegation announcement

**Avoids:** Pitfalls 4 (non-deterministic delegation, Orchestrator state leakage), 8 (chat/batch state isolation)

**Files:** `cli/chat.py` (add `Delegate` tool schema, `_delegation_hook`, `_spawn_agents`), chat system prompt (new constant)

**Research flag:** Delegation heuristic tuning is empirical — requires testing against representative inputs. Plan a prompt-tuning sub-phase after basic dispatch works. The system prompt rules for "handle directly vs. delegate" cannot be resolved through research alone.

### Phase 4: Enhanced TUI Feedback and Escalation Bridge

**Rationale:** These features depend on Phase 3 delegation working. Live sub-agent activity feed requires state file watching (already in v1.0) integrated with a non-blocking TUI display. Escalation surfacing requires the `human_out`/`human_in` asyncio queues to be wired through the delegation hook, which requires Phase 3 to be complete.

**Delivers:** Live sub-agent activity status lines during delegation, escalation questions from sub-agents surfacing interactively in the TUI, per-task GSD scope display.

**Addresses:** Live sub-agent activity feed, escalation interrupt in TUI, UX turn separators and progress clarity

**Avoids:** UX pitfalls (no distinction between thinking/delegating, no turn separators, escalation interrupting streaming response)

**Research flag:** Standard patterns — async queue integration is well-documented. No additional research needed.

### Phase Ordering Rationale

- Phase 1 is non-negotiable first: the Typer entry conflict and input mechanism are blocking issues; nothing is end-to-end testable without resolving them.
- Phase 2 before Phase 3: streaming and session persistence must be in place before delegation because delegation involves streaming sub-results back through the same rendering path.
- Phase 3 before Phase 4: live activity feed and escalation bridge both require the delegation hook infrastructure to be operational.
- Context management (Pitfall 3) belongs in Phase 2, not Phase 4 — it is a session lifecycle concern that will silently cause failures at 20-30 turns even in basic usage.

### Research Flags

Phases likely needing closer attention during implementation:
- **Phase 2 (streaming display):** SDK stream event type handling (`TextChunk`, `ToolUseBlock`, `ToolResultBlock`, `ResultMessage`) needs deliberate mapping to UX states. Reference `ARCHITECTURE.md` data flow diagrams before implementing the renderer.
- **Phase 3 (delegation heuristics):** System prompt tuning is empirical. Plan a dedicated tuning sub-phase with representative test cases (single-file fix, multi-file feature, ambiguous request).

Phases with well-established patterns (minimal additional research needed):
- **Phase 1:** `prompt_toolkit` + Typer `invoke_without_command` integration is fully documented with official examples. HIGH confidence.
- **Phase 4:** Async queue bridging and state file watching already exist in v1.0 infrastructure; this is wiring, not novel design.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All recommendations from official Anthropic SDK docs, prompt_toolkit official docs, and PyPI release data. Only one new dependency. No conflicting sources found. |
| Features | HIGH | Cross-validated against Claude Code, Codex CLI, Aider, and OpenCode official docs plus practitioner post-mortems. Competitor feature matrix is complete. |
| Architecture | HIGH | Based on live codebase inspection and official SDK documentation. All integration boundaries (`ClaudeSDKClient`, `PostToolUse`, custom tools) are from confirmed API surfaces. |
| Pitfalls | HIGH | Derived from direct codebase analysis (existing `input_loop.py` limitations documented in code comments), official Rich/prompt_toolkit issue trackers, CPython issue tracker, and Claude Agent SDK streaming docs. |

**Overall confidence:** HIGH

### Gaps to Address

- **Delegation system prompt heuristics:** The exact rules for "handle directly vs. delegate" are not resolvable through research alone — they require empirical tuning against representative inputs. Plan time in Phase 3 for a prompt-engineering sub-phase.
- **Context window utilization tracking:** The SDK does not surface a token count to the caller by default. Client-side approximation (character count / 4 as token estimate) is the recommended approach, but the accuracy threshold for triggering warnings should be validated in Phase 2.
- **State isolation schema for chat-triggered delegation:** `ARCHITECTURE.md` recommends session-scoped task ID prefixes (`chat-[session-id]-task-001`). The exact schema extension to `ConductorState` for chat metadata needs to be decided before Phase 3 writes any state. Flag for requirements definition.

## Sources

### Primary (HIGH confidence)
- [Claude Agent SDK Python reference](https://platform.claude.com/docs/en/agent-sdk/python) — `ClaudeSDKClient` vs `query()` comparison, session continuity, chat/REPL use case confirmation
- [Claude Agent SDK streaming docs](https://platform.claude.com/docs/en/agent-sdk/streaming-output) — `include_partial_messages`, `StreamEvent`, `text_delta` pattern
- [Claude Agent SDK agent loop docs](https://platform.claude.com/docs/en/agent-sdk/agent-loop) — `PostToolUse` hooks, message types, custom tools
- [prompt_toolkit official docs](https://python-prompt-toolkit.readthedocs.io/en/stable/) — `PromptSession`, `prompt_async()`, `patch_stdout()`, `FileHistory`, asyncio integration
- [PyPI: claude-agent-sdk 0.1.48](https://pypi.org/project/claude-agent-sdk/) — confirmed current release, 2026-03-07
- [PyPI: prompt-toolkit 3.0.52](https://pypi.org/project/prompt-toolkit/) — confirmed current release, 2025-08-27
- [Claude Code official docs](https://code.claude.com/docs/en/overview) — feature baseline comparison
- [Codex CLI docs](https://developers.openai.com/codex/cli/features/) — Ctrl+C double-press pattern, input history
- [Aider docs](https://aider.chat/docs/usage.html) — slash commands, session patterns
- [OpenCode TUI docs](https://opencode.ai/docs/tui/) — session resume patterns
- Rich official docs + issue tracker (#1530, discussion #1791) — Live display + concurrent input limitations confirmed
- prompt_toolkit issue #787 — terminal cleanup on async cancellation confirmed
- CPython issue #107505 — `asyncio.to_thread` non-cancellability confirmed
- Live codebase inspection: `conductor-core/src/conductor/` (2026-03-11)

### Secondary (MEDIUM confidence)
- [Claude Code vs Codex CLI vs Gemini CLI — codeant.ai](https://www.codeant.ai/blogs/claude-code-cli-vs-codex-cli-vs-gemini-cli-best-ai-cli-tool-for-developers-in-2025) — feature matrix cross-check
- [Context window management strategies — getmaxim.ai](https://www.getmaxim.ai/articles/context-window-management-strategies-for-long-context-ai-agents-and-chatbots/) — aligns with Anthropic official guidance on context management
- [Claude Code GitHub issue #3455](https://github.com/anthropics/claude-code/issues/3455) — Ctrl+C interrupt bug, confirmed limitation to avoid replicating

### Tertiary
- [Building AI Coding Agents for the Terminal — arXiv 2603.05344](https://arxiv.org/html/2603.05344v1) — engineering paper, cross-validates feature set
- [Minimal agent post-mortem — mariozechner.at](https://mariozechner.at/posts/2025-11-30-pi-coding-agent/) — practitioner anti-feature rationale (full-screen TUI, built-in plan display)

---
*Research completed: 2026-03-11*
*Ready for roadmap: yes*
