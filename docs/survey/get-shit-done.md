# Survey: Get Shit Done (GSD)

**Repository:** https://github.com/gsd-build/get-shit-done
**Version analyzed:** 1.22.4
**Date:** 2026-03-11
**Purpose:** Extract patterns and ideas to improve our conductor orchestrator project.

---

## 1. Project Overview

GSD is a meta-prompting, context engineering, and spec-driven development system designed for Claude Code (and other AI coding CLI tools like OpenCode, Gemini CLI, and Codex). It provides a structured workflow layer on top of these tools to solve "context rot" -- the quality degradation that happens as Claude fills its context window.

**Core value proposition:** Give Claude everything it needs to do the work AND verify it, while keeping each execution context fresh and focused.

**Target user:** Solo developers or small teams who use AI coding agents. Not an enterprise tool -- explicitly avoids sprint ceremonies, stakeholder syncs, and organizational overhead.

**Tech stack:** Pure Node.js (CommonJS), no dependencies beyond devDependencies for testing. Installed via `npx get-shit-done-cc@latest`. Uses Claude Code's slash command system (`/gsd:command-name`) as the user interface.

---

## 2. Architecture Breakdown

### 2.1 Layered Architecture

GSD uses a three-layer architecture:

```
User Interface Layer
  commands/gsd/*.md         -- Slash command definitions (entry points)

Workflow Layer
  get-shit-done/workflows/*.md  -- Detailed workflow orchestration logic

Agent Layer
  agents/gsd-*.md           -- Specialized agent definitions with roles/tools

Tooling Layer
  get-shit-done/bin/gsd-tools.cjs  -- CLI utility for state/config/phase operations
  get-shit-done/bin/lib/*.cjs      -- Library modules (core, state, phase, verify, etc.)
```

### 2.2 Key Components

**Slash Commands (entry points):** Thin wrappers in `commands/gsd/` that define allowed tools and reference the workflow file. Example: `execute-phase.md` references `workflows/execute-phase.md`.

**Workflows (orchestration logic):** Detailed step-by-step instructions in XML-like format embedded in markdown. Each workflow defines steps with names, priorities, conditional logic, and success criteria. These are essentially prompt templates that the orchestrator (Claude) follows.

**Agents (specialized workers):** Defined in `agents/gsd-*.md` with YAML frontmatter specifying name, tools, and color. Each agent has a focused role with explicit constraints.

**CLI Tools (`gsd-tools.cjs`):** A Node.js CLI router with 50+ subcommands for state management, phase operations, git commits, template scaffolding, verification, and more. This is the machine-readable backbone that agents invoke via `Bash` tool calls.

### 2.3 Agent Roster

| Agent | Role | Model Profile (balanced) |
|-------|------|--------------------------|
| `gsd-planner` | Creates executable PLAN.md files with task breakdown | Opus |
| `gsd-executor` | Executes plans, creates per-task commits and SUMMARY.md | Sonnet |
| `gsd-verifier` | Goal-backward verification of phase completion | Sonnet |
| `gsd-plan-checker` | Validates plans before execution | Sonnet |
| `gsd-phase-researcher` | Investigates domain/tech before planning | Sonnet |
| `gsd-project-researcher` | Deep research during project initialization | Sonnet |
| `gsd-research-synthesizer` | Synthesizes research from parallel agents | Sonnet |
| `gsd-debugger` | Systematic debugging with persistent state | Sonnet |
| `gsd-codebase-mapper` | Analyzes existing codebases | Haiku |
| `gsd-integration-checker` | Checks integration between components | Sonnet |
| `gsd-nyquist-auditor` | Validates testing coverage | Sonnet |
| `gsd-roadmapper` | Creates roadmaps from requirements | Sonnet |

### 2.4 File System as State Store

GSD uses the file system (`.planning/` directory) as its entire state store:

```
.planning/
  PROJECT.md          -- Project vision, requirements, decisions
  REQUIREMENTS.md     -- Scoped v1/v2 requirements with traceability
  ROADMAP.md          -- Phase structure with progress tracking
  STATE.md            -- Living memory: position, decisions, blockers
  config.json         -- Workflow preferences, model profile
  phases/
    01-foundation/
      01-01-PLAN.md     -- Executable task plan
      01-01-SUMMARY.md  -- Execution result
      01-RESEARCH.md    -- Domain research
      01-CONTEXT.md     -- User decisions from discuss-phase
      01-VERIFICATION.md -- Goal verification report
  research/           -- Project-level research
  codebase/           -- Codebase analysis maps
  todos/pending/      -- Captured ideas
  quick/              -- Ad-hoc task tracking
  agent-history.json  -- Agent spawn/completion tracking
```

---

## 3. Key Design Patterns and Techniques

### 3.1 Context Engineering (Most Important Pattern)

GSD's central innovation is systematic context management. Every agent interaction is designed to stay under 50% context window usage.

**Fresh context per agent:** Each subagent (executor, researcher, etc.) is spawned via Claude Code's `Task()` primitive with a fresh 200K context window. The orchestrator stays at ~10-15% context usage, passing only file paths (not content) to subagents.

**File-path-only delegation:** The orchestrator passes paths like `{phase_dir}/{plan_file}` to agents, which read files themselves. This keeps the orchestrator lean.

```markdown
Task(
  subagent_type="gsd-executor",
  model="{executor_model}",
  prompt="
    <files_to_read>
    Read these files at execution start using the Read tool:
    - {phase_dir}/{plan_file} (Plan)
    - .planning/STATE.md (State)
    </files_to_read>
  "
)
```

**Structured frontmatter for machine-readable metadata:** SUMMARY.md files use YAML frontmatter with dependency graphs (`requires/provides/affects`), tech-stack tracking, key-files, and patterns-established. This enables automatic context assembly -- future planners can scan frontmatter across all summaries cheaply without reading full content.

### 3.2 Wave-Based Parallel Execution

Plans within a phase are grouped into "waves" based on dependency analysis. Plans in the same wave run in parallel (via multiple `Task()` calls). Waves execute sequentially.

**Wave assignment is pre-computed at plan time** -- the `wave` field is set in PLAN.md frontmatter during `/gsd:plan-phase`. Execute-phase reads wave numbers directly, no runtime dependency analysis needed.

**Vertical slices preferred over horizontal layers:** Plans are structured as feature slices (User model + API + UI) rather than technology layers (all models, then all APIs). This maximizes parallelism since independent features have no file conflicts.

### 3.3 Plan-Check-Revise Loop

A planner-checker feedback loop with a max of 3 iterations:

1. Planner creates PLAN.md files
2. Plan-checker verifies plans achieve phase goals
3. If issues found: planner revises (targeted updates, not full replan)
4. Re-check until pass or max iterations
5. At max iterations: user decides (force proceed / provide guidance / abandon)

### 3.4 Goal-Backward Verification

The verifier does NOT check if tasks were completed -- it checks if the GOAL was achieved. This is the key distinction:

```
Task "create chat component" can be marked complete when it's a placeholder.
Goal "working chat interface" requires actual message rendering and API wiring.
```

Three-level verification for every artifact:
1. **Exists** -- file is on disk
2. **Substantive** -- file has real implementation (not a stub)
3. **Wired** -- file is imported AND used (not orphaned)

The `must_haves` field in PLAN.md frontmatter carries verification criteria from planning to execution:

```yaml
must_haves:
  truths:
    - "User can see existing messages"
  artifacts:
    - path: "src/components/Chat.tsx"
      provides: "Message list rendering"
      min_lines: 30
  key_links:
    - from: "src/components/Chat.tsx"
      to: "/api/chat"
      via: "fetch in useEffect"
```

### 3.5 Deviation Rules (Auto-Fix Classification)

During execution, unplanned work is systematically classified:

| Rule | Trigger | Permission |
|------|---------|------------|
| Rule 1: Bug | Broken behavior, errors | Auto-fix |
| Rule 2: Missing Critical | Missing error handling, validation, auth | Auto-fix |
| Rule 3: Blocking | Prevents task completion | Auto-fix |
| Rule 4: Architectural | Structural changes | Ask user |

Priority: Rule 4 > Rules 1-3 > unsure defaults to Rule 4.

All deviations are tracked and documented in SUMMARY.md for traceability.

### 3.6 Atomic Git Commits

Each task gets its own commit with a structured format: `{type}({phase}-{plan}): {description}`. Files are staged individually (never `git add .`). This enables:
- `git bisect` to find exact failing task
- Independent reversion of any task
- Clean history for future AI sessions

### 3.7 State Machine via Markdown

STATE.md acts as a lightweight state machine with YAML frontmatter that is automatically synced from the markdown body. Every write to STATE.md goes through `writeStateMd()` which rebuilds frontmatter from body content.

The state tracks: current phase, current plan, status (planning/executing/verifying), progress bar, decisions, blockers, session continuity.

### 3.8 Model Profile System

Agents are assigned different Claude model tiers based on a "profile" setting:

| Profile | Planning | Execution | Verification |
|---------|----------|-----------|--------------|
| quality | Opus | Opus | Sonnet |
| balanced | Opus | Sonnet | Sonnet |
| budget | Sonnet | Sonnet | Haiku |

Individual agent model overrides are also supported.

### 3.9 Discuss Phase (User Context Capture)

Before planning, `/gsd:discuss-phase` captures user preferences for gray areas:
- Visual features: layout, density, interactions
- APIs/CLIs: response format, flags, error handling
- Content systems: structure, tone, depth

Output is a CONTEXT.md with locked decisions, deferred ideas, and areas left to Claude's discretion. This feeds into both research and planning -- the planner MUST honor locked decisions.

---

## 4. Workflow Pipeline

The complete lifecycle:

```
new-project
  Questions -> Research -> Requirements -> Roadmap -> STATE.md

For each phase:
  discuss-phase N    -> CONTEXT.md (user decisions)
  plan-phase N       -> RESEARCH.md -> PLAN.md (x N) -> Plan-check loop
  execute-phase N    -> Wave execution -> SUMMARY.md (x N) -> VERIFICATION.md
  verify-work N      -> UAT with user -> Fix plans if needed

complete-milestone   -> Archive -> Tag release
new-milestone        -> Fresh cycle
```

---

## 5. Strengths

### 5.1 Context Window Management
The single most impressive aspect. GSD solves the real problem that AI agents face: quality degradation over long sessions. By spawning fresh subagents with focused context, it maintains peak quality throughout execution.

### 5.2 Plans as Prompts
PLAN.md files ARE the execution prompts -- they include `@` references for context, XML-structured tasks, verification criteria, and success criteria. This removes the "interpretation layer" where an agent reads a specification and generates its own prompt.

### 5.3 Goal-Backward Verification
Distinguishing "tasks done" from "goal achieved" is a critical insight. The three-level artifact check (exists/substantive/wired) catches the most common AI failure mode: creating placeholder files that pass simple existence checks.

### 5.4 Deviation Classification System
Rules 1-4 give the executor clear decision boundaries. Auto-fixing bugs and missing validation (Rules 1-3) without stopping, while escalating architectural changes (Rule 4) to the user. This balances autonomy with safety.

### 5.5 Resumability
Re-running any command picks up where it left off. Execute-phase discovers completed SUMMARYs and skips them. STATE.md tracks exact position. Session continuity enables instant restoration.

### 5.6 CLI Tools as Machine Interface
`gsd-tools.cjs` provides a clean machine-readable API (JSON output) for all state mutations. Agents don't parse markdown directly for writes -- they call structured commands. This separates the human-readable format (markdown) from the machine interface (JSON).

### 5.7 Configuration Flexibility
Model profiles, workflow toggles (research/plan-checker/verifier), parallelization, git branching strategies -- all configurable without code changes.

### 5.8 Honest UX
The project acknowledges AI limitations directly: quality degradation curves, context budget planning, analysis paralysis guards, fix attempt limits. These are practical guardrails, not aspirational features.

---

## 6. Weaknesses and Limitations

### 6.1 Claude Code Coupling
Deeply coupled to Claude Code's `Task()` primitive, `@` file references, `AskUserQuestion`, and slash command system. Porting to other agent frameworks would require significant rework.

### 6.2 Markdown + Regex State Management
State management relies heavily on regex pattern matching against markdown files. The `stateExtractField` function uses regex to find `**Field:** value` patterns. This is fragile -- markdown formatting changes can break state reads.

### 6.3 No Real Database
Everything is file-system based. For complex projects with many phases/milestones, scanning directories and reading files becomes slow. No indexing, no querying, no transactions.

### 6.4 Workflow Logic in Markdown
The orchestration logic lives in markdown files that are essentially "prompt programs." These are not testable in the traditional sense -- you can't unit test a workflow step. The `tests/` directory tests the CLI tools, not the workflows.

### 6.5 Sequential Workflow Steps
Even though plans execute in parallel, the workflow steps (research -> plan -> check -> execute -> verify) are strictly sequential. There's no pipelining where phase N+1 planning begins while phase N executes.

### 6.6 Limited Error Recovery
When an executor agent fails, the options are retry, skip, or stop. There's no automatic retry with backoff, no fallback to a different approach, no partial result salvage beyond what git provides.

### 6.7 Large Surface Area
50+ CLI commands, 30+ workflow files, 12 agents. Maintaining consistency across all these definitions as the system evolves is challenging. The codebase has already accumulated migration code (e.g., `depth` -> `granularity` key rename).

### 6.8 No Streaming/Progress During Execution
While subagents execute (which can take 30+ minutes), the orchestrator provides no intermediate progress. Users see the spawn message, then wait for the completion report.

---

## 7. Ideas for Improving Our Conductor

### 7.1 Fresh Context Per Sub-Task (High Priority)

**Pattern:** Spawn each decomposed task as a separate agent with fresh context, passing only file paths (not content) in the spawn prompt.

**Why it matters:** Context rot is the #1 cause of degraded output quality in long-running agent sessions. Our orchestrator should track context budget and spawn fresh agents before quality degrades.

**Implementation idea for conductor:**
- Track estimated context usage per orchestrator session
- When approaching 40-50% usage, spawn sub-agents for remaining work
- Pass task descriptions + file paths, not file contents
- Each sub-agent reads its own context independently

### 7.2 Goal-Backward Verification (High Priority)

**Pattern:** After execution, verify that the GOAL was achieved, not just that tasks were completed. Check artifacts at three levels: exists, substantive (not a stub), and wired (imported and used).

**Implementation idea for conductor:**
- Add a verification phase to our orchestrator pipeline
- Derive "must-haves" from task objectives before execution
- After execution, verify must-haves against actual file system state
- Use grep/file checks (fast) rather than running the app (slow)

### 7.3 Deviation Classification (Medium Priority)

**Pattern:** Give agents explicit rules for handling unplanned work. Classify deviations by severity: auto-fixable (bugs, missing validation, blockers) vs. needs-user-approval (architectural changes).

**Implementation idea for conductor:**
- Define a deviation taxonomy in our decomposer/reviewer
- Let sub-agents auto-fix within scope (Rules 1-3 equivalent)
- Escalate structural changes to the orchestrator (Rule 4 equivalent)
- Document all deviations in task results

### 7.4 Wave-Based Parallel Execution (Medium Priority)

**Pattern:** Pre-compute dependency graphs during planning. Group independent tasks into "waves." Execute waves in parallel, sequence between waves.

**Implementation idea for conductor:**
- Analyze task dependencies during decomposition
- Assign wave numbers based on dependency chain
- Run all tasks in a wave concurrently
- Wait for wave completion before starting next wave
- Prefer "vertical slice" task decomposition for better parallelism

### 7.5 Plans as Prompts (Medium Priority)

**Pattern:** Task plans should BE the execution prompts, not documents that get interpreted into prompts. Include all context references, verification criteria, and success criteria directly in the task specification.

**Implementation idea for conductor:**
- Structure decomposed tasks as complete execution prompts
- Include `@` file references for relevant source files
- Include specific verification commands (not just "test passes")
- Include measurable acceptance criteria

### 7.6 User Decision Capture Before Planning (Medium Priority)

**Pattern:** Before planning/decomposing, capture user preferences for implementation choices. Distinguish between locked decisions (must follow), deferred ideas (must not include), and discretionary areas.

**Implementation idea for conductor:**
- Add a "discuss" phase before decomposition
- Identify gray areas based on the task domain
- Store decisions as context that feeds into decomposition
- Enforce locked decisions during execution

### 7.7 Atomic Git Commits Per Task (Low Priority)

**Pattern:** Each sub-task gets its own commit with a structured format. Files staged individually, never bulk-added.

**This is specific to code-generating agents but relevant for our conductor's code-writing tasks.**

### 7.8 State Frontmatter Sync (Low Priority)

**Pattern:** STATE.md has a YAML frontmatter section that is automatically kept in sync with the markdown body via `writeStateMd()`. This provides both human-readable (markdown) and machine-readable (YAML) views of the same data.

**Implementation idea for conductor:**
- Maintain state in a structured format (JSON/YAML) with a human-readable projection
- Auto-sync between formats on every write
- Use the structured format for programmatic access, the readable format for user inspection

### 7.9 Analysis Paralysis Guard (Low Priority)

**Pattern:** If an agent makes 5+ consecutive Read/Grep calls without any Write/Edit action, force it to either write code or report "blocked."

**Implementation idea for conductor:**
- Monitor sub-agent tool usage patterns
- Detect stuck loops (repeated reads without writes)
- Intervene with a prompt injection or timeout

### 7.10 Model Tier Assignment by Agent Role (Low Priority)

**Pattern:** Assign different model tiers (quality/speed/cost) to different agent roles. Planning gets the most capable model, execution gets a balanced model, verification gets a fast model.

**Implementation idea for conductor:**
- Define model profiles for our agent roles
- Use more capable models for decomposition/review
- Use faster/cheaper models for execution and verification
- Make profiles configurable

---

## 8. Notable Code Examples

### 8.1 Context-Lean Orchestrator Spawn

From `workflows/execute-phase.md` -- the orchestrator passes paths, not content:

```markdown
Task(
  subagent_type="gsd-executor",
  model="{executor_model}",
  prompt="
    <objective>
    Execute plan {plan_number} of phase {phase_number}-{phase_name}.
    </objective>

    <files_to_read>
    Read these files at execution start using the Read tool:
    - {phase_dir}/{plan_file} (Plan)
    - .planning/STATE.md (State)
    - ./CLAUDE.md (Project instructions, if exists)
    </files_to_read>

    <success_criteria>
    - [ ] All tasks executed
    - [ ] Each task committed individually
    - [ ] SUMMARY.md created
    </success_criteria>
  "
)
```

### 8.2 Large Output Handling

From `get-shit-done/bin/lib/core.cjs` -- handles outputs exceeding Claude Code's buffer:

```javascript
function output(result, raw, rawValue) {
  if (raw && rawValue !== undefined) {
    process.stdout.write(String(rawValue));
  } else {
    const json = JSON.stringify(result, null, 2);
    // Large payloads exceed Claude Code's Bash tool buffer (~50KB).
    // Write to tmpfile and output the path prefixed with @file:
    if (json.length > 50000) {
      const tmpPath = path.join(require('os').tmpdir(), `gsd-${Date.now()}.json`);
      fs.writeFileSync(tmpPath, json, 'utf-8');
      process.stdout.write('@file:' + tmpPath);
    } else {
      process.stdout.write(json);
    }
  }
  process.exit(0);
}
```

### 8.3 Compound Init Commands

From `get-shit-done/bin/lib/init.cjs` -- single CLI call loads ALL context needed for a workflow:

```javascript
function cmdInitExecutePhase(cwd, phase, raw) {
  const config = loadConfig(cwd);
  const phaseInfo = findPhaseInternal(cwd, phase);
  const milestone = getMilestoneInfo(cwd);
  const roadmapPhase = getRoadmapPhaseInternal(cwd, phase);

  const result = {
    executor_model: resolveModelInternal(cwd, 'gsd-executor'),
    verifier_model: resolveModelInternal(cwd, 'gsd-verifier'),
    commit_docs: config.commit_docs,
    parallelization: config.parallelization,
    phase_found: !!phaseInfo,
    phase_dir: phaseInfo?.directory || null,
    plans: phaseInfo?.plans || [],
    incomplete_plans: phaseInfo?.incomplete_plans || [],
    // ... 20+ fields pre-computed in one call
  };
  output(result, raw);
}
```

This pattern minimizes Bash tool calls from the orchestrator -- one call retrieves everything.

### 8.4 Stub Detection Patterns

From `agents/gsd-verifier.md` -- concrete patterns for detecting AI-generated stubs:

```javascript
// RED FLAGS for React components:
return <div>Component</div>
return <div>Placeholder</div>
onClick={() => {}}
onChange={() => console.log('clicked')}
onSubmit={(e) => e.preventDefault()}  // Only prevents default

// RED FLAGS for API routes:
export async function POST() {
  return Response.json({ message: "Not implemented" });
}
export async function GET() {
  return Response.json([]); // Empty array with no DB query
}

// RED FLAGS for wiring:
fetch('/api/messages')  // No await, no .then, no assignment
await prisma.message.findMany()
return Response.json({ ok: true })  // Returns static, not query result
```

### 8.5 Quality Degradation Awareness

From `agents/gsd-planner.md` -- explicit acknowledgment of context quality curve:

```
| Context Usage | Quality | Claude's State |
|---------------|---------|----------------|
| 0-30%         | PEAK    | Thorough, comprehensive |
| 30-50%        | GOOD    | Confident, solid work |
| 50-70%        | DEGRADING | Efficiency mode begins |
| 70%+          | POOR    | Rushed, minimal |

Rule: Plans should complete within ~50% context.
```

---

## 9. Summary of Key Takeaways for Conductor

1. **Context management is everything.** Fresh agent contexts per task is the single most impactful pattern.
2. **Verify goals, not tasks.** A three-level verification (exists/substantive/wired) catches the most common AI failure mode.
3. **Plans should be execution-ready.** Include all context references, verification commands, and acceptance criteria in the task itself.
4. **Pre-compute dependencies.** Wave assignment during planning eliminates runtime dependency analysis.
5. **Classify deviations systematically.** Give agents clear rules for when to auto-fix vs. escalate.
6. **Minimize orchestrator context.** Pass paths, not content. Use compound init commands to batch state reads.
7. **User preferences before planning.** Capture locked decisions, deferred items, and discretionary areas before decomposition.
8. **File system as state.** For AI agent workflows, markdown + frontmatter provides both human-readable and machine-readable state. YAML frontmatter for structured access, markdown body for narrative context.
9. **Model tiering.** Use the most capable model for planning/decomposition, balanced models for execution.
10. **Acknowledge AI limitations.** Build in analysis paralysis guards, context budget tracking, and fix attempt limits.
