# Superpowers: Comprehensive Survey and Analysis

**Project:** [obra/superpowers](https://github.com/obra/superpowers)
**Version:** 5.0.1
**Author:** Jesse Vincent
**License:** MIT
**Analyzed:** 2026-03-11

---

## 1. Project Overview

Superpowers is a composable skills-and-hooks system that overlays a structured software development workflow onto AI coding agents. It works as a plugin for Claude Code, Cursor, Codex, OpenCode, and Gemini CLI. Rather than being a standalone orchestrator, it enhances existing coding agents by injecting process discipline through markdown-based "skills" that the agent is instructed to follow.

The core value proposition: an AI coding agent with Superpowers will not immediately jump into writing code. Instead, it follows a structured pipeline -- brainstorm a design, write a plan, execute tasks via subagents with two-stage review, enforce TDD, and verify before claiming completion.

### Key Differentiator

Superpowers is **not code** -- it is almost entirely markdown documents and bash scripts. The "intelligence" lives in carefully crafted prompt engineering that shapes agent behavior through explicit instructions, rationalization prevention tables, and flowcharts. There is no runtime, no state machine, no orchestration engine. The agent itself IS the orchestrator, guided by skill documents.

---

## 2. Architecture Breakdown

### 2.1 Directory Structure

```
superpowers/
  hooks/
    hooks.json              # Claude Code hook configuration
    session-start           # Bash script injecting bootstrap context
    run-hook.cmd            # Windows hook runner
  skills/
    using-superpowers/      # Bootstrap skill (loaded at session start)
    brainstorming/          # Design phase
    writing-plans/          # Planning phase
    subagent-driven-development/  # Execution via subagents
    executing-plans/        # Execution without subagents
    test-driven-development/     # TDD enforcement
    systematic-debugging/   # Debugging methodology
    dispatching-parallel-agents/ # Parallel work
    requesting-code-review/ # Review dispatch
    receiving-code-review/  # Review response
    verification-before-completion/ # Completion gates
    using-git-worktrees/    # Workspace isolation
    finishing-a-development-branch/ # Branch completion
    writing-skills/         # Meta: creating new skills
  agents/
    code-reviewer.md        # Agent definition for code review
  commands/
    brainstorm.md           # Deprecated slash commands
    execute-plan.md
    write-plan.md
  .claude-plugin/
    plugin.json             # Plugin metadata
  .opencode/
    plugins/superpowers.js  # OpenCode plugin adapter
  .cursor-plugin/
    plugin.json             # Cursor plugin metadata
```

### 2.2 Bootstrap Mechanism

The system activates via a **SessionStart hook**. The `hooks/hooks.json` file registers a hook that fires on startup/resume/clear/compact events:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|resume|clear|compact",
      "hooks": [{
        "type": "command",
        "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" session-start"
      }]
    }]
  }
}
```

The `session-start` bash script reads the `using-superpowers/SKILL.md` content, escapes it for JSON, and injects it into the session context via `hookSpecificOutput.additionalContext`. This means the bootstrap skill is loaded into every conversation automatically -- the agent does not need to be told to use Superpowers.

### 2.3 Skill System

Each skill is a directory containing a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: skill-name
description: Use when [triggering conditions]
---
```

Key design decisions:

- **Frontmatter is trigger-only**: Descriptions MUST only describe when to use the skill, never summarize the workflow. Testing showed that when descriptions summarize the workflow, the agent shortcuts and follows the description instead of reading the full skill content.

- **Skills are loaded on demand**: Only the bootstrap skill (`using-superpowers`) is loaded at session start. All other skills are loaded via the `Skill` tool when the agent determines they are relevant.

- **Mandatory, not optional**: The bootstrap skill instructs the agent that even a "1% chance a skill might apply" means it MUST invoke the skill. A rationalization prevention table explicitly blocks common excuses ("this is just a simple question", "I need more context first", etc.).

- **Priority ordering**: Process skills (brainstorming, debugging) take priority over implementation skills. User instructions always override skill instructions.

### 2.4 Workflow Pipeline

The intended flow is a linear pipeline with quality gates:

```
1. Brainstorming
   - Explore context, ask questions one-at-a-time
   - Propose 2-3 approaches
   - Present design in sections for approval
   - Write spec doc, run spec-reviewer subagent
   - User reviews written spec

2. Git Worktree Setup
   - Create isolated workspace
   - Run project setup
   - Verify clean test baseline

3. Writing Plans
   - Break work into bite-sized tasks (2-5 min each)
   - Exact file paths, complete code, verification steps
   - Plan review loop via subagent

4. Subagent-Driven Development (preferred) or Executing Plans
   - One subagent per task
   - Two-stage review: spec compliance, then code quality
   - Fix-review loops until approved

5. Finishing
   - Verify tests pass
   - Present 4 options: merge/PR/keep/discard
   - Clean up worktree
```

### 2.5 Subagent Architecture

The subagent-driven development skill defines three distinct agent roles with dedicated prompt templates:

**Implementer** (`implementer-prompt.md`):
- Receives full task text (not told to read files)
- Encouraged to ask questions before starting
- Reports status: DONE / DONE_WITH_CONCERNS / BLOCKED / NEEDS_CONTEXT
- Self-reviews before reporting
- Explicitly told "it is always OK to stop and say this is too hard for me"

**Spec Reviewer** (`spec-reviewer-prompt.md`):
- Verifies implementation matches specification
- Explicitly told "Do Not Trust the Report" -- must read actual code
- Checks for missing requirements, extra/unneeded work, misunderstandings

**Code Quality Reviewer** (`code-quality-reviewer-prompt.md`):
- Only dispatched after spec compliance passes
- Reviews against standard code quality concerns
- Returns: Strengths, Issues (Critical/Important/Minor), Assessment

**Key rule**: Implementation subagents are dispatched sequentially (never in parallel) to avoid conflicts. Reviews are also sequential.

### 2.6 Model Selection Strategy

The SDD skill includes guidance on model selection per role:

- **Mechanical tasks** (isolated functions, clear specs, 1-2 files): cheap/fast model
- **Integration tasks** (multi-file, pattern matching): standard model
- **Architecture/design/review tasks**: most capable model

This is advisory, not enforced programmatically.

### 2.7 Cross-Platform Support

Superpowers supports multiple AI coding platforms through different integration mechanisms:

| Platform | Integration | Skill Loading |
|----------|------------|---------------|
| Claude Code | Plugin marketplace + hooks | Native Skill tool |
| Cursor | Plugin marketplace | Plugin system |
| Codex | Manual install | Fetch from URL |
| OpenCode | JS plugin | System prompt transform |
| Gemini CLI | Extension registry | `activate_skill` tool |

The OpenCode plugin (`superpowers.js`) is notable for including tool mapping that translates Claude Code tool names to OpenCode equivalents.

---

## 3. Key Design Patterns and Techniques

### 3.1 Rationalization Prevention

The most distinctive pattern in Superpowers. Nearly every skill includes:

1. **"Iron Law" statements** -- absolute rules stated emphatically:
   ```
   NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
   NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
   NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
   ```

2. **Rationalization tables** -- explicit counters to common excuses:
   ```
   | "Too simple to test" | Simple code breaks. Test takes 30 seconds. |
   | "I'll test after"    | Tests passing immediately prove nothing.   |
   ```

3. **Red Flags lists** -- self-check lists for the agent:
   ```
   - Code before test
   - "I already manually tested it"
   - "This is different because..."
   ```

4. **"Spirit vs Letter" preemption**:
   ```
   Violating the letter of the rules is violating the spirit of the rules.
   ```

This pattern is based on observed agent behavior -- the `writing-skills` skill documents a TDD approach where you first run agents without the skill, record their rationalizations, then write counters.

### 3.2 Graphviz Flowcharts as Decision Trees

Skills embed `dot` language flowcharts to make decision processes unambiguous:

```dot
digraph when_to_use {
    "Have implementation plan?" [shape=diamond];
    "Tasks mostly independent?" [shape=diamond];
    "subagent-driven-development" [shape=box];
    "executing-plans" [shape=box];
    ...
}
```

These serve as machine-readable decision trees that agents can follow more reliably than prose instructions.

### 3.3 Hard Gates

Critical transitions are marked with explicit `<HARD-GATE>` tags:

```markdown
<HARD-GATE>
Do NOT invoke any implementation skill, write any code, scaffold any project,
or take any implementation action until you have presented a design and
the user has approved it.
</HARD-GATE>
```

### 3.4 Subagent Stop Signals

Skills include escape hatches for subagents that should not follow workflow processes:

```markdown
<SUBAGENT-STOP>
If you were dispatched as a subagent to execute a specific task, skip this skill.
</SUBAGENT-STOP>
```

### 3.5 Review Loops with Iteration Limits

All review processes have bounded iteration counts:

- Spec review loop: max 5 iterations, then surface to human
- Plan review loop: max 5 iterations, then surface to human
- Debugging: after 3 failed fixes, question the architecture

### 3.6 Context Curation for Subagents

The controller agent reads the plan once, extracts all tasks with full text, and provides each subagent with exactly what it needs. Subagents never read plan files themselves. This reduces token usage and prevents context pollution.

### 3.7 Trust Hierarchies

The spec reviewer is explicitly told not to trust the implementer's report:

```markdown
## CRITICAL: Do Not Trust the Report
The implementer finished suspiciously quickly. Their report may be incomplete,
inaccurate, or optimistic. You MUST verify everything independently.
```

### 3.8 Escalation Protocols

The implementer has structured escalation paths:

- **DONE**: Normal completion
- **DONE_WITH_CONCERNS**: Completed but flagging doubts
- **NEEDS_CONTEXT**: Missing information, need more context
- **BLOCKED**: Cannot complete, need help

The controller handles each differently, potentially re-dispatching with a more capable model or breaking tasks into smaller pieces.

---

## 4. Strengths

### 4.1 Zero-Infrastructure Design

Superpowers requires no runtime, no server, no database, no configuration beyond plugin installation. Everything is markdown and bash. This makes it extremely portable and easy to understand.

### 4.2 Battle-Tested Rationalization Prevention

The rationalization tables and red flag lists are clearly derived from extensive real-world testing of agent behavior. The `writing-skills` skill documents the methodology: run agents without skills, record their rationalizations, write explicit counters. This is a genuinely novel contribution to prompt engineering.

### 4.3 Composable Skill Architecture

Skills reference each other by name with explicit requirement markers (`REQUIRED SUB-SKILL`, `REQUIRED BACKGROUND`). This creates a dependency graph without tight coupling. Skills can be added, removed, or modified independently.

### 4.4 Two-Stage Review Pattern

Separating spec compliance from code quality review is a smart design:
- Stage 1 catches "did we build the right thing?"
- Stage 2 catches "did we build it well?"

This mirrors how human code review naturally works.

### 4.5 Structured Escalation

The DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED status system gives subagents a safe way to flag problems without guessing. The explicit "it is always OK to stop and say this is too hard for me" instruction is important for preventing agents from producing low-quality work when they are out of their depth.

### 4.6 Claude Search Optimization (CSO)

The `writing-skills` skill includes a sophisticated section on optimizing skill descriptions for agent discovery. The finding that summarizing workflows in descriptions causes agents to skip the full skill content is a valuable insight.

### 4.7 Visual Brainstorming Companion

The browser-based visual companion for brainstorming sessions (serving HTML mockups, capturing click selections via event files) is a creative approach to bridging the gap between text-based AI and visual design decisions.

### 4.8 Cross-Platform Portability

Despite being built for Claude Code, the system works across 5+ platforms through adapter patterns. The tool mapping approach (translating tool names between platforms) is simple and effective.

---

## 5. Weaknesses and Limitations

### 5.1 No Runtime State or Persistence

There is no state tracking between sessions. The agent must re-read plan files, re-discover where it left off, and re-establish context from scratch each time. Superpowers relies entirely on git commits and file artifacts for persistence.

### 5.2 No Programmatic Enforcement

All rules are prompt-based. There is no linting, no pre-commit hook that verifies TDD was followed, no automated check that the review loop actually ran. Everything depends on the agent's compliance with written instructions. The rationalization prevention tables mitigate this, but cannot eliminate it.

### 5.3 Sequential-Only Subagent Execution

The SDD skill explicitly prohibits parallel implementation subagents ("Dispatch multiple implementation subagents in parallel (conflicts)"). This means tasks are always sequential, even when they touch completely independent codebases. The `dispatching-parallel-agents` skill exists for independent debugging, but not for implementation.

### 5.4 Token Efficiency Tension

The bootstrap skill is loaded into every conversation. The more comprehensive the instructions, the more tokens consumed before any work begins. The system explicitly acknowledges this tension ("getting-started workflows: <150 words each") but the `using-superpowers` skill alone is substantial.

### 5.5 No Progress Tracking Dashboard

There is no visibility into the current state of a multi-task execution. The controller agent tracks progress via TodoWrite, but there is no external dashboard or monitoring. The user sees progress only through the chat conversation.

### 5.6 Fragile Integration Points

The hook system relies on specific environment variables (`CLAUDE_PLUGIN_ROOT`) and platform-specific JSON output formats. The `session-start` script must handle differences between Claude Code and Cursor by checking which variable is set.

### 5.7 No Rollback or Recovery

If a subagent breaks something, there is no automated rollback. The system depends on git (worktree isolation + commits) as the recovery mechanism, which requires the agent to have committed at appropriate points.

### 5.8 Limited Error Handling in the Pipeline

If the brainstorming phase produces a poor spec, the plan will be poor, and the implementation will be poor. The spec-reviewer subagent loop helps, but the quality of the entire pipeline depends on the quality of the initial design conversation.

### 5.9 Overly Aggressive Discipline for Small Tasks

The system mandates a full brainstorming-planning-execution cycle for every task, explicitly calling out "A todo list, a single-function utility, a config change -- all of them." This creates significant overhead for genuinely simple changes. While the skill says "The design can be short," the process overhead remains.

---

## 6. Ideas for Improving the Conductor Project

### 6.1 Adopt Rationalization Prevention Tables

**What Superpowers does:** Every discipline-enforcing skill includes tables mapping common excuses to reality checks.

**How Conductor can use this:** The decomposer and reviewer components should include rationalization prevention in their prompts. When the orchestrator decomposes tasks, it should have explicit counters for "this is too simple to decompose" and "I can just do it all at once."

### 6.2 Implement Two-Stage Review

**What Superpowers does:** Spec compliance review (did we build the right thing?) followed by code quality review (did we build it well?).

**How Conductor can use this:** The reviewer component should be split into two phases. The first phase verifies task completion against the plan. The second phase reviews code quality. This separation prevents conflating "incomplete" with "poorly written."

### 6.3 Structured Subagent Status Reporting

**What Superpowers does:** DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED with specific handling for each.

**How Conductor can use this:** Sub-agents dispatched by the orchestrator should report structured statuses. The orchestrator should have explicit handling paths for each status, including the ability to re-dispatch with more context or escalate to the user.

### 6.4 Context Curation Pattern

**What Superpowers does:** The controller reads the plan once, extracts all task text, and provides each subagent with exactly what it needs. Subagents never read plan files.

**How Conductor can use this:** When the orchestrator dispatches sub-tasks, it should pre-digest context and provide focused, complete prompts rather than telling sub-agents to read files or discover context on their own.

### 6.5 Model Selection by Task Complexity

**What Superpowers does:** Advisory guidance on using cheap models for mechanical tasks, standard for integration, capable for architecture/review.

**How Conductor can use this:** The orchestrator should classify decomposed tasks by complexity and route them to appropriate models. This is a cost optimization that Conductor can enforce programmatically (unlike Superpowers' advisory approach).

### 6.6 Bounded Iteration Loops

**What Superpowers does:** All review/fix cycles have a maximum iteration count (typically 5) before escalating to human.

**How Conductor can use this:** The orchestrator should enforce iteration limits on all feedback loops. After N iterations, the system should surface the issue to the user rather than continuing to loop.

### 6.7 Spec-Before-Plan-Before-Code Pipeline

**What Superpowers does:** Enforces brainstorm -> spec -> plan -> execute as a mandatory pipeline. No skipping steps.

**How Conductor can use this:** The orchestrator's decomposer should validate that requirements are clear before decomposing into tasks. A lightweight "spec validation" step before task decomposition could catch ambiguous or underspecified requests early.

### 6.8 Hard Gate Pattern

**What Superpowers does:** Uses `<HARD-GATE>` markers to enforce that certain transitions cannot happen without prerequisites.

**How Conductor can use this:** The orchestrator should have programmatic gates between phases (decomposition -> execution, execution -> completion). Unlike Superpowers' prompt-based gates, Conductor can enforce these in code.

### 6.9 Flowchart-Based Decision Trees

**What Superpowers does:** Embeds `dot` language flowcharts in skills to make decision processes unambiguous.

**How Conductor can use this:** The decomposer and reviewer prompts could include decision tree flowcharts for complex routing decisions. Testing showed that agents follow flowcharts more reliably than prose.

### 6.10 Trust Hierarchy for Review

**What Superpowers does:** Explicitly tells reviewers not to trust implementer reports. Spec reviewer must read actual code.

**How Conductor can use this:** The reviewer component should independently verify sub-agent outputs rather than trusting their self-reported status. This maps to the orchestrator verifying that a sub-task's claimed outputs actually exist and are correct.

### 6.11 Verification-Before-Completion Gate

**What Superpowers does:** Dedicated skill that prevents claiming completion without fresh evidence.

**How Conductor can use this:** The orchestrator should require verification evidence (test output, build output, actual file diffs) before marking any task as complete. Self-reported "done" from sub-agents should be treated as claims requiring verification.

### 6.12 Skill Description Design for Agent Discovery

**What Superpowers does:** Discovered that skill descriptions summarizing workflows cause agents to shortcut and skip the full content.

**How Conductor can use this:** When the orchestrator presents task descriptions or capability descriptions, keep them focused on triggering conditions ("when to use") rather than workflow summaries ("what it does"). This prevents the agent from hallucinating a simplified version of the process.

### 6.13 Parallel Agent Patterns

**What Superpowers does:** The `dispatching-parallel-agents` skill provides clear criteria for when parallelism is safe (independent domains, no shared state, clear scope per agent).

**How Conductor can use this:** The orchestrator should apply these same criteria when deciding whether to execute decomposed tasks in parallel. The key signals: independent files, independent subsystems, clear boundaries, no shared state.

### 6.14 Escalation from Cheap to Capable Models

**What Superpowers does:** When a subagent reports BLOCKED, the controller can re-dispatch with a more capable model.

**How Conductor can use this:** The orchestrator should implement a model escalation ladder. Start with the cheapest appropriate model. If the sub-agent fails or reports uncertainty, automatically retry with a more capable model before escalating to the user.

---

## 7. Notable Code Examples

### 7.1 Session Start Hook (Bootstrap Injection)

The session-start script (`hooks/session-start`) demonstrates how to inject context into every agent session:

```bash
# Read using-superpowers content
using_superpowers_content=$(cat "${PLUGIN_ROOT}/skills/using-superpowers/SKILL.md")

# Escape for JSON embedding
escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\r'/\\r}"
    s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}

# Output as hookSpecificOutput for context injection
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "${session_context}"
  }
}
EOF
```

### 7.2 Implementer Prompt Template Structure

The implementer prompt (`skills/subagent-driven-development/implementer-prompt.md`) shows effective subagent prompt structure:

```markdown
## Before You Begin
If you have questions about:
- The requirements or acceptance criteria
- The approach or implementation strategy
- Dependencies or assumptions
**Ask them now.** Raise any concerns before starting work.

## When You're in Over Your Head
It is always OK to stop and say "this is too hard for me."
Bad work is worse than no work. You will not be penalized for escalating.

## Report Format
- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- What you implemented
- What you tested and test results
- Files changed
- Self-review findings
- Any issues or concerns
```

### 7.3 Spec Reviewer's "Do Not Trust" Pattern

From `skills/subagent-driven-development/spec-reviewer-prompt.md`:

```markdown
## CRITICAL: Do Not Trust the Report
The implementer finished suspiciously quickly. Their report may be incomplete,
inaccurate, or optimistic. You MUST verify everything independently.

**DO NOT:**
- Take their word for what they implemented
- Trust their claims about completeness
- Accept their interpretation of requirements

**DO:**
- Read the actual code they wrote
- Compare actual implementation to requirements line by line
- Check for missing pieces they claimed to implement
```

### 7.4 CSO Finding on Description Design

From `skills/writing-skills/SKILL.md`:

```markdown
Testing revealed that when a description summarizes the skill's workflow,
Claude may follow the description instead of reading the full skill content.
A description saying "code review between tasks" caused Claude to do ONE
review, even though the skill's flowchart clearly showed TWO reviews
(spec compliance then code quality).

When the description was changed to just "Use when executing implementation
plans with independent tasks" (no workflow summary), Claude correctly read
the flowchart and followed the two-stage review process.
```

---

## 8. Summary

Superpowers is a well-crafted prompt engineering system that transforms AI coding agents from "write code now" assistants into disciplined software engineers following structured processes. Its primary innovations are:

1. **Rationalization prevention as a first-class design pattern** -- anticipating and blocking agent excuses
2. **Skills as composable process documents** -- not code, but markdown that shapes behavior
3. **Two-stage review with trust boundaries** -- spec compliance separate from code quality
4. **Structured escalation protocols** -- giving subagents safe paths to report uncertainty

For the Conductor project, the most actionable takeaways are: implementing programmatic versions of Superpowers' prompt-based patterns (two-stage review, bounded iteration loops, hard gates between phases), adopting the context curation pattern for sub-agent dispatch, and implementing model escalation from cheap to capable based on task complexity and sub-agent feedback.

The fundamental insight from Superpowers is that **agent orchestration is as much about preventing bad behavior as enabling good behavior**. The rationalization prevention tables, trust hierarchies, and verification gates are all defensive patterns that prevent the common failure mode of agents confidently doing the wrong thing.
