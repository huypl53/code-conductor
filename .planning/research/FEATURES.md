# Feature Research

**Domain:** Multi-agent coding orchestration framework
**Researched:** 2026-03-10
**Confidence:** HIGH (primary sources: Claude Code official docs, GitHub projects, verified 2026 ecosystem surveys)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Orchestrator agent that breaks down work and delegates | Core premise — without this it's just a single agent | HIGH | Must plan, decompose, assign, and review. Claude Code + orchestration skills is Conductor's approach |
| Sub-agent spawning and management | Multi-agent means spawning and controlling agents | HIGH | ACP protocol is the integration layer; orchestrator spawns via ACP |
| Task list with status tracking | Users need to see what's being done | MEDIUM | Shared `.conductor/state.json` approach. Claude Code agent teams use shared task files with claiming + file locks |
| Per-agent role assignment | Agents need defined scope to avoid overlap | MEDIUM | Name, role, target, materials per agent. Prevents agents trampling each other's work |
| Dependency management (task ordering) | Parallel work on dependent code causes failures | HIGH | Must sequence tasks that share interfaces; parallel tasks that are independent |
| Conflict prevention for concurrent file edits | Two agents editing same file = merge conflict | MEDIUM | File ownership per agent; git worktree isolation (ccswarm, ComposioHQ approach) or orchestrator-enforced file locks |
| Human-in-the-loop intervention / escalation | Users must be able to redirect, cancel, inject guidance | MEDIUM | Interrupt running agents, provide feedback, redirect approach mid-stream |
| Session persistence across restarts | Long sessions die; work must survive | MEDIUM | Agent identities, task state, memory must persist to disk. Critical for long-running builds |
| CLI interface for orchestrator interaction | Minimum viable interface | LOW | Chat with orchestrator, see current agent status |
| Repo context inheritance | Agents must understand the project they're working in | LOW | Pick up CLAUDE.md, .claude/, project config naturally. Already how Claude Code works |
| Autonomous mode vs interactive mode | Different users want different control levels | LOW | `--auto` for hands-off; interactive for supervised. This is an established expectation (Claude Code has this) |
| Output coherence / integration review | Multiple agents produce fragments that must form a whole | HIGH | Orchestrator reviews and integrates sub-agent output before declaring work done |

### Differentiators (Competitive Advantage)

Features that set Conductor apart from generic frameworks and thin wrappers.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Orchestrator-as-ACP-client (answers sub-agent questions in real-time) | Sub-agents can ask questions and get answers mid-task rather than stalling or guessing | HIGH | Key architectural differentiator. ACP enables bidirectional flow. Claude Code agent teams use mailbox; Conductor uses orchestrator as the answering party |
| Web dashboard with layered visibility | Most tools dump raw logs; layered view (summary -> detail -> live stream) solves the verbosity problem | HIGH | No existing tool does this well. ccswarm has terminal UI. ComposioHQ has PR-based status. Neither has spatial multi-agent visibility |
| Dynamic team sizing based on work scope | Orchestrator decides how many agents to spawn based on complexity, not user configuration | MEDIUM | Most tools require explicit agent count. Automatic scaling based on task breakdown is genuinely novel |
| Orchestrator decides GSD scope per sub-agent | Simple tasks execute directly; complex tasks get full planning. Avoids overhead on simple work | MEDIUM | CrewAI and LangGraph apply same process to all tasks. Per-task scope flexibility reduces wasted tokens |
| Orchestrator mediates all sub-agent coordination | No peer-to-peer agent chaos; single coordination model | MEDIUM | Claude Code agent teams allow direct peer messaging (which creates complex failure modes). Conductor routes through orchestrator |
| Shared `.memory/` for cross-agent knowledge | Agents accumulate team knowledge that persists across tasks and restarts | MEDIUM | LangGraph and AutoGen have per-agent or per-session memory. Shared persistent memory across the team is underexplored |
| ACP all the way down (human <-> orchestrator <-> sub-agents same protocol) | Uniform protocol at every layer; real-time tool call visibility at each layer | HIGH | Most tools use different protocols for user interface vs agent coordination. Uniform ACP means same observability primitives throughout |
| Quality review loop (orchestrator reviews and gives feedback) | Work is reviewed before being marked complete, not just executed | MEDIUM | CrewAI has review step in hierarchical mode. Most frameworks just collect outputs. Conductor explicitly loops on quality |
| Multi-level intervention (cancel, reassign, inject mid-stream, pause/escalate) | Fine-grained control beyond stop/start | MEDIUM | AutoGen Studio has mid-execution pause. Most tools offer coarser control. Full intervention vocabulary is a meaningful DX differentiator |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for the Conductor use case specifically.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Direct agent-to-agent peer messaging | "Agents should collaborate like humans" | Creates coordination chaos — race conditions, deadlocks, loops with no coordinator to resolve them. AutoGen peer-to-peer debugging is notoriously hard | Orchestrator-mediated messaging with mailbox model. All coordination goes through one party |
| Custom LLM provider support (non-ACP) | Flexibility / cost optimization | Massively increases complexity. Each provider has different capabilities, auth models, tool schemas, streaming behaviors. V1 scope explosion | ACP-compatible agents only. When ACP is more widely adopted, adding providers is straightforward |
| Per-agent billing / usage dashboards | "I want to know how much each agent costs" | Billing logic varies by provider, changes frequently, and creates vendor coupling. Adds a full accounting subsystem | Rely on underlying providers (Anthropic Console, etc.). Not Conductor's responsibility |
| Multi-user / team collaboration | "Multiple engineers using same orchestrator" | Requires auth, access control, conflict resolution between humans, websocket multiplexing. Entire new product surface | Single user + session handoff patterns. V2 feature once core is proven |
| Mobile app | "I want to monitor agents from my phone" | High build cost for low-value use case. Agents run to completion or need real intervention — neither warrants mobile-first | Responsive web dashboard covers emergency monitoring |
| Unlimited parallel agent scaling | "Spin up 50 agents at once" | Token costs scale linearly. Coordination overhead rises super-linearly. Beyond 5-10 agents, diminishing returns dominate (Claude Code docs: start with 3-5 teammates) | Dynamic scaling that caps based on task graph, not user ambition |
| Raw conversation log streaming as primary UI | "I want to see everything" | Information overload is the #1 UX problem of multi-agent tools (identified in PROJECT.md). Raw logs are not useful for intervention | Layered visibility: summary by default, expandable to detail, stream available on demand |
| General-purpose agent framework (not coding-specific) | "Make it work for customer support, research, etc." | Loses the coding-specific advantages: repo context inheritance, git integration, CI hooks, code review loops | Stay focused on coding. Domain specificity is a feature, not a constraint |

---

## Feature Dependencies

```
[Orchestrator agent]
    └──requires──> [ACP client/server runtime]
                       └──requires──> [Sub-agent spawning via ACP]

[Sub-agent spawning via ACP]
    └──requires──> [Agent identity system (name, role, target, materials)]
    └──requires──> [Shared state file (.conductor/state.json)]

[Shared state file]
    └──requires──> [Task list with status tracking]
    └──enables──>  [Dependency management (task ordering)]
    └──enables──>  [Conflict prevention for concurrent edits]

[Session persistence]
    └──requires──> [Shared state file]
    └──requires──> [Shared .memory/ folder]

[Web dashboard]
    └──requires──> [Shared state file] (reads task/agent status)
    └──requires──> [ACP streaming] (live tool call visibility)
    └──enhances──> [Human-in-the-loop intervention]

[Orchestrator-as-ACP-client (answering sub-agent questions)]
    └──requires──> [ACP bidirectional protocol]
    └──requires──> [Human escalation logic]

[Dynamic team sizing]
    └──requires──> [Orchestrator agent] (must plan before sizing)
    └──requires──> [Task breakdown / dependency management]

[Output coherence / integration review]
    └──requires──> [Task list with status tracking] (knows when tasks complete)
    └──requires──> [Orchestrator agent] (reviews output)

[Multi-level intervention]
    └──requires──> [ACP streaming] (must see what's happening to intervene)
    └──enhances──> [Human-in-the-loop intervention]
```

### Dependency Notes

- **Web dashboard requires ACP streaming:** The dashboard gets its live data from ACP tool call events — without streaming, it can only show stale state, not live activity.
- **Dynamic team sizing requires task breakdown first:** The orchestrator cannot decide team size before understanding the work. Breakdown precedes scaling.
- **Session persistence requires both state file and memory folder:** State file holds task/agent metadata; memory folder holds accumulated knowledge. Both must survive restarts for true persistence.
- **Orchestrator answering questions requires human escalation logic:** In `--auto` mode, orchestrator answers sub-agent questions using best judgment. In interactive mode, it escalates to human. The same mechanism handles both.
- **Conflict prevention conflicts with agent-to-agent peer messaging:** If agents coordinate directly, the orchestrator loses the ability to enforce file ownership and task boundaries. These are fundamentally incompatible approaches.

---

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to prove the concept works end-to-end.

- [ ] Orchestrator agent (Claude Code + orchestration skills) — without this, nothing else is possible
- [ ] ACP client/server runtime — protocol layer for spawning and managing sub-agents
- [ ] Agent identity system (name, role, target, materials) — agents need defined scope
- [ ] Shared state file (`.conductor/state.json`) — coordination backbone
- [ ] Task list with status tracking — orchestrator and agents need shared task view
- [ ] Dependency management (sequence vs parallel decisions) — parallel work without this breaks
- [ ] Conflict prevention for concurrent file edits — required for parallel correctness
- [ ] Orchestrator-as-ACP-client (answers sub-agent questions) — differentiator that prevents agent stalling
- [ ] `--auto` mode + interactive mode — covers the two primary user scenarios
- [ ] Session persistence (state + memory) — long sessions need to survive restarts
- [ ] CLI interface — minimum viable user interface
- [ ] Web dashboard v1 (layered visibility: summary, expandable, live stream) — multi-agent visibility requires more than CLI; this is a core product promise

### Add After Validation (v1.x)

Features to add once core workflow is proven working.

- [ ] Dynamic team sizing — add when base orchestration is stable; requires tuning orchestrator judgment
- [ ] Smart notifications (completions, errors, intervention needed) — add to dashboard once base visibility works
- [ ] Per-task GSD scope flexibility — add when orchestrator skill set is mature enough to judge correctly
- [ ] Quality review loops with feedback — add when basic delegation works; refine the "done" definition
- [ ] Multi-level intervention (cancel, reassign, inject mid-stream) — add after users report needing finer control

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Multi-user / team collaboration — defer; requires auth, access control, significant new surface
- [ ] Additional ACP-compatible agent types beyond Claude Code / Codex — defer; ACP ecosystem needs to mature
- [ ] Plugin/extension system — defer; wait until usage patterns reveal what extensions are actually needed
- [ ] CI integration (auto-fix failing builds) — powerful but complex; ComposioHQ does this; defer until core is solid
- [ ] Git worktree isolation per agent — useful for large parallel work; adds complexity; evaluate after v1 usage data

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Orchestrator agent (planning + delegation) | HIGH | HIGH | P1 |
| ACP client/server runtime | HIGH | HIGH | P1 |
| Agent identity system | HIGH | LOW | P1 |
| Shared state file | HIGH | LOW | P1 |
| Task list with status tracking | HIGH | LOW | P1 |
| Dependency management | HIGH | MEDIUM | P1 |
| Conflict prevention for concurrent edits | HIGH | MEDIUM | P1 |
| Orchestrator answers sub-agent questions | HIGH | MEDIUM | P1 |
| Session persistence | HIGH | MEDIUM | P1 |
| CLI interface | HIGH | LOW | P1 |
| `--auto` vs interactive mode | HIGH | LOW | P1 |
| Web dashboard (layered visibility) | HIGH | HIGH | P1 |
| Output coherence / integration review | HIGH | MEDIUM | P1 |
| Dynamic team sizing | MEDIUM | MEDIUM | P2 |
| Smart notifications | MEDIUM | MEDIUM | P2 |
| Per-task GSD scope flexibility | MEDIUM | MEDIUM | P2 |
| Multi-level intervention (full vocabulary) | MEDIUM | MEDIUM | P2 |
| Quality review loops with feedback | MEDIUM | HIGH | P2 |
| CI integration | MEDIUM | HIGH | P3 |
| Git worktree isolation per agent | MEDIUM | HIGH | P3 |
| Multi-user collaboration | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch — the product doesn't work without these
- P2: Should have — adds significant value; add when P1 is stable
- P3: Nice to have — defer until PMF is established

---

## Competitor Feature Analysis

| Feature | CrewAI | AutoGen / AutoGen Studio | LangGraph | ccswarm | ComposioHQ orchestrator | Claude Code agent teams | Conductor (planned) |
|---------|--------|--------------------------|-----------|---------|------------------------|------------------------|---------------------|
| Orchestrator-as-coordinator | Yes (hierarchical process) | Yes (GroupChat manager) | Yes (supervisor node) | Yes (master agent) | Yes | Yes (team lead) | Yes |
| Task list / shared state | Via Crews task system | Via message passing | Via StateGraph | Via file-based task tracking | Via issue tracker integration | Shared task list + file locking | `.conductor/state.json` |
| Dependency management | Sequential/parallel flows | Message order | Graph edges | Basic | Basic | Task dependencies with blocking | Orchestrator-judged |
| Conflict prevention | Not explicit | Not explicit | Not explicit | Git worktree isolation | Git worktree + branch per agent | "Avoid same-file edits" (best practice, not enforced) | Orchestrator-enforced file ownership |
| Sub-agent questions / escalation | Not supported | UserProxy can be in loop | Not built-in | Not supported | Not supported | Teammate mailbox | Orchestrator answers via ACP |
| Human intervention | Task-level | Mid-execution pause (Studio) | Not built-in | Terminal UI | Manual PR review | Direct teammate messaging | Multi-level: cancel, reassign, inject, pause/escalate |
| Session persistence | Via memory system | Via SQLite checkpointing | Via checkpointer | 93% token reduction via conversation persistence | Via PR-based state | No (known limitation) | Full: state + memory + agent identities |
| Dashboard / UI | Cloud platform only | AutoGen Studio (local web) | LangGraph Studio (cloud) | Terminal UI | PR-based status | Terminal (split-pane or in-process) | Web dashboard with layered visibility |
| Protocol | Custom | Custom message bus | Custom StateGraph | PTY/native | Agent-agnostic (tmux/Docker) | Claude-specific | ACP throughout |
| Coding-domain specificity | Generic | Generic | Generic | Yes (specialized pools: frontend/backend/devops/QA) | Yes (CI, PRs, code review) | Yes | Yes |
| Dynamic team sizing | No (defined in config) | No | No | No | No | Claude decides (experimental) | Orchestrator decides |
| Open source | Yes | Yes | Yes | Yes | Yes | No (built into Claude Code) | Yes |

---

## Sources

- [Claude Code Agent Teams — Official Docs](https://code.claude.com/docs/en/agent-teams) — HIGH confidence, official Anthropic documentation
- [CrewAI Documentation — Introduction](https://docs.crewai.com/en/introduction) — HIGH confidence, official docs
- [AutoGen GitHub](https://github.com/microsoft/autogen) — HIGH confidence, official Microsoft repo
- [LangGraph — LangChain](https://www.langchain.com/langgraph) — HIGH confidence, official LangChain product page
- [OpenAI Swarm GitHub](https://github.com/openai/swarm) — HIGH confidence, official OpenAI repo (now superseded by Agents SDK)
- [ccswarm — GitHub](https://github.com/nwiizo/ccswarm) — MEDIUM confidence, active OSS project with detailed README
- [ComposioHQ agent-orchestrator](https://github.com/ComposioHQ/agent-orchestrator) — MEDIUM confidence, active OSS project
- [zed-industries/claude-agent-acp](https://github.com/zed-industries/claude-agent-acp) — HIGH confidence, the ACP adapter referenced in PROJECT.md
- [Conductors to Orchestrators — O'Reilly Radar](https://www.oreilly.com/radar/conductors-to-orchestrators-the-future-of-agentic-coding/) — MEDIUM confidence, industry analysis
- [LangGraph vs CrewAI vs AutoGen — DEV Community 2026](https://dev.to/pockit_tools/langgraph-vs-crewai-vs-autogen-the-complete-multi-agent-ai-orchestration-guide-for-2026-2d63) — MEDIUM confidence, comparative analysis
- [AI Coding Agents 2026: Coherence Through Orchestration — Mike Mason](https://mikemason.ca/writing/ai-coding-agents-jan-2026/) — MEDIUM confidence, practitioner perspective
- [AI Agent Anti-Patterns — Medium 2026](https://achan2013.medium.com/ai-agent-anti-patterns-part-1-architectural-pitfalls-that-break-enterprise-agents-before-they-32d211dded43) — MEDIUM confidence, engineering experience post
- [Multi-Agent Orchestration: Running 10+ Claude Instances in Parallel — DEV Community](https://dev.to/bredmond1019/multi-agent-orchestration-running-10-claude-instances-in-parallel-part-3-29da) — MEDIUM confidence, practitioner post
- [Human-In-The-Loop Software Development Agents — arXiv 2025](https://arxiv.org/abs/2411.12924) — HIGH confidence, peer-reviewed research
- [Simon Willison — Agentic Engineering Patterns: Anti-patterns](https://simonwillison.net/guides/agentic-engineering-patterns/anti-patterns/) — HIGH confidence, authoritative practitioner

---
*Feature research for: multi-agent coding orchestration (Conductor)*
*Researched: 2026-03-10*
