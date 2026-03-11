# Roadmap: Conductor

## Milestones

- ✅ **v1.0 MVP** — Phases 1-17 (shipped 2026-03-11)
- ✅ **v1.1 Interactive Chat TUI** — Phases 18-22 (completed 2026-03-11)
- ✅ **v1.2 Task Verification & Build Safety** — Phases 23-25 (completed 2026-03-11)
- 🔄 **v1.3 Orchestrator Intelligence** — Phases 26-30 (in progress)

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

### v1.2 Task Verification & Build Safety

**Milestone Goal:** Ensure Conductor validates task output before marking tasks complete, with structured review cycles and hardened resume support.

- [x] **Phase 23: Resume Robustness** — Harden resume path so exceptions in review_only mode and spawn loop edge cases never crash the orchestrator (completed 2026-03-11)
- [x] **Phase 24: Task Verification and Quality Loops** — File existence gate forces re-runs when target files are missing; structured review cycles with configurable max rounds and explicit NEEDS_REVISION on exhaustion (completed 2026-03-11)
- [x] **Phase 25: Post-Run Build Verification** — Orchestrator runs a user-configured build command after all tasks complete and reports pass/fail with stderr output (completed 2026-03-11)

### v1.3 Orchestrator Intelligence

**Milestone Goal:** Make Conductor's orchestrator smarter — wave-based parallel execution, model routing for cost control, structured agent communication, goal-backward verification, and complexity-informed task decomposition.

- [ ] **Phase 26: Models & Scheduler Infrastructure** — Add foundational models (OrchestratorConfig, ModelProfile, AgentReport) and compute_waves() to scheduler
- [ ] **Phase 27: Execution & Routing Pipeline** — Wave-based spawn loop, model routing through ACPClient, context-lean agent prompts
- [ ] **Phase 28: Agent Communication Protocol** — Structured AgentReport status protocol, status-based routing, deviation classification rules
- [ ] **Phase 29: Verification & Review Pipeline** — TaskVerifier with stub detection and wiring checks, two-stage review (spec then quality)
- [ ] **Phase 30: Smart Decomposition** — Complexity scoring per task, selective expansion of high-complexity tasks

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
- [ ] 26-01-PLAN.md — OrchestratorConfig, ModelProfile, compute_waves(), and orchestrator wiring

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
- [ ] 27-01-PLAN.md — Wave-based spawn loop, ACPClient model routing, lean system prompts

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
**Plans**: TBD

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
**Plans**: TBD

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
**Plans**: TBD



### Phase 18: CLI Foundation and Input Layer
**Goal**: Users can open an interactive chat session by running `conductor` with no arguments, type and submit prompts with full input control (history, multiline, interrupt), and use basic slash commands to navigate
**Depends on**: Phase 17 (v1.0 complete)
**Requirements**: CHAT-01, CHAT-03, CHAT-04, CHAT-05, SESS-01, SESS-02
**Success Criteria** (what must be TRUE):
  1. Running `conductor` with no arguments opens an interactive input prompt instead of showing help text
  2. Pressing Up/Down arrow keys cycles through prompts submitted earlier in the current session
  3. Pasting multi-line text into the prompt does not submit prematurely — user must press Enter on an empty line or a designated submit key
  4. First Ctrl+C while a response is running stops the agent and returns to the prompt with a cancellation notice; second Ctrl+C in quick succession exits the TUI cleanly
  5. `/help` displays all slash commands with descriptions; `/exit` terminates cleanly and restores the terminal to its pre-launch state
**Plans**: TBD

### Phase 19: Streaming Display and Session Lifecycle
**Goal**: Users see orchestrator responses rendered token-by-token as they arrive, with a working indicator before the first token, human-readable tool activity lines, and a warning when context is running low — and all of this survives crashes because chat history is persisted to disk
**Depends on**: Phase 18
**Requirements**: CHAT-02, CHAT-06, CHAT-07, CHAT-08, SESS-05
**Success Criteria** (what must be TRUE):
  1. Orchestrator response tokens appear incrementally in the chat as they are generated — the user never waits for the full response before seeing output
  2. A spinner or working indicator is visible from the moment a prompt is submitted until the first response token appears
  3. Each direct tool invocation (file read, file edit, shell command) shows a human-readable status line in the chat (e.g. "Reading src/auth.py...") rather than raw JSON
  4. When conversation context reaches approximately 75% utilization, the user receives a warning with an option to summarize and continue
  5. Chat history written to disk so that a subsequent `conductor --resume` can restore it after a crash or process kill
**Plans**: TBD

### Phase 20: Session Resumption
**Goal**: Users can resume a prior chat session from exactly where they left off — conversation history is restored before the input prompt activates — so context is never lost across restarts
**Depends on**: Phase 19
**Requirements**: SESS-04
**Success Criteria** (what must be TRUE):
  1. Running `conductor --resume` shows a numbered list of recent sessions with timestamp and first prompt text for each
  2. Selecting a session from the list restores the full conversation history in the chat before the input prompt activates
  3. Resuming a session that was active during a crash or kill recovers all turns that were persisted before the interruption
**Plans**: TBD

### Phase 21: Smart Delegation and Orchestrator Integration
**Goal**: The orchestrator handles simple coding tasks (file edits, shell commands) directly in-context and transparently delegates complex tasks to a sub-agent team — every request produces a visible delegation decision before work begins
**Depends on**: Phase 19
**Requirements**: DELG-01, DELG-02, DELG-03, DELG-04, SESS-03
**Success Criteria** (what must be TRUE):
  1. A simple request (e.g. "rename variable X to Y in auth.py") completes via direct file edit with no delegation announcement or sub-agent overhead
  2. A complex request (e.g. "add OAuth login") triggers a "Delegating to team..." announcement and spawns a sub-agent team via the existing orchestrator
  3. Every request — simple or complex — produces a visible decision line ("Handling directly" or "Delegating to team") before any work begins
  4. When sub-agents are spawned, the delegation announcement includes the dashboard URL
  5. `/status` displays a table of active sub-agents with ID, task, and elapsed time; shows "No active agents" when none are running
**Plans**: TBD

### Phase 22: Sub-Agent Visibility and Escalation Bridge
**Goal**: Users can see live per-agent progress during delegation without switching to the dashboard, and escalation questions from sub-agents surface directly in the chat with the agent ID so users can reply without leaving the TUI
**Depends on**: Phase 21
**Requirements**: VISB-01, VISB-02
**Success Criteria** (what must be TRUE):
  1. While sub-agents are active, the chat displays a per-agent status line that updates as each agent progresses through its task
  2. When all sub-agents complete, the per-agent status lines are removed from the chat display
  3. When a sub-agent escalates a question, it appears in the chat prefixed with the agent ID and the input field activates immediately so the user can reply without any additional steps
**Plans**: TBD

### Phase 23: Resume Robustness
**Goal**: The resume path never crashes — review_only exceptions fall back gracefully, and the spawn loop correctly handles all completed-task edge cases so runs always reach a clean terminal state
**Depends on**: Phase 22 (v1.1 complete)
**Requirements**: RESM-01, RESM-02
**Success Criteria** (what must be TRUE):
  1. When a review_only review raises an exception, the task is approved with a warning log instead of crashing the orchestrator process
  2. When resuming a run where some tasks are already complete, the spawn loop does not exit prematurely — it processes all remaining ready tasks to completion
  3. Task exceptions surfaced from `get_ready()` are retrieved and logged without causing the resume loop to hang or crash
  4. The `marked_done` flag correctly tracks task completion so the loop exits only when all tasks have been handled
**Plans**: TBD

### Phase 24: Task Verification and Quality Loops
**Goal**: Every task that declares a target file is verified to have produced that file before being marked complete, and reviewers drive structured revision cycles with an explicit failure mode when retries are exhausted — no task silently completes with missing or unreviewed output
**Depends on**: Phase 23
**Requirements**: VRFY-01, QUAL-01, QUAL-02
**Success Criteria** (what must be TRUE):
  1. When an agent session ends and `target_file` is set but the file does not exist on disk, the orchestrator sends a revision message to the agent and re-enters the revision loop instead of marking the task COMPLETED
  2. When the file is still missing after all revision attempts are exhausted, the task is marked NEEDS_REVISION with a reason string, not silently completed
  3. The reviewer returns structured feedback that the agent receives as concrete revision instructions, not a raw boolean
  4. When the maximum number of revision rounds is reached without approval, the task is marked NEEDS_REVISION with the reviewer's last reason — the orchestrator does not approve it silently
  5. The maximum revision rounds is configurable (not hardcoded)
**Plans**: TBD

### Phase 25: Post-Run Build Verification
**Goal**: After all tasks finish, the orchestrator optionally runs a user-specified build command and reports whether the project builds cleanly — giving users a single-line verdict and the full error output if it fails
**Depends on**: Phase 24
**Requirements**: VRFY-02, VRFY-03
**Success Criteria** (what must be TRUE):
  1. After all tasks complete, if `build_command` is configured, the orchestrator runs it and prints "Build passed" or "Build failed" with the full stderr output
  2. A build failure does not mark any tasks as failed — it is a post-run report only
  3. `conductor run --build-command "npx tsc --noEmit"` passes the command through to the orchestrator and runs it after task completion
  4. The build command can be set in `.conductor/config.json` so it persists across runs without repeating the CLI flag
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 26 → 27 → 28 → 29 → 30 (Phase 30 can run after 26)

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
| 23. Resume Robustness | 1/1 | Complete   | 2026-03-11 | - |
| 24. Task Verification and Quality Loops | 1/1 | Complete   | 2026-03-11 | - |
| 25. Post-Run Build Verification | v1.2 | 1/1 | Complete | 2026-03-11 |
| 26. Models & Scheduler Infrastructure | v1.3 | 0/1 | In Progress | - |
| 27. Execution & Routing Pipeline | v1.3 | 0/1 | Pending | - |
| 28. Agent Communication Protocol | v1.3 | 0/0 | Pending | - |
| 29. Verification & Review Pipeline | v1.3 | 0/0 | Pending | - |
| 30. Smart Decomposition | v1.3 | 0/0 | Pending | - |
