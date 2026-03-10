# Pitfalls Research

**Domain:** Multi-agent coding orchestration (Claude Code orchestrator + ACP sub-agents)
**Researched:** 2026-03-10
**Confidence:** HIGH (critical pitfalls verified via multiple sources including official docs, GitHub issues, and research papers)

---

## Critical Pitfalls

### Pitfall 1: Shared State File Corruption from Concurrent Writes

**What goes wrong:**
Multiple sub-agents writing to `.conductor/state.json` simultaneously without coordination produce corrupted JSON — truncated files, partial writes caught mid-stream, or last-writer-wins collisions. Claude Code's own `.claude.json` has this exact bug in production (GitHub issues #28847, #29036, #29153). Once corrupted, recovery attempts that re-read the broken file compound the problem, producing progressively smaller broken files until all state is lost.

**Why it happens:**
Developers treat a JSON file as a simple shared variable. The atomic write pattern (write to `.tmp`, rename to target) is the right instinct, but it fails under concurrent contention: on Linux, rename() is atomic per POSIX but concurrent reads can still see stale data; multiple simultaneous writers can each write to differently-named temp files and one rename overwrites the other's data silently.

**How to avoid:**
- Use orchestrator-mediated state writes: sub-agents send state update requests to the orchestrator via ACP, and the orchestrator serializes all writes
- Alternatively, use per-agent namespaced state keys (each agent owns its own key, never overwrites another's section) with the orchestrator writing to shared/coordination sections exclusively
- Implement write-with-validation: read → validate checksum → merge → write → verify checksum on every mutation
- Never allow two processes to write to the same JSON key simultaneously

**Warning signs:**
- JSON parse errors in any consumer of state.json
- Agents reporting stale task statuses (reading outdated state)
- "Task completed" appearing simultaneously with "Task in progress" for the same task
- State file size shrinking unexpectedly

**Phase to address:** Core infrastructure phase (state management design) — before any multi-agent parallelism is implemented

---

### Pitfall 2: Runaway Token Costs from Unbounded Agent Proliferation

**What goes wrong:**
Each spawned sub-agent maintains its own context window, and the orchestrator's context grows with every agent communication it processes. A real-world example: 887,000 tokens/minute during a 2.5-hour session when 23 sub-agents were spawned without lifecycle limits. Enterprise teams report 300-500% higher costs than expected. Because there is no per-agent token attribution in Claude Code's `/cost` command, the explosion is invisible until the monthly bill arrives.

**Why it happens:**
The orchestrator is an LLM that has been told to "break work down and delegate." With no hard constraints, it will spawn as many agents as it thinks useful for the problem. Sub-agents themselves may spawn additional sub-agents. Neither the orchestrator nor sub-agents have built-in cost awareness.

**How to avoid:**
- Enforce a hard `max_agents` cap (recommended: 6-8 for typical features, configurable)
- Implement per-session and per-agent `max_turns` limits
- Add agent lifecycle timeouts: auto-terminate agents idle >N minutes
- Track tokens-per-minute velocity (not just total) and trigger alerts at thresholds
- Use cheaper models for sub-agents (Haiku/Sonnet) and reserve expensive models (Opus) for orchestrator planning steps only
- Lazy agent creation: start with 2-3 agents, scale up only when parallelism is clearly needed

**Warning signs:**
- Orchestrator spawning more than 8-10 agents for a single feature
- Sub-agents spawning their own sub-agents (unbounded recursion)
- Session cost doubling every 10 minutes
- Agents generating output with no visible progress on actual code

**Phase to address:** Orchestrator intelligence phase — cost controls must be baked into orchestrator skills/prompts from day one, not added later

---

### Pitfall 3: Over-Parallelization with Missed Sequential Dependencies

**What goes wrong:**
The orchestrator incorrectly determines two tasks can run in parallel when one depends on the other's output (e.g., implementing a function before its interface contract is defined, or writing tests before the module structure is settled). Sub-agents proceed, produce incompatible work, and the integration phase requires throwing away one agent's output entirely. This is the multi-agent equivalent of a merge conflict at the architecture level — extremely costly.

**Why it happens:**
LLM-based task decomposition is optimistic about parallelism. The orchestrator may not have full visibility into implicit dependencies (naming conventions, shared types, database schema changes that affect multiple modules). Research shows specification failures and coordination breakdowns account for ~79% of multi-agent failures.

**How to avoid:**
- Define dependency chains explicitly in orchestrator skills: "Task B cannot start until Task A has committed its interface to state.json"
- Establish a "contracts-first" step at the start of any multi-agent session: orchestrator defines shared interfaces, types, and conventions before any sub-agent begins coding
- Require dependency declaration in task descriptions: every task must list "requires:" and "produces:" explicitly
- Use a "stub-then-implement" dependency strategy: generate interface stubs first (shared), then parallelize implementations

**Warning signs:**
- Two sub-agents both creating a new module with the same name
- Sub-agent A importing from a path that sub-agent B hasn't created yet
- TypeScript compilation errors after merging parallel agent outputs
- Orchestrator log shows tasks starting simultaneously that share the same files

**Phase to address:** Orchestrator skills phase — dependency modeling must be a first-class skill, not an afterthought

---

### Pitfall 4: Context Window Exhaustion Mid-Task with Silent State Loss

**What goes wrong:**
A sub-agent working on a complex task runs out of context window space mid-implementation. Auto-compaction kicks in and summarizes prior work — but the summary loses critical implementation details (specific edge cases handled, design decisions made, error patterns fixed). The agent continues but produces inconsistent code: the second half of the implementation contradicts the first half. The orchestrator sees "task completed" in state.json but the delivered code is subtly broken.

**Why it happens:**
Long-running coding tasks naturally accumulate large contexts: tool call results, file contents read, compilation errors iterated on, test output. Complex feature implementations can easily exceed 100K tokens. Compaction is lossy by design — it cannot preserve every detail.

**How to avoid:**
- Set explicit context budgets per task: break tasks that would require >50K tokens into subtasks
- Require sub-agents to write "progress notes" to `.memory/[agent-id].md` at regular intervals — durable checkpoints outside the context window
- Design tasks to be resumable: output artifacts should be self-describing so a fresh agent can pick up where the previous left off
- Monitor context utilization via ACP streaming and warn the orchestrator before compaction triggers

**Warning signs:**
- Sub-agent output quality degrades noticeably midway through a file
- Functions defined in one part of output contradict function signatures established earlier
- Sub-agent "forgets" constraints it acknowledged at task start
- Compaction events in ACP event stream for tasks that were supposed to be straightforward

**Phase to address:** Sub-agent runtime phase — checkpointing and task sizing must be designed before long-running tasks are supported

---

### Pitfall 5: Orchestrator Intelligence Drift — The LLM Forgetting Its Coordination Role

**What goes wrong:**
The orchestrator is itself an LLM (Claude Code with skills). Under certain conditions it starts behaving like a coding agent rather than a coordinator: it writes code directly, makes architectural decisions without delegating for review, or narrows focus on a single agent's thread while losing track of other agents. This is a variant of the "specification failure" category (42% of multi-agent failures per research). The orchestrator essentially defects from its coordination role.

**Why it happens:**
The orchestrator's skills and system prompt define its role, but LLMs are susceptible to context drift in long sessions. If early messages heavily feature code discussion, the model anchors on coding behavior. Skills/instructions that are far back in the context are deprioritized.

**How to avoid:**
- Structure orchestrator skills to repeatedly re-anchor on coordination responsibilities: "You are a coordinator. Do not write code. Your job is to assign, review, and unblock."
- Implement a periodic "role check" in orchestrator workflow: before every action, the orchestrator states its current coordination objective
- Keep the orchestrator's context lean: route sub-agent output summaries (not full outputs) to the orchestrator
- Define strict output format expectations for the orchestrator: its responses should be task assignments, reviews, or escalations — never raw code

**Warning signs:**
- Orchestrator output contains code blocks rather than task assignments
- Orchestrator stops updating state.json with delegation decisions
- Only one sub-agent is receiving new tasks while others are idle
- CLI shows orchestrator "thinking" for long periods without spawning agents or updating status

**Phase to address:** Orchestrator skills/prompts phase — role anchoring must be explicit from day one

---

### Pitfall 6: ACP Permission Prompt Deadlock — Agents Blocked Waiting for Responses

**What goes wrong:**
Sub-agents encounter tool-use permission prompts (file deletion, running scripts, network requests) and pause, waiting for the orchestrator to respond via ACP. The orchestrator is simultaneously waiting on other agents and doesn't process the blocked agent's prompt for minutes. The blocked agent times out, marks its task failed, and the orchestrator must decide whether to retry — potentially causing cascading retries. In `--auto` mode, if the orchestrator also encounters a permission prompt and pauses, the entire system can deadlock.

**Why it happens:**
ACP's bidirectional permission flow is powerful but requires the orchestrator to be always-responsive. A single-threaded or busy orchestrator naturally creates queues. Orchestrators that are themselves LLMs add LLM inference latency to every permission response.

**How to avoid:**
- Pre-authorize common tool classes at session start: define an explicit allowlist of operations each agent can perform without asking (e.g., "read any file, write to your designated output directory, run tests")
- Implement async permission processing: the orchestrator must have a separate fast-path for permission responses, not the same LLM inference loop as planning
- Set permission response timeouts: if no response in N seconds, apply a safe default (deny, and route to human if interactive mode)
- In `--auto` mode, grant broader pre-authorization to reduce prompt frequency

**Warning signs:**
- ACP event stream shows `permission_request` events not followed by `permission_response` within expected time
- Agent status stuck on "awaiting_permission" for >30 seconds
- Multiple agents simultaneously in "awaiting_permission" state
- System throughput drops to near zero despite all agents showing as "running"

**Phase to address:** ACP integration phase — permission flow design must be explicit, not assumed

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Direct file writes from sub-agents (no orchestrator mediation) | Simpler code, less latency | State corruption under any real concurrency | Never — architecture must enforce this from day one |
| Passing full conversation history to orchestrator | Orchestrator has full context | Context explosion, cost blowup, role drift | Never at scale — always summarize |
| Single state.json for all coordination | Simple mental model | Race conditions, no partial failure recovery | Prototype only, must be replaced before multi-agent parallelism |
| Polling state.json for status updates | Simple implementation | High I/O, stale reads, missed events | Acceptable in MVP if polling interval is reasonable (>1s) |
| Hardcoded max_agents limit | Prevents runaway costs | Inflexible for different task sizes | Acceptable if configurable per-session |
| Identical model for orchestrator and all sub-agents | Simpler deployment | Unnecessary cost — orchestrator needs expensive model, sub-agents don't | Never — tier models by role from day one |
| Using exceptions for all ACP error signaling | Simple error handling | Silent failures when ACP stream drops | Only if combined with dead-letter detection |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ACP stdio transport | Assuming stdio never drops or blocks; not handling SIGPIPE when sub-process exits | Wrap all stdio reads in timeout + EOF detection; treat sub-process death as task failure, not hang |
| ACP ndjson streaming | Buffering entire response before parsing; missing partial-line events | Parse line-by-line as events arrive; handle partial lines across buffer boundaries |
| Claude Code as ACP client | Assuming synchronous request-response semantics | ACP is async and event-driven; design around event handlers, not await patterns |
| `.conductor/state.json` | Reading the file directly in sub-agents without knowing if a write is in progress | Use a versioned read protocol: read + check version field; retry if version changed during read |
| `.memory/` shared folder | Multiple agents appending to same memory file | Each agent writes to its own keyed file; orchestrator merges on demand |
| `@zed-industries/claude-agent-acp` adapter | Assuming it handles all Claude Code tool types; not pinning version | Verify tool coverage for all tools sub-agents will use; pin adapter version in lockfile |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Broadcasting full sub-agent output to orchestrator | Works fine with 2 agents, slow with 6+ | Summarize sub-agent output before routing to orchestrator; only escalate key artifacts | >4 concurrent agents |
| Synchronous state.json reads on every tool call | Acceptable with 1-2 agents | Cache state with TTL; only re-read when event signals a write | >3 agents making frequent tool calls |
| Orchestrator re-planning entire task graph after any agent update | Fine when simple, catastrophic when complex | Implement incremental planning: only re-evaluate tasks affected by the completed task | Task graphs >10 nodes |
| Streaming full ACP events to web dashboard | Demo-friendly, overwhelming in production | Apply event filtering/aggregation at dashboard backend; only stream summary events by default | >3 active agents |
| Using a single ACP connection pool for all agents | Negligible difference at small scale | Per-agent connection isolation prevents one agent's backpressure blocking others | >5 concurrent agents with heavy tool use |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Trusting sub-agent output unconditionally as orchestrator input | Prompt injection: code in a file sub-agent read could instruct the orchestrator to take unauthorized actions | Treat all sub-agent output as untrusted data; never interpolate it directly into orchestrator system prompts |
| Granting all sub-agents identical tool permissions | A compromised or misbehaving agent can perform actions outside its scope (delete unrelated files, exfiltrate code) | Define per-role permission manifests: "frontend agent can only write to `src/` and read from `types/`" |
| Storing API keys in `.conductor/state.json` | State file is readable by all agents; a prompt-injected agent could exfiltrate it | Never store credentials in state; use environment variables or secrets manager |
| No audit log for agent actions | Cannot determine what an agent did during a runaway session | Log all tool calls with agent identity, timestamp, and parameters to append-only log before executing |
| Inter-agent message passthrough without sanitization | A malicious file on disk could inject instructions that cascade through multiple agents | Sanitize/quote all file content before including in inter-agent messages |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Raw ACP event streams shown in dashboard | Information overload; user cannot find signal in noise; 90% of events are tool call results with no user value | Layered visibility: collapsed status by default, expandable to detail, opt-in to raw stream |
| Identical visual treatment for all agents | User cannot determine which agent is doing critical work vs. background tasks | Hierarchy: orchestrator at top, sub-agents below with role labels; visual distinction by status |
| Notifying on every agent event | Alert fatigue; user learns to ignore notifications | Smart notifications: only escalation requests, task completions, errors, and explicit human-needed events |
| No progress indication during long LLM inference | User thinks system is hung | Show "thinking" state with elapsed time; if >30s, surface what the agent is currently attempting |
| Blocking the CLI while waiting for agent responses | User cannot cancel or inspect state during a long run | CLI always-responsive: separate input thread from agent monitoring; Ctrl+C should pause and offer options |
| Hiding error details in "Task failed" status | User cannot diagnose failures without digging through raw logs | Surface the last error message and the tool call that triggered it in the collapsed card view |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Multi-agent parallelism:** Often missing write coordination — verify that two agents can simultaneously complete tasks without corrupting state.json
- [ ] **Orchestrator role:** Often missing role anchoring under long sessions — verify orchestrator still makes delegation decisions (not code decisions) after 50+ turns
- [ ] **Cost controls:** Often missing velocity monitoring — verify that a runaway sub-agent triggers an alert before hitting a per-session budget limit
- [ ] **ACP permission flow:** Often missing timeout handling — verify that a permission prompt with no response eventually resolves (fails safely) rather than hanging
- [ ] **Session persistence:** Often missing mid-task resumability — verify that restarting the orchestrator mid-session restores sub-agent contexts and in-progress tasks
- [ ] **Context compaction:** Often missing post-compaction consistency — verify that sub-agent output quality is equivalent before and after a compaction event
- [ ] **Web dashboard:** Often missing error states — verify that a crashed sub-agent is visually distinguished from an idle one
- [ ] **`.memory/` folder:** Often missing write conflict prevention — verify that two agents writing to memory simultaneously doesn't corrupt entries
- [ ] **Dependency management:** Often missing implicit dependency detection — verify that the orchestrator rejects or serializes tasks that touch the same files

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| State.json corruption | MEDIUM | Detect via JSON parse failure; restore from last valid checkpoint (maintain rolling backups every N writes); replay any events since checkpoint |
| Runaway token cost | LOW-MEDIUM | Kill all sub-agents via process management; audit orchestrator log to determine which agent triggered proliferation; restart with tighter max_agents config |
| Over-parallelization merge conflict | HIGH | Identify canonical implementation via orchestrator review; assign a "merge agent" with both outputs as context to produce reconciled version; update contracts file |
| Context exhaustion mid-task | MEDIUM | Load latest progress notes from `.memory/[agent-id].md`; spawn fresh agent with notes as context + explicit instruction to continue from checkpoint |
| Orchestrator role drift | MEDIUM | Inject a correction message via CLI: "You are the orchestrator. Stop writing code. Review current agent statuses and issue your next delegation decision." |
| ACP deadlock | LOW | Identify blocked agents via status monitoring; send explicit permission responses via orchestrator API; implement watchdog that auto-resolves stale permission prompts |
| Prompt injection cascade | HIGH | Kill all agents immediately; review audit log for scope of injected instructions; manually verify all files touched after the injection point |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| State.json corruption | State management design (early infrastructure) | Integration test: two agents write concurrently 100 times; state must be valid and complete each time |
| Runaway token costs | Orchestrator intelligence / skills | Test: run orchestrator on complex task; verify agent count never exceeds configured max and cost alerts fire |
| Over-parallelization dependency misses | Orchestrator skills: task decomposition | Test: feed orchestrator a task with implicit sequential dependencies; verify it detects and serializes them |
| Context exhaustion mid-task | Sub-agent runtime design | Test: assign a task requiring >80K tokens; verify compaction event triggers a memory checkpoint |
| Orchestrator role drift | Orchestrator skills + prompting | Long-run test: 100-turn session; verify orchestrator's last 10 actions are all coordination (not coding) |
| ACP permission deadlock | ACP integration layer | Test: sub-agent issues permission request; block orchestrator; verify safe default applies after timeout |
| Verbose output UX overload | Web dashboard: layered visibility | UX test: dashboard with 6 active agents; verify collapsed view shows only status summaries |
| Prompt injection cross-agent | Security design phase | Test: inject malicious instruction in a file sub-agent reads; verify orchestrator does not execute it |
| Interface contract drift | Pre-coding contracts step in orchestrator workflow | Test: two sub-agents implement same interface; types must match without orchestrator correction |

---

## Sources

- [Multi-agent workflows often fail — GitHub Blog](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/) — MEDIUM confidence (official GitHub, practical guidance)
- [Why Do Multi-Agent LLM Systems Fail? — arXiv 2503.13657](https://arxiv.org/html/2503.13657v1) — HIGH confidence (peer-reviewed research, 150+ execution traces)
- [Claude Code Subagent Cost Explosion — AICosts.ai](https://www.aicosts.ai/blog/claude-code-subagent-cost-explosion-887k-tokens-minute-crisis) — MEDIUM confidence (real-world case study, single source)
- [Race condition: .claude.json corruption — GitHub Issue #28847](https://github.com/anthropics/claude-code/issues/28847) — HIGH confidence (official Anthropic repository issue)
- [Race condition: .claude.json corruption (Windows) — GitHub Issue #29036](https://github.com/anthropics/claude-code/issues/29036) — HIGH confidence (official Anthropic repository issue)
- [Multi-Agent Coordination Strategies — Galileo](https://galileo.ai/blog/multi-agent-coordination-strategies) — MEDIUM confidence (practitioner guidance, multiple sources agree)
- [Effective harnesses for long-running agents — Anthropic Engineering](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — HIGH confidence (official Anthropic)
- [Claude Code Sub-Agents: Parallel vs Sequential Patterns — ClaudeFast](https://claudefa.st/blog/guide/agents/sub-agent-best-practices) — MEDIUM confidence (community, aligns with official patterns)
- [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html) — HIGH confidence (OWASP official)
- [Prompt injection / cross-agent trust boundary attacks — arXiv 2506.23260](https://arxiv.org/html/2506.23260v1) — HIGH confidence (peer-reviewed)
- [Manage costs effectively — Claude Code official docs](https://code.claude.com/docs/en/costs) — HIGH confidence (official)
- [Agent Token Usage API issue — Claude Code GitHub #10388](https://github.com/anthropics/claude-code/issues/10388) — HIGH confidence (official repository)

---
*Pitfalls research for: multi-agent coding orchestration (Conductor)*
*Researched: 2026-03-10*
