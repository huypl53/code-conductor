---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 13-02-PLAN.md (add Pause button to InterventionPanel, phase 13 complete)
last_updated: "2026-03-11T02:09:37.928Z"
last_activity: "2026-03-10 — Phase 2 Plan 1 complete: Pydantic v2 state models, enums, and error hierarchy"
progress:
  total_phases: 14
  completed_phases: 12
  total_plans: 28
  completed_plans: 27
  percent: 10
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-10)

**Core value:** A product owner describes a feature, and a self-organizing team of AI coding agents delivers quality, reviewed, tested code — with the human staying in control when they want to be.
**Current focus:** Phase 2 — Shared State Infrastructure

## Current Position

Phase: 2 of 11 (Shared State Infrastructure)
Plan: 1 of TBD in current phase
Status: In progress
Last activity: 2026-03-10 — Phase 2 Plan 1 complete: Pydantic v2 state models, enums, and error hierarchy

Progress: [█░░░░░░░░░] 10%

## Performance Metrics

**Velocity:**
- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: none yet
- Trend: -

*Updated after each plan completion*
| Phase 01-monorepo-foundation P01 | 2 | 2 tasks | 13 files |
| Phase 01-monorepo-foundation P02 | 8 | 2 tasks | 13 files |
| Phase 02-shared-state-infrastructure P01 | 5 | 2 tasks | 6 files |
| Phase 02-shared-state-infrastructure P02 | 8 | 2 tasks | 3 files |
| Phase 03-acp-communication-layer P01 | 3 | 2 tasks | 5 files |
| Phase 03-acp-communication-layer P02 | 4 | 2 tasks | 3 files |
| Phase 04-orchestrator-core P01 | 3 | 2 tasks | 6 files |
| Phase 04-orchestrator-core P02 | 2 | 2 tasks | 5 files |
| Phase 04-orchestrator-core P03 | 4 | 2 tasks | 5 files |
| Phase 05-orchestrator-intelligence P01 | 4 | 2 tasks | 7 files |
| Phase 05-orchestrator-intelligence P02 | 7 | 1 tasks | 2 files |
| Phase 06-escalation-and-intervention P01 | 3 | 1 tasks | 4 files |
| Phase 06-escalation-and-intervention P02 | 4 | 1 tasks | 2 files |
| Phase 07-agent-runtime P01 | 3 | 2 tasks | 5 files |
| Phase 07-agent-runtime P02 | 132 | 2 tasks | 4 files |
| Phase 07-agent-runtime P03 | 12 | 2 tasks | 2 files |
| Phase 08-cli-interface P01 | 4 | 2 tasks | 7 files |
| Phase 08-cli-interface P02 | 4 | 2 tasks | 3 files |
| Phase 09-dashboard-backend P01 | 87 | 1 tasks | 3 files |
| Phase 09-dashboard-backend P02 | 3 | 2 tasks | 7 files |
| Phase 10-dashboard-frontend P01 | 5 | 2 tasks | 11 files |
| Phase 10-dashboard-frontend P02 | 5 | 2 tasks | 9 files |
| Phase 10-dashboard-frontend P03 | 10 | 2 tasks | 11 files |
| Phase 11-packaging-and-distribution P01 | 2 | 2 tasks | 6 files |
| Phase 11-packaging-and-distribution P02 | 2 | 2 tasks | 1 files |
| Phase 12-fix-cli-cancel-redirect P01 | 10 | 2 tasks | 2 files |
| Phase 13-wire-escalation-pause P02 | 7 | 1 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Build order is state → ACP → orchestrator → CLI → dashboard backend → dashboard frontend → packaging (non-negotiable dependency chain)
- Roadmap: CLI (Phase 8) delivers working multi-agent product; dashboard phases (9-10) are significant investment, validate core loop first
- Roadmap: All three critical pitfalls (state corruption, cost explosion, over-parallelization) addressed in Phases 2-4 before any parallel agent work
- [Phase 01-monorepo-foundation]: uv workspace members uses explicit list [packages/conductor-core] not glob to avoid including Node.js conductor-dashboard as Python member
- [Phase 01-monorepo-foundation]: ruff added to conductor-core dev dependencies so uv run ruff works without global install
- [Phase 01-monorepo-foundation]: Biome 2.x uses assist.actions.source.organizeImports (removed top-level organizeImports key in 2.x)
- [Phase 01-monorepo-foundation]: Node 22 used in CI (current LTS); pnpm/action-setup@v4 with version 9 as specified
- [Phase 02-shared-state-infrastructure]: Use StrEnum + ConfigDict(use_enum_values=True) for clean JSON enum serialization — prevents "TaskStatus.pending" repr leaking into state.json
- [Phase 02-shared-state-infrastructure]: Use datetime.UTC alias (ruff UP017) instead of timezone.utc — enforced by project lint config
- [Phase 02-shared-state-infrastructure]: StateError exception hierarchy provides unified catch handling for all state operation failures
- [Phase 02-shared-state-infrastructure]: _spawn_write_tasks placed in conductor.state.manager (installed package) not tests/ — pytest importlib mode prevents spawned processes from importing test modules
- [Phase 02-shared-state-infrastructure]: StateManager lock file at state_path.with_suffix('.json.lock') — same directory as state.json guarantees same filesystem for atomic os.replace
- [Phase 03-acp-communication-layer]: PermissionHandler uses asyncio.wait_for for all async decision logic — ensures no deadlock from unanswered sub-agent prompts
- [Phase 03-acp-communication-layer]: asyncio.to_thread for StateManager.read_state() inside async callbacks — never block the event loop
- [Phase 03-acp-communication-layer]: Permission routing: AskUserQuestion -> answer_fn, everything else -> default-allow with input passthrough
- [Phase 03-acp-communication-layer]: ACPClient uses _closed flag set in __aexit__ finally block — ensures flag is set even if disconnect raises
- [Phase 03-acp-communication-layer]: PreToolUse keepalive hook (SyncHookJSONOutput) is mandatory SDK companion to can_use_tool — always register both or neither
- [Phase 03-acp-communication-layer]: setting_sources parameter typed as list[SettingSource] not list[str] — enforces SDK type contract at call site
- [Phase 04-orchestrator-core]: CycleError stores cycle as list[str] via .cycle attribute — enables graph debug output without string parsing
- [Phase 04-orchestrator-core]: TaskPlan.model_json_schema() is the output_format contract for SDK structured decomposition
- [Phase 04-orchestrator-core]: Task state model extended with all-default new fields (requires, produces, target_file, material_files) — backward compat with existing serialized state guaranteed
- [Phase 04-orchestrator-core]: build_system_prompt() includes 'Do not modify files outside your assignment' as explicit constraint for role anchoring over long sessions
- [Phase 04-orchestrator-core]: DependencyScheduler accepts dict[str, set[str]] graph — decouples from Pydantic TaskSpec, orchestrator builds graph at wire-up time
- [Phase 04-orchestrator-core]: validate_file_ownership accepts list[(task_id, target_file)] tuples — same decoupling rationale, avoids coupling to TaskSpec before Plan 03 wires it
- [Phase 04-orchestrator-core]: DECOMPOSE_PROMPT_TEMPLATE uses XML boundary tags to mitigate prompt injection from untrusted feature descriptions
- [Phase 04-orchestrator-core]: asyncio.wait(FIRST_COMPLETED) drives spawn loop — ready tasks unblock as dependencies complete without waiting for whole wave
- [Phase 04-orchestrator-core]: AgentRecord written to state before ACPClient.__aenter__ — state remains consistent even if session crashes before cleanup
- [Phase 05-orchestrator-intelligence]: StreamMonitor does NOT take StateManager — lightweight, state writes happen in orchestrator (Plan 02)
- [Phase 05-orchestrator-intelligence]: review_output() uses asyncio.to_thread for file reads — avoids blocking event loop under parallelism
- [Phase 05-orchestrator-intelligence]: Content truncation: first 4000 + last 4000 chars with notice — preserves module declarations and end-of-file implementations
- [Phase 05-orchestrator-intelligence]: ReviewStatus.PENDING/APPROVED/NEEDS_REVISION StrEnum with backward-compatible defaults on Task model
- [Phase 05-orchestrator-intelligence]: _run_agent_loop max_revisions defaults to instance-level self._max_revisions — per-orchestrator config without per-call override
- [Phase 05-orchestrator-intelligence]: revision_num from for loop used as revision_count — captures final iteration index naturally without extra counter
- [Phase 05-orchestrator-intelligence]: Single async-with ACPClient block for entire revision loop — session must stay open between review and revision send
- [Phase 06-escalation-and-intervention]: EscalationRouter.resolve() always returns PermissionResultAllow — escalation routing never denies
- [Phase 06-escalation-and-intervention]: Auto mode strictly ignores human_out/human_in queues — mode takes precedence over queue availability
- [Phase 06-escalation-and-intervention]: _LOW_CONFIDENCE_KEYWORDS frozenset: delete/drop/remove/irreversible/cannot be undone/production/deploy/billing/secret/credentials
- [Phase 06-escalation-and-intervention]: _active_clients cleanup in try/finally inside async-with ACPClient block — ensures cleanup even on SessionError
- [Phase 06-escalation-and-intervention]: cancel_agent uses asyncio.create_task fire-and-forget for new session — caller does not wait for reassigned agent
- [Phase 06-escalation-and-intervention]: pause_for_human_decision drains stream_response() after interrupt — prevents stale message corruption
- [Phase 07-agent-runtime]: AgentRecord session_id/memory_file/started_at all default None for backward compat with existing serialized state
- [Phase 07-agent-runtime]: Memory file path convention is .memory/<agent-name>.md using AgentIdentity.name (unique per agent-task-uuid)
- [Phase 07-agent-runtime]: Orchestrator default max_agents raised from 5 to 10 — decomposer TaskPlan.max_agents (1-10 schema) is binding constraint
- [Phase 07-agent-runtime]: ACPClient resume parameter positioned after system_prompt to preserve existing keyword-only API order
- [Phase 07-agent-runtime]: SessionRegistry.load() silently returns empty registry on missing/invalid JSON — crash-safe startup
- [Phase 07-agent-runtime]: filelock lock file at path.with_suffix('.json.lock') for SessionRegistry — mirrors StateManager pattern
- [Phase 07-agent-runtime]: Orchestrator SessionRegistry loaded from .conductor/sessions.json on init — crash-safe, empty registry on missing file
- [Phase 07-agent-runtime]: session_id persisted via get_server_info() in try/except — not a fatal error if SDK method unavailable
- [Phase 07-agent-runtime]: pre_run_review() uses query() (single-exchange, no PermissionHandler) — never blocks on human input in auto mode
- [Phase 07-agent-runtime]: SpecReview Pydantic model with is_clear/issues/confirmed_description — JSON schema enforced structured output
- [Phase 07-agent-runtime]: run_auto() is the --auto CLI entry point — chains pre_run_review then run
- [Phase 08-cli-interface]: Typer name= parameter not prog_name= in typer>=0.12 — fixed during execution (Rule 1 auto-fix)
- [Phase 08-cli-interface]: asyncio.gather combines _display_loop and orch_task — live table and orchestrator run concurrently
- [Phase 08-cli-interface]: Live(console=Console(stderr=False)) prevents mixing Rich table output with stderr SDK logs
- [Phase 08-cli-interface]: asyncio.wait FIRST_COMPLETED races terminal input vs. HumanQuery queue events — prevents blocking on one source while the other has data
- [Phase 08-cli-interface]: Console(stderr=True) for input loop — confirmation messages and agent questions appear on stderr, never interfering with Rich Live table on stdout
- [Phase 08-cli-interface]: asyncio.Queue typed as Queue[HumanQuery]/Queue[str] — eliminates pyright type errors and makes queue contracts explicit
- [Phase 09-dashboard-backend]: EventType uses StrEnum so values compare equal to plain strings — classify_delta compares task.status to string literals without needing TaskStatus import
- [Phase 09-dashboard-backend]: classify_delta returns [] when prev is None (initial snapshot) — avoids emitting TASK_ASSIGNED for every task on first load
- [Phase 09-dashboard-backend]: Watch parent directory (not state_path directly) — watchfiles misses atomic os.replace inode swaps when watching the file itself
- [Phase 09-dashboard-backend]: broadcast iterates list(active_connections) copy — avoids mutation-during-iteration when disconnecting dead clients
- [Phase 09-dashboard-backend]: gather_extras list pattern — clean conditional task injection into asyncio.gather without restructuring existing orchestrator coroutines
- [Phase 10-dashboard-frontend]: Use defineConfig from vitest/config (not vite) to enable test: {} block without TypeScript errors in Vitest 4.x
- [Phase 10-dashboard-frontend]: TYPE_CHECKING guard for Orchestrator import in server.py avoids circular import while preserving type annotations
- [Phase 10-dashboard-frontend]: handle_intervention wraps orchestrator calls in try/except to prevent WebSocket disconnection on errors
- [Phase 10-dashboard-frontend]: MockWebSocket class assigned to globalThis.WebSocket — standard pattern for testing WebSocket hooks in jsdom without a real server
- [Phase 10-dashboard-frontend]: applyDelta returns null when state is null — delta-before-snapshot is a no-op, safe to ignore without snapshot
- [Phase 10-dashboard-frontend]: Events array capped at 500 via FIFO eviction (slice from tail) — prevents unbounded memory growth in long sessions
- [Phase 10-dashboard-frontend]: useRef for lastProcessed index in useSmartNotifications avoids re-firing toasts on re-renders
- [Phase 10-dashboard-frontend]: Single activeInput state (feedback|redirect|null) for InterventionPanel ensures mutual exclusivity
- [Phase 11-packaging-and-distribution]: Package name is conductor-ai (PyPI) but import path remains conductor — documented in README
- [Phase 11-packaging-and-distribution]: sirv (not sirv-cli) used as production dep — bin script uses Node HTTP server API directly
- [Phase 11-packaging-and-distribution]: bin script uses ES module syntax (import.meta.url) for __dirname resolution, consistent with type:module package
- [Phase 11-packaging-and-distribution]: Task 2 (human-verify checkpoint) was auto-approved per user direction for fully autonomous execution
- [Phase 11-packaging-and-distribution]: Guide documents conductor run, --auto, --dashboard-port commands as the canonical CLI interface (Phase 8 contracts)
- [Phase 12-fix-cli-cancel-redirect]: cancel_agent reconstructs TaskSpec from state internally — CLI only needs to pass agent_id and optional new_instructions string
- [Phase 12-fix-cli-cancel-redirect]: Unknown agent_id in cancel_agent returns early as safe no-op (not an error, not a re-spawn)
- [Phase 13-wire-escalation-pause]: Pause placeholder falls through to final else branch — the only remaining ActiveInput value when not feedback/redirect
- [Phase 13-wire-escalation-pause]: Purple color scheme (bg-purple-100/600) for Pause distinguishes it from Cancel (red), Feedback (blue), Redirect (amber)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3 (ACP Layer): `ClaudeSDKClient` session management and interrupt semantics need validation against SDK 0.1.48 docs before implementation
- Phase 4 (Orchestrator Core): Orchestrator prompt engineering for role anchoring over long sessions is the highest-risk unknown — consider research-phase before Phase 4

## Session Continuity

Last session: 2026-03-11T02:09:37.925Z
Stopped at: Completed 13-02-PLAN.md (add Pause button to InterventionPanel, phase 13 complete)
Resume file: None
