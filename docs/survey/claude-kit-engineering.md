# ClaudeKit Engineer: Architecture and Design Pattern Survey

**Date**: 2026-03-11
**Source**: `/home/huypham/code/tools/claude/.claude/` (claudekit-engineer v1.0.1)
**Repository**: https://github.com/truongtv22/claudekit-engineer.git
**Purpose**: Inform improvements to the Conductor AI agent orchestrator project

---

## 1. Overview

ClaudeKit Engineer is a comprehensive boilerplate/template for configuring Claude Code as a multi-agent software engineering system. It transforms a general-purpose LLM into a structured, role-specialized development team through a layered architecture of:

- **16 agent definitions** (specialized roles)
- **32+ skill modules** (domain knowledge packs)
- **50+ slash commands** (user-facing CLI entry points)
- **4 workflow documents** (process protocols)
- **5 hook scripts** (automated guardrails and notifications)
- **3 statusline scripts** (real-time session dashboard)
- **1 settings.json** (runtime configuration binding it all together)

The key insight: this is not a traditional code framework but a **prompt engineering architecture** -- a system of markdown files, JSON configs, and helper scripts that shapes LLM behavior through structured context injection.

---

## 2. Directory Structure

```
.claude/
├── settings.json              # Runtime config: hooks, statusline, co-author toggle
├── metadata.json              # Kit metadata: version, name, repo URL
├── .env.example               # API keys template (Discord, Telegram, Gemini)
├── .mcp.json.example          # MCP server config template
├── .gitignore
│
├── agents/                    # 16 role-specialized agent definitions (.md)
│   ├── planner.md
│   ├── researcher.md
│   ├── code-reviewer.md
│   ├── tester.md
│   ├── debugger.md
│   ├── scout.md / scout-external.md
│   ├── project-manager.md
│   ├── git-manager.md
│   ├── docs-manager.md
│   ├── brainstormer.md
│   ├── copywriter.md
│   ├── database-admin.md
│   ├── ui-ux-designer.md
│   ├── journal-writer.md
│   └── mcp-manager.md
│
├── commands/                  # 50+ slash commands organized in subdirectories
│   ├── plan.md / plan/fast.md / plan/hard.md / plan/two.md / plan/ci.md / plan/cro.md
│   ├── code.md
│   ├── cook.md / cook/auto.md / cook/auto/fast.md
│   ├── fix.md / fix/fast.md / fix/hard.md / fix/test.md / fix/ci.md / ...
│   ├── bootstrap.md / bootstrap/auto.md / bootstrap/auto/fast.md
│   ├── scout.md / scout/ext.md
│   ├── git/cm.md / git/cp.md / git/pr.md
│   ├── design/ / content/ / docs/ / review/ / skill/ / integrate/
│   └── ...
│
├── skills/                    # 32+ skill modules
│   ├── planning/              # Implementation planning framework
│   ├── research/              # Multi-source research methodology
│   ├── debugging/             # Four-phase debugging framework
│   ├── sequential-thinking/   # Structured reasoning process
│   ├── problem-solving/       # Stuck-ness resolution techniques
│   ├── code-review/           # Review protocol with verification gates
│   ├── ai-multimodal/         # Gemini-based media processing
│   ├── docs-seeker/           # Documentation discovery via llms.txt
│   ├── mcp-management/        # MCP server integration
│   ├── repomix/               # Repository packaging for AI context
│   ├── aesthetic/             # UI design principles and workflows
│   ├── devops/                # Docker, Cloudflare, GCloud
│   ├── skill-creator/         # Meta-skill for creating new skills
│   ├── template-skill/        # Bare skeleton for new skills
│   ├── google-adk-python/     # Google Agent Development Kit reference
│   └── ... (frontend, backend, databases, shopify, etc.)
│
├── hooks/                     # Automated guardrails and notifications
│   ├── scout-block.js/.sh/.ps1  # PreToolUse: blocks access to heavy dirs
│   ├── modularization-hook.js   # PostToolUse: suggests splitting large files
│   ├── discord_notify.sh        # Stop/SubagentStop: Discord notifications
│   ├── telegram_notify.sh       # Stop/SubagentStop: Telegram notifications
│   └── send-discord.sh          # Manual Discord notification
│
├── workflows/                 # Process orchestration documents
│   ├── primary-workflow.md           # Main dev lifecycle
│   ├── orchestration-protocol.md     # Sequential chaining vs parallel execution
│   ├── development-rules.md          # Coding standards and principles
│   └── documentation-management.md   # Doc update triggers and protocol
│
├── statusline.js              # Node.js statusline (primary)
├── statusline.sh              # Bash fallback
└── statusline.ps1             # PowerShell fallback
```

---

## 3. How the Components Relate

### 3.1 The Activation Chain

```
User input (or slash command)
    │
    ▼
settings.json ── hooks fire (PreToolUse/PostToolUse)
    │
    ▼
Command .md ── defines workflow template with $ARGUMENTS
    │
    ▼
Workflow .md ── establishes orchestration rules
    │
    ▼
Agent .md(s) ── spawned via Task tool as subagents
    │
    ▼
Skill SKILL.md(s) ── loaded dynamically when agent needs domain knowledge
    │
    ▼
Skill references/ & scripts/ ── loaded on demand (progressive disclosure)
```

### 3.2 Relationship Model

| Component | Role | Loaded When | Consumes |
|-----------|------|-------------|----------|
| **settings.json** | Runtime binding | Always | Hooks, statusline config |
| **Workflows** | Process rules (included in CLAUDE.md) | Session start | -- |
| **Commands** | User entry points (slash commands) | User invokes `/command` | Agents, Skills, other Commands |
| **Agents** | Specialized roles (via `Task` tool) | Delegated by command or agent | Skills, other Agents |
| **Skills** | Domain knowledge packs | Agent determines relevance | References, Scripts, Assets |
| **Hooks** | Automated guardrails | Tool events (pre/post) | stdin JSON from Claude Code |
| **Statusline** | Session dashboard | Every prompt cycle | stdin JSON, `ccusage`, `git` |

### 3.3 Agent-to-Agent Delegation Graph

The primary orchestration pattern is a **hub-and-spoke** model where the main agent (or a command) delegates to specialist subagents:

```
Main Agent (or /code, /cook, /bootstrap command)
    ├── planner ─── researcher (parallel, haiku model)
    ├── tester (sonnet)
    ├── debugger (sonnet)
    ├── code-reviewer (sonnet)
    ├── project-manager (haiku)
    ├── docs-manager (sonnet)
    ├── git-manager (haiku)
    ├── scout ─── Explore subagents (parallel)
    ├── scout-external ─── gemini/opencode CLI (parallel)
    ├── ui-ux-designer ─── researcher (parallel)
    ├── brainstormer
    ├── mcp-manager
    ├── journal-writer
    └── copywriter
```

---

## 4. Key Design Patterns

### 4.1 Progressive Disclosure (Context Engineering)

The most important architectural pattern. Skills use a three-tier loading system:

1. **Metadata** (name + description in YAML frontmatter): always in context, ~100 words
2. **SKILL.md body**: loaded when skill triggers, kept under 100 lines / 5k words
3. **Bundled resources** (references/, scripts/): loaded only when Claude determines they are needed

This means a skill like `debugging` advertises itself with a rich description, but the detailed four-phase process, root-cause tracing techniques, and verification protocols are only loaded when actually needed. This directly addresses the fundamental LLM constraint: finite context windows.

**Enforced by**: The `skill-creator` skill explicitly mandates SKILL.md under 100 lines, reference files under 100 lines each, and progressive splitting into multiple files.

### 4.2 Hierarchical Agent Specialization with Model Selection

Each agent has explicit YAML frontmatter controlling:
- **name**: identity for delegation
- **description**: rich, example-laden text that teaches the Task tool *when* to use this agent
- **model**: deliberate model selection for cost optimization
- **tools**: optional tool restriction (e.g., scout gets only search tools)

Model selection strategy:
- **haiku** for cheap, fast tasks: researcher, scout, project-manager, git-manager, mcp-manager
- **sonnet** for quality-critical tasks: code-reviewer, tester, debugger, docs-manager, copywriter
- **inherit** (parent model): ui-ux-designer (needs the best available)

This is a manual cost-optimization layer. The git-manager agent explicitly documents the math: delegating diff analysis to Gemini Flash instead of Haiku saves 81% cost per commit.

### 4.3 Command Variants (Complexity Tiers)

Commands use directory nesting to provide complexity variants:

```
/plan        → auto-detects complexity, routes to fast or hard
/plan:fast   → no research, just analyze and plan
/plan:hard   → research + analyze + plan
/plan:two    → (variant)

/fix         → auto-detects, routes to fast or hard
/fix:fast    → quick analysis + fix
/fix:hard    → deep debugging + fix

/bootstrap        → full step-by-step project creation
/bootstrap:auto   → automated variant
/bootstrap:auto:fast → fastest automated bootstrap
```

The parent command acts as a **router** that inspects task complexity and delegates to the appropriate variant. This gives users a simple default (`/plan`) while preserving access to specific behaviors.

### 4.4 File-Based Inter-Agent Communication

Agents communicate through the filesystem:
- **Plans directory**: `plans/YYYYMMDD-HHmm-plan-name/`
- **Reports**: `plans/<plan-name>/reports/YYMMDD-from-agent-name-to-agent-name-task-name-report.md`
- **Research**: `plans/<plan-name>/research/researcher-XX-report.md`
- **Scout reports**: `plans/<plan-name>/scout/scout-XX-report.md`

This is a pragmatic choice: since agents are separate Claude instances that cannot share memory, the filesystem serves as a persistent, inspectable message bus.

### 4.5 Hook-Based Guardrails (Pre/Post Tool Use)

The hooks system provides automated quality enforcement:

| Hook | Event | Behavior |
|------|-------|----------|
| **scout-block.js** | PreToolUse (Bash) | **Blocking**: prevents access to node_modules, .git, __pycache__, dist, build |
| **modularization-hook.js** | PostToolUse (Write\|Edit) | **Non-blocking**: suggests splitting files > 200 LOC |

The scout-block hook is a cross-platform dispatcher (Node.js) that delegates to platform-specific scripts (bash or PowerShell). It reads the hook payload from stdin, validates JSON, and exits with code 2 to block prohibited commands.

The modularization hook uses the `continue: true` + `additionalContext` pattern to inject suggestions without halting execution.

### 4.6 Cost-Conscious Token Engineering

A recurring theme throughout the kit:

1. Every agent and skill file includes: "Ensure token efficiency while maintaining high quality"
2. Reports sacrifice grammar for concision
3. Research is capped at max 5 tool calls
4. Research reports capped at 150 lines
5. Plan overview files capped at 80 lines
6. SKILL.md files capped at 100 lines
7. Git-manager delegates to Gemini Flash for diff analysis (13x cheaper than Haiku for that task)
8. Scout agents have 3-minute timeouts; failed scouts are skipped, not retried
9. The statusline integrates `ccusage` to display real-time cost and token consumption

### 4.7 External Tool Delegation (Gemini/OpenCode)

The kit treats external AI CLIs (Gemini CLI, OpenCode) as first-class tools:
- **scout-external** agent spawns `gemini` or `opencode` CLI processes for parallel codebase search
- **git-manager** delegates commit message generation to Gemini Flash
- **mcp-manager** uses Gemini CLI as primary execution method for MCP tools
- **researcher** can use `gemini` for web research

This is a novel pattern: using multiple AI providers as specialized workers orchestrated by the main Claude instance.

### 4.8 Verification Gates

The code-review skill defines strict verification protocols:
- **Iron Law**: "NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE"
- IDENTIFY command, RUN command, READ output, VERIFY confirms claim, THEN claim
- Red flags: using "should"/"probably"/"seems to" without evidence

This prevents a common LLM failure mode: claiming success without actually running verification.

---

## 5. Notable Implementation Details

### 5.1 Statusline Architecture

The statusline (`statusline.js`) is a Node.js script that:
- Reads JSON data from stdin (workspace, model info)
- Detects git branch via `execSync`
- Integrates with `ccusage` (npm package) to show cost, burn rate, token count, and session time remaining
- Uses color-coded indicators (green > yellow > red based on remaining session percentage)
- Displays: directory, git branch, model name/version, session time, cost per hour, total tokens

### 5.2 Cross-Platform Design

The kit explicitly targets Windows, macOS, and Linux:
- Hooks use Node.js as the universal dispatcher, delegating to bash or PowerShell
- Scripts prefer Node.js or Python over bash for Windows compatibility
- The `.env` loading chain is consistent: `process.env > skill/.env > skills/.env > .claude/.env`

### 5.3 Agent Description Engineering

Agent descriptions are heavily optimized for Claude's Task tool dispatch mechanism. They include:
- Detailed usage scenarios in XML-like `<example>` blocks
- Explicit `<commentary>` explaining *why* the agent should be selected
- Multiple contrasting examples to define boundaries
- Proactive trigger conditions ("use this agent when...")

This is essentially prompt engineering for the router -- the descriptions teach the main agent's Task tool when to delegate.

### 5.4 The Journal Writer Pattern

The `journal-writer` agent is uniquely positioned: it documents failures with emotional authenticity. It triggers on repeated test failures, production bugs, failed migrations, etc. The output includes a "The Brutal Truth" section expressing genuine frustration. This serves as:
- A learning record for the team
- A form of rubber-duck debugging
- An honest counterweight to the LLM tendency to be optimistic

### 5.5 MCP Management Strategy

MCP (Model Context Protocol) integration follows a three-tier fallback:
1. **Gemini CLI** (primary): fastest, auto-discovers tools via `.mcp.json`
2. **Direct Scripts** (secondary): `npx tsx cli.ts call-tool <server> <tool>`
3. **mcp-manager Subagent** (tertiary): delegates to subagent to keep main context clean

A `GEMINI.md` file in the project root enforces structured JSON responses from Gemini CLI, making output parseable.

---

## 6. Strengths of This Approach

### 6.1 Modular and Extensible
Adding a new agent is one markdown file. Adding a new skill is one directory with a SKILL.md. The system is designed for incremental growth without restructuring.

### 6.2 Progressive Disclosure is Genuine Context Engineering
The three-tier loading system for skills (metadata -> body -> references) is one of the most sophisticated approaches to managing LLM context budgets. It allows the system to maintain awareness of 32+ skills while only paying the context cost for those actually needed.

### 6.3 Cost Optimization is First-Class
The deliberate model selection per agent (haiku for cheap tasks, sonnet for critical ones), the token budgets, the delegation to Gemini Flash -- this shows real production thinking about API costs.

### 6.4 Practical Guardrails
The hook system (blocking heavy directories, suggesting modularization) catches real problems without requiring user discipline. These are automated quality gates.

### 6.5 Rich Orchestration Vocabulary
The kit defines clear patterns: sequential chaining, parallel execution, file-based inter-agent communication, verification gates, complexity-tiered commands. This gives the LLM a structured vocabulary for organizing work.

### 6.6 Self-Documenting
The skill-creator skill and template-skill create a meta-system: the kit can extend itself by teaching Claude how to create new skills following its own conventions.

---

## 7. Limitations

### 7.1 No Dynamic Agent Discovery
Agents are hardcoded by name in workflow and command files. There is no registry or dynamic discovery mechanism. Adding a new agent requires manually updating every workflow that should use it.

### 7.2 No State Machine or Execution Tracking
The orchestration is entirely prompt-driven. There is no formal state machine tracking which phase of a workflow is active, no persistent execution state, no resume capability beyond what the LLM can reconstruct from filesystem artifacts.

### 7.3 Fragile Inter-Agent Communication
File-based communication (markdown reports in `plans/` directories) works but is fragile:
- No schema validation for reports
- No guaranteed delivery (agent might not write the report)
- No structured data exchange format (everything is markdown prose)
- Naming conventions are enforced only by agent instructions, not by code

### 7.4 No Real Feedback Loops
The "repeat until all tests pass" pattern relies entirely on the LLM faithfully implementing a loop. There is no programmatic retry mechanism, no circuit breaker, no max-retry limit enforced by infrastructure.

### 7.5 Duplication Across Commands
Many commands (bootstrap, cook, code) contain nearly identical workflow sections (research, plan, implement, test, review, document). This violates DRY -- changes to the testing protocol must be made in multiple command files.

### 7.6 No Observability Beyond Notifications
Hooks support Discord/Telegram notifications for session completion, but there is no structured logging, no execution trace, no way to replay or audit what happened during a complex multi-agent workflow.

### 7.7 Prompt Brittleness
The entire system depends on the LLM correctly following markdown instructions. There is no enforcement layer for most protocols -- if the LLM ignores a "IMPORTANT: do not implement" directive, there is no hard stop.

### 7.8 No Dependency Management Between Skills
Skills reference each other by name in prose ("use `docs-seeker` skill"), but there is no formal dependency graph. Loading one skill does not automatically ensure its dependencies are available.

---

## 8. Ideas and Patterns for the Conductor Project

### 8.1 Adopt Progressive Disclosure for Agent Capabilities

**Pattern**: Three-tier capability loading -- metadata always available, detailed instructions loaded on activation, reference materials loaded on demand.

**For Conductor**: The decomposer and orchestrator could maintain a lightweight capability registry (name + description) for all available agents, loading full agent prompts only when dispatching. This would allow scaling to many more agent types without bloating the orchestrator's context.

### 8.2 Implement Verification Gates as Infrastructure

**Pattern**: The code-review skill's "Iron Law" (no claims without evidence) is powerful but enforced only through prompts.

**For Conductor**: Implement verification gates as actual code checkpoints in the orchestrator pipeline. Before marking a task complete, require the agent's output to include structured evidence (test output, build status) that the orchestrator can programmatically validate.

### 8.3 Model Selection Per Task Type

**Pattern**: Cheap models (Haiku) for research/search/management, expensive models (Sonnet) for code review/debugging/writing.

**For Conductor**: The orchestrator could maintain a model routing table mapping task types to optimal models. The decomposer could annotate each sub-task with a recommended model tier (fast/cheap, balanced, quality/expensive).

### 8.4 Command Variant Routing (Complexity Tiers)

**Pattern**: `/plan` auto-detects complexity and routes to `/plan:fast` or `/plan:hard`.

**For Conductor**: Implement a complexity estimator in the decomposer that classifies tasks into tiers. Each tier gets a different orchestration strategy (simple tasks skip research/planning phases, complex tasks get full pipeline).

### 8.5 File-Based Agent Communication with Schema

**Pattern**: ClaudeKit uses filesystem as a message bus but with no schema enforcement.

**For Conductor**: Adopt the file-based pattern but add structured schemas (JSON or YAML) for inter-agent messages. The orchestrator validates message format before passing to the next agent. This gives both inspectability (files on disk) and reliability (schema validation).

### 8.6 Automated Guardrail Hooks

**Pattern**: PreToolUse hooks block dangerous operations; PostToolUse hooks inject quality suggestions.

**For Conductor**: Implement a hook system that:
- **Pre-execution**: validates the agent's proposed action against safety rules
- **Post-execution**: checks output quality (file size limits, test pass rates, etc.)
- **Non-blocking suggestions**: inject additional context without stopping the pipeline

### 8.7 Cost Tracking and Budget Controls

**Pattern**: The statusline shows real-time cost and burn rate; agents are instructed to be token-efficient.

**For Conductor**: Add cost tracking per sub-task and per agent. Implement budget limits that the orchestrator enforces -- if a sub-task exceeds its token budget, escalate to the user rather than allowing unbounded spending.

### 8.8 External AI Delegation

**Pattern**: ClaudeKit delegates specific tasks to Gemini CLI or OpenCode for cost savings.

**For Conductor**: Implement a provider router that can dispatch sub-tasks to different AI providers based on task type and cost constraints. Research tasks to a cheap fast model, code generation to a capable one, commit messages to the cheapest available.

### 8.9 Rich Agent Descriptions with Dispatch Examples

**Pattern**: Agent descriptions include XML-style examples with commentary that teach the router when to select each agent.

**For Conductor**: When defining agent capabilities for the orchestrator, include concrete dispatch examples. These serve as few-shot examples that improve the orchestrator's routing accuracy.

### 8.10 Structured Plan Directory Convention

**Pattern**: `plans/YYYYMMDD-HHmm-plan-name/` with `plan.md`, `phase-XX-*.md`, `reports/`, `research/`, `scout/`.

**For Conductor**: Adopt a similar convention for task decomposition artifacts. Each orchestration session creates a structured directory with the decomposition plan, sub-task results, and a final synthesis. This provides auditability and session resumption support.

### 8.11 Journal Writing for Failure Documentation

**Pattern**: The journal-writer agent captures failures with emotional authenticity and technical precision.

**For Conductor**: When sub-tasks fail after multiple retries, automatically generate a structured failure report documenting: what was attempted, what failed, root cause analysis, and lessons learned. This becomes input for future task decomposition.

### 8.12 Self-Extending Meta-Skills

**Pattern**: The skill-creator skill teaches Claude how to create new skills following the kit's conventions.

**For Conductor**: Implement a meta-capability where the orchestrator can define new agent types or modify existing ones based on observed patterns. If certain tasks repeatedly require a specific combination of capabilities, the system could propose a new specialized agent type.

---

## 9. Summary Table: ClaudeKit vs Conductor Architecture Comparison

| Aspect | ClaudeKit | Conductor (Current) | Improvement Opportunity |
|--------|-----------|-------------------|------------------------|
| Agent definition | Markdown files with YAML frontmatter | Python classes | Add progressive disclosure loading |
| Orchestration | Prompt-driven, no formal state | Python orchestrator with state | Good foundation; add verification gates |
| Inter-agent comms | Filesystem (markdown reports) | In-memory (Python) | Add structured schemas + inspectable artifacts |
| Cost optimization | Manual model selection per agent | Single model | Implement model routing table |
| Guardrails | Hook scripts (pre/post tool use) | None | Implement hook system |
| Task decomposition | Planner agent + researcher agents | Decomposer module | Add complexity tiers |
| Observability | Discord/Telegram notifications | Dashboard (WebSocket) | Add structured execution traces |
| Extensibility | Drop-in markdown files | Code changes required | Add plugin/skill system |
| Failure handling | Prompt-based retry instructions | Orchestrator retry logic | Add structured failure reports |
| Context management | Progressive disclosure (3 tiers) | Full prompt loading | Critical improvement needed |

---

## 10. Appendix: File Counts

| Directory | Count | Types |
|-----------|-------|-------|
| agents/ | 16 | .md |
| commands/ | 53 | .md (nested directories) |
| skills/ | 32 | directories with SKILL.md |
| workflows/ | 4 | .md |
| hooks/ | 10 | .js, .sh, .ps1, .md |
| statusline | 3 | .js, .sh, .ps1 |
| config | 4 | .json, .env.example |
