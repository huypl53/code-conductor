# Requirements: Conductor

**Defined:** 2026-03-11
**Core Value:** A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## v1.1 Requirements

Requirements for the Interactive Chat TUI milestone. Each maps to roadmap phases.

### Chat Interface

- [ ] **CHAT-01**: User can start interactive chat session via `conductor` (no args)
- [ ] **CHAT-02**: As the orchestrator responds, tokens stream into the chat incrementally (not buffered until complete)
- [ ] **CHAT-03**: First Ctrl+C stops the running agent and returns to the input prompt with a cancellation notice; second Ctrl+C exits the TUI
- [ ] **CHAT-04**: User can recall previous prompts with Up/Down arrow keys within the current session
- [ ] **CHAT-05**: User can paste multi-line text into the input without premature submission
- [ ] **CHAT-06**: Each direct tool invocation (file read, file edit, shell command) shows a human-readable status line in the chat (e.g. "Reading src/auth.py...")
- [ ] **CHAT-07**: A spinner or working indicator is visible from prompt submission until the first response token appears
- [ ] **CHAT-08**: User receives a warning when conversation context is running low, with an option to summarize and continue

### Smart Delegation

- [ ] **DELG-01**: Simple requests (e.g. "rename variable X to Y") complete directly without a delegation announcement or sub-agent overhead
- [ ] **DELG-02**: Complex requests (e.g. "add OAuth login") trigger a delegation announcement and spawn a sub-agent team
- [ ] **DELG-03**: Every request produces a visible delegation decision — either "Handling directly" or "Delegating to team" — before work begins
- [ ] **DELG-04**: When sub-agents are spawned, the delegation announcement includes a dashboard URL

### Session Management

- [ ] **SESS-01**: `/help` displays all supported slash commands with one-line descriptions
- [ ] **SESS-02**: `/exit` terminates the TUI, restores the terminal to its pre-launch state, and stops any running sub-agents
- [ ] **SESS-03**: `/status` shows a table of active sub-agents (ID, task, elapsed time); displays "No active agents" if none running
- [ ] **SESS-04**: `conductor --resume` lists recent sessions by timestamp and first prompt; selecting one restores conversation history before the input prompt activates
- [ ] **SESS-05**: Chat history is persisted to disk so it survives crashes and process kills

### Sub-Agent Visibility

- [ ] **VISB-01**: While sub-agents are active, the chat shows a per-agent status line that updates as agents progress, removed when all agents complete
- [ ] **VISB-02**: When a sub-agent escalates a question, it appears in the chat prefixed with the agent ID, and the input field activates for the user to reply

## v1.2+ Requirements

Deferred to future release. Tracked but not in current roadmap.

### Concurrency

- **CONC-01**: Multiple concurrent chat sessions with session-scoped state namespacing

### Enhanced Display

- **DISP-01**: Inline diff review in TUI for file changes
- **DISP-02**: Per-task GSD scope flexibility display in chat

### Input

- **INPT-01**: Voice input support

## Out of Scope

| Feature | Reason |
|---------|--------|
| Full-screen curses TUI | Loses terminal scrollback buffer; anti-feature per research |
| Built-in to-do/plan display in chat | Confuses model context; plans belong in files |
| MCP server integration surface | Inherits from `.claude/` naturally; no new TUI surface needed |
| Real-time token/cost tracking | Use provider console; accurate billing-grade tracking is non-trivial |
| Raw log streaming as primary view | Information overload; web dashboard covers full logs |
| Multiple chat modes (code/architect/ask) | Single conversational mode with implicit delegation is simpler |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CHAT-01 | Phase 18 | Complete |
| CHAT-02 | Phase 19 | Complete |
| CHAT-03 | Phase 18 | Complete |
| CHAT-04 | Phase 18 | Complete |
| CHAT-05 | Phase 18 | Complete |
| CHAT-06 | Phase 19 | Complete |
| CHAT-07 | Phase 19 | Complete |
| CHAT-08 | Phase 19 | Complete |
| DELG-01 | Phase 21 | Complete |
| DELG-02 | Phase 21 | Complete |
| DELG-03 | Phase 21 | Complete |
| DELG-04 | Phase 21 | Complete |
| SESS-01 | Phase 18 | Complete |
| SESS-02 | Phase 18 | Complete |
| SESS-03 | Phase 21 | Complete |
| SESS-04 | Phase 20 | Complete |
| SESS-05 | Phase 19 | Complete |
| VISB-01 | Phase 22 | Complete |
| VISB-02 | Phase 22 | Complete |

**Coverage:**
- v1.1 requirements: 19 total
- Mapped to phases: 19
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 after v1.1 milestone completion*
