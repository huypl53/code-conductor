# Roadmap: Conductor

## Milestones

- ✅ **v1.0 MVP** — Phases 1-17 (shipped 2026-03-11)
- ✅ **v1.1 Interactive Chat TUI** — Phases 18-22 (completed 2026-03-11)
- ✅ **v1.2 Task Verification & Build Safety** — Phases 23-25 (completed 2026-03-11)
- ✅ **v1.3 Orchestrator Intelligence** — Phases 26-30 (completed 2026-03-11)
- ✅ **v2.0 Textual TUI Redesign** — Phases 31-38 (completed 2026-03-11)
- 🚧 **v2.1 UX Polish** — Phases 39-42 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-17) — SHIPPED 2026-03-11</summary>

- [x] Phase 1: Monorepo Foundation (2/2 plans) — completed 2026-03-10
- [x] Phase 2: Shared State Infrastructure (2/2 plans) — completed 2026-03-10
- [x] Phase 3: ACP Communication Layer (2/2 plans) — completed 2026-03-10
- [x] Phase 4: Orchestrator Core (3/3 plans) — completed 2026-03-10
- [x] Phase 5: Orchestrator Intelligence (2/2 plans) — completed 2026-03-10
- [x] Phase 6: Escalation and Intervention (2/2 plans) — completed 2026-03-10
- [x] Phase 7: Agent Runtime (3/3 plans) — completed 2026-03-10
- [x] Phase 8: CLI Interface (2/2 plans) — completed 2026-03-10
- [x] Phase 9: Dashboard Backend (2/2 plans) — completed 2026-03-10
- [x] Phase 10: Dashboard Frontend (3/3 plans) — completed 2026-03-10
- [x] Phase 11: Packaging and Distribution (2/2 plans) — completed 2026-03-10
- [x] Phase 12: Fix CLI Cancel/Redirect Signatures (1/1 plan) — completed 2026-03-11
- [x] Phase 13: Wire Escalation Router + Pause Surface (2/2 plans) — completed 2026-03-11
- [x] Phase 14: Fix Getting-Started Guide .env Claim (1/1 plan) — completed 2026-03-11
- [x] Phase 15: Fix Dashboard Server Cancel Type Mismatch (1/1 plan) — completed 2026-03-11
- [x] Phase 16: Fix Agent Status Lifecycle (1/1 plan) — completed 2026-03-11
- [x] Phase 17: Fix Production WebSocket URL (1/1 plan) — completed 2026-03-11

Full details: `.planning/milestones/v1.0-ROADMAP.md`

</details>

<details>
<summary>✅ v1.1 Interactive Chat TUI (Phases 18-22) — COMPLETED 2026-03-11</summary>

- [x] **Phase 18: CLI Foundation and Input Layer** — completed 2026-03-11
- [x] **Phase 19: Streaming Display and Session Lifecycle** — completed 2026-03-11
- [x] **Phase 20: Session Resumption** — completed 2026-03-11
- [x] **Phase 21: Smart Delegation and Orchestrator Integration** — completed 2026-03-11
- [x] **Phase 22: Sub-Agent Visibility and Escalation Bridge** — completed 2026-03-11

</details>

<details>
<summary>✅ v1.2 Task Verification & Build Safety (Phases 23-25) — COMPLETED 2026-03-11</summary>

- [x] **Phase 23: Resume Robustness** — completed 2026-03-11
- [x] **Phase 24: Task Verification and Quality Loops** — completed 2026-03-11
- [x] **Phase 25: Post-Run Build Verification** — completed 2026-03-11

</details>

<details>
<summary>✅ v1.3 Orchestrator Intelligence (Phases 26-30) — COMPLETED 2026-03-11</summary>

- [x] **Phase 26: Models & Scheduler Infrastructure** — completed 2026-03-11
- [x] **Phase 27: Execution & Routing Pipeline** — completed 2026-03-11
- [x] **Phase 28: Agent Communication Protocol** — completed 2026-03-11
- [x] **Phase 29: Verification & Review Pipeline** — completed 2026-03-11
- [x] **Phase 30: Smart Decomposition** — completed 2026-03-11

</details>

<details>
<summary>✅ v2.0 Textual TUI Redesign (Phases 31-38) — COMPLETED 2026-03-11</summary>

- [x] **Phase 31: TUI Foundation** — completed 2026-03-11
- [x] **Phase 32: Static TUI Shell** — completed 2026-03-11
- [x] **Phase 33: SDK Streaming** — completed 2026-03-11
- [x] **Phase 34: Rich Output** — completed 2026-03-11
- [x] **Phase 35: Agent Monitoring** — completed 2026-03-11
- [x] **Phase 36: Approval Modals** — completed 2026-03-11
- [x] **Phase 37: Slash Commands & Dashboard Coexistence** — completed 2026-03-11
- [x] **Phase 38: Session Persistence & Polish** — completed 2026-03-11

</details>

### v2.1 UX Polish (In Progress)

**Milestone Goal:** Refine the Textual TUI to feel native and polished in the terminal — auto-focus, full alt-screen mode, borderless design, smooth animations, and external editor support — bringing the TUI to parity with OpenAI Codex CLI's terminal integration quality.

- [x] **Phase 39: Auto-Focus & Alt-Screen** — Input auto-focuses on start; TUI fully owns the terminal with clean entry/exit on all exit paths (completed 2026-03-11)
- [x] **Phase 40: Borderless Design** — CSS-only redesign removes visible box borders on layout containers and replaces thick cell borders with subtle accent lines (completed 2026-03-11)
- [ ] **Phase 41: Smooth Cell Animations** — New cells fade in via opacity animation on mount; env var toggle disables animations for CI/SSH
- [ ] **Phase 42: Ctrl-G External Editor** — Ctrl-G suspends TUI, opens $VISUAL/$EDITOR with current input pre-populated, reads result back into CommandInput

## Phase Details

### Phase 26: Models & Scheduler Infrastructure
**Goal**: Add foundational data models and scheduler capabilities that all subsequent phases depend on
**Depends on**: Phase 25 (v1.2 complete)
**Requirements**: INFRA-01, INFRA-02, MODEL-01
**Success Criteria** (what must be TRUE):
  1. `scheduler.compute_waves()` returns a list of lists where each inner list contains task IDs that can execute concurrently
  2. `OrchestratorConfig` model exists with `max_review_iterations`, `max_decomposition_retries` fields and the orchestrator reads from it instead of hardcoded defaults
  3. `ModelProfile` model exists with role-to-model mapping and at least three presets (quality, balanced, budget)
  4. All existing tests still pass after adding new models
**Plans**: 1 plan
Plans:
- [x] 26-01-PLAN.md — OrchestratorConfig, ModelProfile, compute_waves(), and orchestrator wiring

### Phase 27: Execution & Routing Pipeline
**Goal**: Orchestrator spawns tasks in waves for maximum parallelism, routes model selection per agent role, and uses lean prompts to preserve agent context
**Depends on**: Phase 26
**Requirements**: WAVE-01, ROUTE-01, LEAN-01
**Success Criteria** (what must be TRUE):
  1. The orchestrator's run() method spawns all tasks in a wave concurrently and waits for the wave to complete before starting the next
  2. ACPClient constructor accepts an optional `model` parameter that gets passed to the underlying SDK
  3. The orchestrator passes the active ModelProfile's role-specific model to each ACPClient instance
  4. Agent system prompts contain file paths to read, not file content — keeping prompts under 500 tokens
  5. All existing tests still pass; new tests cover wave execution and model routing
**Plans**: 1 plan
Plans:
- [x] 27-01-PLAN.md — Wave-based spawn loop, ACPClient model routing, lean system prompts

### Phase 28: Agent Communication Protocol
**Goal**: Agents report structured status (DONE/BLOCKED/NEEDS_CONTEXT) that the orchestrator parses and routes programmatically, with deviation rules preventing unplanned scope creep
**Depends on**: Phase 27
**Requirements**: STAT-01, STAT-02, DEVN-01
**Success Criteria** (what must be TRUE):
  1. Agent system prompt instructs agents to output a JSON status block with status, summary, files_changed, and concerns fields
  2. The orchestrator parses AgentReport from agent output and routes based on status enum
  3. BLOCKED status triggers retry with additional context or escalation to human
  4. NEEDS_CONTEXT status triggers context provision and retry
  5. Agent prompts include deviation rules: auto-fix for bugs/missing-critical (Rules 1-3), escalate for architectural changes (Rule 4)
**Plans**: 1 plan
Plans:
- [x] 28-PLAN.md — AgentReport model, status parsing, routing, deviation rules

### Phase 29: Verification & Review Pipeline
**Goal**: Every completed task is independently verified for substance and wiring (not just file existence), and review is split into spec compliance and code quality stages for faster, more focused feedback
**Depends on**: Phase 28
**Requirements**: VERI-01, VERI-02, RVEW-01
**Success Criteria** (what must be TRUE):
  1. `TaskVerifier.verify()` returns a three-level result: exists, substantive (not a stub), wired (imported by other files)
  2. Stub detection catches common patterns: pass-only functions, NotImplementedError, TODO markers, empty returns
  3. Wiring check confirms target file is imported/referenced by at least one other project file
  4. `review_spec_compliance()` checks output against task description independently from code quality
  5. `review_code_quality()` only runs after spec compliance passes — failing spec skips quality review
  6. All existing tests pass; new tests cover verifier and two-stage review
**Plans**: 2 plans
Plans:
- [x] 29-01-PLAN.md — TaskVerifier module and two-stage reviewer refactor with tests
- [x] 29-02-PLAN.md — Wire verifier into orchestrator, update exports, integration tests

### Phase 30: Smart Decomposition
**Goal**: The decomposer produces better task plans by scoring complexity and selectively expanding only high-complexity tasks, giving each sub-task AI-specific guidance
**Depends on**: Phase 26 (needs models only)
**Requirements**: DCMP-01, DCMP-02
**Success Criteria** (what must be TRUE):
  1. `decompose()` returns tasks with a `complexity_score` (1-10) and `reasoning` field
  2. Tasks with `complexity_score > 5` are automatically expanded into sub-tasks
  3. Each expansion includes a task-specific `expansion_prompt` that guides the sub-task decomposition
  4. Low-complexity tasks (score <= 5) pass through unchanged
  5. The expanded task plan maintains correct dependency relationships
**Plans**: 1 plan
Plans:
- [x] 30-01-PLAN.md — Complexity scoring, selective expansion, dependency rewiring

### Phase 31: TUI Foundation
**Goal**: Textual owns the asyncio event loop and ConductorApp is the sole process entry point — prompt_toolkit is fully removed, all conflicting patterns eliminated, and the test infrastructure is established so subsequent phases can be verified in headless mode
**Depends on**: Phase 30 (v1.3 complete)
**Requirements**: TUIF-01, TUIF-02, TUIF-03, TUIF-04
**Success Criteria** (what must be TRUE):
  1. Running `conductor` launches a Textual full-screen TUI instead of the prompt_toolkit REPL — the terminal switches to alternate screen mode
  2. No `prompt_toolkit` import appears in any code path executed during TUI lifetime — verified by grep and runtime audit
  3. All async subsystems (SDK client, uvicorn dashboard server, orchestrator delegation) launch as Textual workers or asyncio tasks inside `ConductorApp.on_mount` — no competing `asyncio.run()` calls exist in the TUI entry path
  4. A `pytest` test using Textual's `run_test()` pilot can launch `ConductorApp` in headless mode and assert the app starts without error
**Plans**: 1 plan
Plans:
- [x] 31-01-PLAN.md — ConductorApp entry point, delegation.py cleanup, headless test infrastructure

### Phase 32: Static TUI Shell
**Goal**: The two-column TUI layout is verified with hard-coded content — TranscriptPane displays user message cells, CommandInput submits text, StatusFooter renders structural info, and AgentMonitorPane placeholder renders — before any live data is connected
**Depends on**: Phase 31
**Requirements**: TRNS-01
**Success Criteria** (what must be TRUE):
  1. User can type a message and press Enter — a user message cell appears in the scrollable transcript with visually distinct styling from assistant cells
  2. The transcript scrolls as cells are added and older cells remain visible by scrolling up
  3. The CommandInput widget at the bottom accepts text input and clears after submission
  4. A status footer bar is visible at the bottom of the screen (structural, not yet live-wired)
  5. An agent monitor panel area is visible on the right side (placeholder, not yet reactive)
**Plans**: 1 plan
Plans:
- [x] 32-01-PLAN.md — TranscriptPane, UserCell/AssistantCell, CommandInput, StatusFooter, AgentMonitorPane placeholder

### Phase 33: SDK Streaming
**Goal**: Users see real Claude responses streaming token-by-token into the active transcript cell with a thinking indicator before the first token arrives, and the status footer displays live token counts
**Depends on**: Phase 32
**Requirements**: TRNS-02, STAT-01
**Success Criteria** (what must be TRUE):
  1. After submitting a prompt, a thinking indicator (spinner or animated indicator) appears in the transcript before any response text arrives
  2. Response tokens appear incrementally in the active assistant cell as they are generated — the user never waits for the full response before seeing output
  3. The status footer displays the current model name, mode (auto/interactive), and live token count that updates as the response streams
  4. The session ID is visible in the status footer
  5. When streaming completes, the active cell becomes immutable and the input widget reactivates
**Plans**: 2 plans
Plans:
- [x] 33-01-PLAN.md — Streaming widget upgrades (AssistantCell lifecycle, StatusFooter reactives, tests)
- [x] 33-02-PLAN.md — SDK @work streaming coroutine wiring in ConductorApp

### Phase 34: Rich Output
**Goal**: Code, markdown, and diffs in assistant responses render with full visual formatting — syntax-highlighted code blocks, proper markdown structure, and color-coded diff additions/deletions — making output readable without leaving the terminal
**Depends on**: Phase 33
**Requirements**: TRNS-03, TRNS-04, TRNS-05
**Success Criteria** (what must be TRUE):
  1. Code blocks in responses render with language-appropriate syntax highlighting (e.g. Python keywords colored, strings colored)
  2. Markdown headings render larger/bolder, bold text renders bold, bullet lists render with proper indentation, blockquotes render with visual offset
  3. File diffs render with green-highlighted addition lines and red-highlighted deletion lines — diff syntax is visually distinct from prose
**Plans**: 1 plan
Plans:
- [x] 34-01-PLAN.md — RichMarkdown widget with diff-aware highlighting, wired into AssistantCell

### Phase 35: Agent Monitoring
**Goal**: Users see live per-agent status panels in the TUI without switching to the web dashboard — panels appear when delegation starts, update reactively as state.json changes, and collapse when agents complete
**Depends on**: Phase 33
**Requirements**: AGNT-01, AGNT-02, AGNT-03, AGNT-04
**Success Criteria** (what must be TRUE):
  1. When the orchestrator delegates to agents, a collapsible panel appears in the agent monitor area for each active agent showing name, task, and current status
  2. Agent panel status and elapsed time update in real-time as state.json changes — without manual refresh or polling delay visible to the user
  3. Expanding an agent panel reveals streaming tool activity lines (file reads, edits, shell commands) as the agent works
  4. When an agent completes its task, its panel collapses or moves to an archived state — the panel does not remain as an active item
**Plans**: 1 plan
Plans:
- [x] 35-01-PLAN.md — AgentPanel, AgentMonitorPane StateWatchWorker, and tests

### Phase 36: Approval Modals
**Goal**: Agent approval requests and escalation questions surface as modal overlays in the TUI — the user can approve or deny file changes and command execution, and reply to sub-agent questions, all without leaving the terminal
**Depends on**: Phase 35
**Requirements**: APRV-01, APRV-02, APRV-03
**Success Criteria** (what must be TRUE):
  1. When an agent requests approval to write a file, a modal overlay appears showing the file path and approve/deny options — the background TUI remains visible but inactive
  2. When an agent requests approval to run a command, a modal overlay appears showing the command and approve/deny options
  3. When a sub-agent escalates a question, a modal dialog appears prefixed with the agent ID and an input field — the user can type a reply and submit without any additional steps
  4. Approving or denying in the modal dismisses it and the background TUI immediately reactivates
**Plans**: 2 plans
Plans:
- [x] 36-01-PLAN.md — Modal widgets (FileApprovalModal, CommandApprovalModal, EscalationModal) + EscalationRequest message + tests
- [x] 36-02-PLAN.md — Wire _watch_escalations worker in ConductorApp, expose delegation queues, integration tests

### Phase 37: Slash Commands & Dashboard Coexistence
**Goal**: Users can type `/` to trigger a fuzzy autocomplete popup for slash commands, all existing slash commands work correctly, and the web dashboard runs simultaneously in the same process so both TUI and browser views are live at once
**Depends on**: Phase 36
**Requirements**: APRV-04
**Success Criteria** (what must be TRUE):
  1. Typing `/` in the input widget opens an autocomplete dropdown showing available slash commands with fuzzy matching as the user types additional characters
  2. Pressing Tab or Enter selects a command from the dropdown and populates the input field
  3. All existing slash commands (`/help`, `/exit`, `/status`, `/summarize`, `/resume`) execute correctly from the Textual input widget
  4. Running `conductor --dashboard-port 8000` starts both the Textual TUI and the WebSocket dashboard server in a single process — opening the dashboard URL in a browser shows live state
  5. `conductor run "..."` batch mode still works without launching the TUI
**Plans**: 1 plan
Plans:
- [x] 37-01-PLAN.md — SlashAutocomplete widget, slash command dispatch, dashboard coexistence wiring

### Phase 38: Session Persistence & Polish
**Goal**: Resumed sessions replay conversation history before input activates, in-progress cells show shimmer animation, and all v2.0 polish is complete — the TUI delivers a terminal experience credibly better than the prompt_toolkit baseline
**Depends on**: Phase 37
**Requirements**: STAT-02, STAT-03
**Success Criteria** (what must be TRUE):
  1. Running `conductor --resume` (or `--resume-id`) replays the prior conversation history as immutable cells in the transcript before the input widget activates
  2. While an assistant response is streaming, the active cell has a visible shimmer or pulse animation that stops when streaming completes
  3. The TUI passes a full end-to-end smoke test: launch, send a prompt, see streaming response, open agent monitor, approve a modal, use slash command, resume a session — all without error
**Plans**: 1 plan
Plans:
- [x] 38-01-PLAN.md — Shimmer animation on streaming cells, session history replay on resume

### Phase 39: Auto-Focus & Alt-Screen
**Goal**: Input is immediately active when the TUI starts — no Tab or click required — and the TUI fully owns the terminal with clean entry and exit on all exit paths including SIGINT and crash
**Depends on**: Phase 38 (v2.0 complete)
**Requirements**: FOCUS-01, TERM-01, TERM-02
**Success Criteria** (what must be TRUE):
  1. User launches `conductor` and can begin typing immediately — no Tab press or click is needed to activate the input widget
  2. The terminal switches to alt-screen on launch and restores the prior scrollback buffer completely on exit — no escape code artifacts remain in the scrollback
  3. Pressing Ctrl-C triggers a clean shutdown: the TUI exits, the terminal is restored, and the shell prompt appears normally
  4. Focus returns to the input widget automatically after a modal is dismissed — no manual re-focus step needed
**Plans**: 1 plan

Plans:
- [ ] 39-01-PLAN.md — AUTO_FOCUS class variable, SIGINT handler, terminal cleanup at CLI entry point

### Phase 40: Borderless Design
**Goal**: The TUI layout uses no visible box borders on structural containers — content flows naturally with minimal chrome — and cell widgets use subtle accent lines instead of thick borders, matching Codex CLI's content-first aesthetic
**Depends on**: Phase 39
**Requirements**: VIS-01, VIS-02
**Success Criteria** (what must be TRUE):
  1. The Screen, app-body container, and CommandInput area have no visible box borders — no lines frame the layout structure itself
  2. UserCell and AssistantCell widgets have a subtle left accent line indicating role rather than a thick box border surrounding the content
  3. AgentMonitorPane retains its column separator (border-left) as a functional divider — only pure chrome borders are removed
  4. All modal overlays retain their borders unchanged — borderless design applies only to main layout containers and transcript cells
**Plans**: 1 plan

Plans:
- [ ] 40-01-PLAN.md — transcript.py cell accent lines (VIS-02), command_input.py border-top removal (VIS-01), borderless regression tests

### Phase 41: Smooth Cell Animations
**Goal**: New conversation cells fade in on mount rather than appearing abruptly, making the TUI feel alive, with a complete disable path for CI and SSH environments
**Depends on**: Phase 40
**Requirements**: VIS-03, VIS-04
**Success Criteria** (what must be TRUE):
  1. When a new UserCell or AssistantCell mounts, it smoothly fades from invisible to fully visible over approximately 0.25 seconds
  2. The fade-in uses opacity animation, not tint or tween hacks — existing shimmer behavior on streaming cells is unchanged
  3. Setting `CONDUCTOR_NO_ANIMATIONS=1` in the environment disables all fade-in calls — cells appear instantly without any animation
  4. The animation disable path works without code changes or restarts — environment variable is read at startup and respected throughout the session
**Plans**: 1 plan

Plans:
- [ ] 41-01-PLAN.md — on_mount opacity fade-in in UserCell/AssistantCell, CONDUCTOR_NO_ANIMATIONS guard

### Phase 42: Ctrl-G External Editor
**Goal**: Power users can press Ctrl-G to open the current input text in their preferred editor, compose or edit multi-line content there, and have the result automatically fill the CommandInput on editor close
**Depends on**: Phase 39
**Requirements**: FOCUS-02, FOCUS-03
**Success Criteria** (what must be TRUE):
  1. Pressing Ctrl-G suspends the TUI, opens the user's `$VISUAL` or `$EDITOR` (vim as fallback) with the current input text pre-populated in a temp file
  2. After the editor closes, the temp file content replaces the CommandInput text exactly — including multi-line content
  3. The TUI resumes cleanly after editor exit — terminal state is fully restored and input is focused with the edited content
  4. Pressing Ctrl-G during session replay (when input is locked) does nothing — no crash, no broken terminal state
  5. In environments where suspend is not supported (CI, non-Unix), Ctrl-G fails gracefully with a status message rather than an exception
**Plans**: TBD

Plans:
- [ ] 42-01-PLAN.md — action_open_editor (sync def), EditorContentReady message, CommandInput handler, tests

## Progress

**Execution Order:**
Phases execute in numeric order: 39 → 40 → 41 → 42
(Phase 42 depends only on Phase 39 for stable terminal lifecycle; can run after Phase 41 or in parallel with it)

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Monorepo Foundation | v1.0 | 2/2 | Complete | 2026-03-10 |
| 2. Shared State Infrastructure | v1.0 | 2/2 | Complete | 2026-03-10 |
| 3. ACP Communication Layer | v1.0 | 2/2 | Complete | 2026-03-10 |
| 4. Orchestrator Core | v1.0 | 3/3 | Complete | 2026-03-10 |
| 5. Orchestrator Intelligence | v1.0 | 2/2 | Complete | 2026-03-10 |
| 6. Escalation and Intervention | v1.0 | 2/2 | Complete | 2026-03-10 |
| 7. Agent Runtime | v1.0 | 3/3 | Complete | 2026-03-10 |
| 8. CLI Interface | v1.0 | 2/2 | Complete | 2026-03-10 |
| 9. Dashboard Backend | v1.0 | 2/2 | Complete | 2026-03-10 |
| 10. Dashboard Frontend | v1.0 | 3/3 | Complete | 2026-03-10 |
| 11. Packaging and Distribution | v1.0 | 2/2 | Complete | 2026-03-10 |
| 12. Fix CLI Cancel/Redirect | v1.0 | 1/1 | Complete | 2026-03-11 |
| 13. Wire Escalation + Pause | v1.0 | 2/2 | Complete | 2026-03-11 |
| 14. Fix Getting-Started .env | v1.0 | 1/1 | Complete | 2026-03-11 |
| 15. Fix Dashboard Cancel Type | v1.0 | 1/1 | Complete | 2026-03-11 |
| 16. Fix Agent Status Lifecycle | v1.0 | 1/1 | Complete | 2026-03-11 |
| 17. Fix Production WebSocket URL | v1.0 | 1/1 | Complete | 2026-03-11 |
| 18. CLI Foundation and Input Layer | v1.1 | 1/1 | Complete | 2026-03-11 |
| 19. Streaming Display and Session Lifecycle | v1.1 | 1/1 | Complete | 2026-03-11 |
| 20. Session Resumption | v1.1 | 1/1 | Complete | 2026-03-11 |
| 21. Smart Delegation and Orchestrator Integration | v1.1 | 1/1 | Complete | 2026-03-11 |
| 22. Sub-Agent Visibility and Escalation Bridge | v1.1 | 1/1 | Complete | 2026-03-11 |
| 23. Resume Robustness | v1.2 | 1/1 | Complete | 2026-03-11 |
| 24. Task Verification and Quality Loops | v1.2 | 1/1 | Complete | 2026-03-11 |
| 25. Post-Run Build Verification | v1.2 | 1/1 | Complete | 2026-03-11 |
| 26. Models & Scheduler Infrastructure | v1.3 | 1/1 | Complete | 2026-03-11 |
| 27. Execution & Routing Pipeline | v1.3 | 1/1 | Complete | 2026-03-11 |
| 28. Agent Communication Protocol | v1.3 | 1/1 | Complete | 2026-03-11 |
| 29. Verification & Review Pipeline | v1.3 | 2/2 | Complete | 2026-03-11 |
| 30. Smart Decomposition | v1.3 | 1/1 | Complete | 2026-03-11 |
| 31. TUI Foundation | v2.0 | 1/1 | Complete | 2026-03-11 |
| 32. Static TUI Shell | v2.0 | 1/1 | Complete | 2026-03-11 |
| 33. SDK Streaming | v2.0 | 2/2 | Complete | 2026-03-11 |
| 34. Rich Output | v2.0 | 1/1 | Complete | 2026-03-11 |
| 35. Agent Monitoring | v2.0 | 1/1 | Complete | 2026-03-11 |
| 36. Approval Modals | v2.0 | 2/2 | Complete | 2026-03-11 |
| 37. Slash Commands & Dashboard Coexistence | v2.0 | 1/1 | Complete | 2026-03-11 |
| 38. Session Persistence & Polish | v2.0 | 1/1 | Complete | 2026-03-11 |
| 39. Auto-Focus & Alt-Screen | 1/1 | Complete   | 2026-03-11 | - |
| 40. Borderless Design | 1/1 | Complete   | 2026-03-11 | - |
| 41. Smooth Cell Animations | v2.1 | 0/1 | Not started | - |
| 42. Ctrl-G External Editor | v2.1 | 0/TBD | Not started | - |
