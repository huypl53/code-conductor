# Requirements: Conductor

**Defined:** 2026-03-11
**Core Value:** A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.

## v2.0 Requirements

Requirements for the Textual TUI Redesign milestone. Each maps to roadmap phases.

### TUI Foundation

- [ ] **TUIF-01**: User can launch `conductor` and see a full-screen Textual TUI instead of the current prompt_toolkit REPL
- [ ] **TUIF-02**: All async subsystems (SDK streaming, uvicorn dashboard, orchestrator delegation) run as workers inside Textual's event loop
- [ ] **TUIF-03**: prompt_toolkit is fully removed from the active code path — no terminal raw mode conflicts
- [ ] **TUIF-04**: Textual app can be tested with `pytest` using pilot/headless fixtures

### Transcript & Streaming

- [ ] **TRNS-01**: User sees a scrollable cell-based conversation transcript with distinct user and assistant cells
- [ ] **TRNS-02**: Assistant responses stream token-by-token into the active cell with a working/thinking indicator before first token
- [ ] **TRNS-03**: Code blocks in responses render with syntax highlighting
- [ ] **TRNS-04**: Markdown in responses renders with proper formatting (headings, bold, links, lists, blockquotes)
- [ ] **TRNS-05**: File diffs render with syntax-highlighted additions/deletions

### Agent Monitoring

- [ ] **AGNT-01**: User sees inline collapsible panels for each active agent showing name, task, and status
- [ ] **AGNT-02**: Agent panels update in real-time as state.json changes (wired to file watcher)
- [ ] **AGNT-03**: User can expand an agent panel to see streaming tool activity and output
- [ ] **AGNT-04**: Agent panels appear when delegation starts and collapse/archive when agents complete

### Approval & Interaction

- [ ] **APRV-01**: User sees a modal overlay when an agent requests approval for file changes, with approve/deny options
- [ ] **APRV-02**: User sees a modal overlay when an agent requests approval for command execution
- [ ] **APRV-03**: Escalation questions from sub-agents surface as modal dialogs with the agent ID and reply input
- [ ] **APRV-04**: User can type `/` to open a slash command autocomplete popup with fuzzy matching

### Status & Polish

- [ ] **STAT-01**: A status footer displays current model, mode, token usage, and session info
- [ ] **STAT-02**: In-progress cells show a shimmer/spinner animation
- [ ] **STAT-03**: Resumed sessions replay previous conversation history in the transcript before the input activates

## Previous Milestone Requirements

### v1.3 Orchestrator Intelligence

- [x] **INFRA-01**: OrchestratorConfig model with configurable max_review_iterations, max_decomposition_retries
- [x] **INFRA-02**: ModelProfile with role-to-model mapping and three presets (quality, balanced, budget)
- [x] **MODEL-01**: compute_waves() returns dependency-ordered wave lists for concurrent execution
- [x] **WAVE-01**: Orchestrator spawns tasks in pre-computed waves with asyncio.gather
- [x] **ROUTE-01**: ACPClient accepts model selection parameter; orchestrator routes model per role
- [x] **LEAN-01**: Agent system prompts pass file paths only, not content
- [x] **STAT-01**: Agents output structured JSON status blocks (DONE/BLOCKED/NEEDS_CONTEXT)
- [x] **STAT-02**: Orchestrator parses AgentReport and routes based on status enum
- [x] **DEVN-01**: Agent prompts include deviation rules for scope control
- [x] **VERI-01**: TaskVerifier with stub detection and wiring checks
- [x] **VERI-02**: Two-stage review (spec compliance then code quality)
- [x] **RVEW-01**: review_output() delegates to two-stage review pipeline
- [x] **DCMP-01**: Complexity scoring per task (1-10)
- [x] **DCMP-02**: Selective expansion of high-complexity tasks into sub-tasks

### v1.2 Task Verification & Build Safety

- [x] **RESM-01**: Resume path handles review_only exceptions gracefully
- [x] **RESM-02**: Spawn loop handles all completed-task edge cases
- [x] **VRFY-01**: File existence gate before marking task COMPLETED
- [x] **QUAL-01**: Structured review feedback with revision cycles
- [x] **QUAL-02**: Configurable max revision rounds with explicit failure mode
- [x] **VRFY-02**: Post-run build command with pass/fail reporting
- [x] **VRFY-03**: Build command configurable via CLI flag and config file

### v1.1 Interactive Chat TUI (19 requirements — all complete)

All 19 requirements delivered. See `.planning/milestones/v1.1-REQUIREMENTS.md`.

### v1.0 MVP (30 requirements — all complete)

All 30 requirements delivered. See `.planning/milestones/v1.0-REQUIREMENTS.md`.

## Future Requirements

Deferred to a later release. Tracked but not in current roadmap.

### Advanced Input

- **INPT-01**: Vi-mode keybindings for the input widget
- **INPT-02**: Multi-line input editing with proper cursor navigation
- **INPT-03**: Voice input support

### Visual Enhancements

- **VISL-01**: Collapsible tool activity within transcript cells
- **VISL-02**: Image rendering in terminal (via Kitty/iTerm2 protocols)
- **VISL-03**: Animated onboarding/welcome screen

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Rewrite TUI in Rust (Ratatui) | Textual stays in Python ecosystem, avoids FFI complexity |
| Replace web dashboard | TUI and web dashboard coexist — web serves remote/mobile access |
| Custom terminal color themes | Respect terminal theme with ANSI standard colors — no custom palettes |
| Real-time collaborative editing | Single-user tool — orchestrator mediates all coordination |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TUIF-01 | TBD | Pending |
| TUIF-02 | TBD | Pending |
| TUIF-03 | TBD | Pending |
| TUIF-04 | TBD | Pending |
| TRNS-01 | TBD | Pending |
| TRNS-02 | TBD | Pending |
| TRNS-03 | TBD | Pending |
| TRNS-04 | TBD | Pending |
| TRNS-05 | TBD | Pending |
| AGNT-01 | TBD | Pending |
| AGNT-02 | TBD | Pending |
| AGNT-03 | TBD | Pending |
| AGNT-04 | TBD | Pending |
| APRV-01 | TBD | Pending |
| APRV-02 | TBD | Pending |
| APRV-03 | TBD | Pending |
| APRV-04 | TBD | Pending |
| STAT-01 | TBD | Pending |
| STAT-02 | TBD | Pending |
| STAT-03 | TBD | Pending |

**Coverage:**
- v2.0 requirements: 20 total
- Mapped to phases: 0
- Unmapped: 20 ⚠️

---
*Requirements defined: 2026-03-11*
*Last updated: 2026-03-11 after initial definition*
