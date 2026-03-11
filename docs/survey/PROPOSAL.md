# Conductor Enhancement Proposal

**Date**: 2026-03-11
**Based on**: Analysis of Get Shit Done, Superpowers, Claude Task Master, and ClaudeKit Engineer
**Target**: `packages/conductor-core/src/conductor/`

---

## Executive Summary

After analyzing four production-grade AI orchestration systems, we identified **12 high-impact enhancements** for Conductor, grouped into three tiers. The common thread across all four projects: **the quality of AI agent output degrades predictably with context size and task ambiguity**. Every successful pattern we found is ultimately a strategy to either (a) keep agent context fresh and focused, or (b) verify outcomes independently of agent self-reporting.

Conductor already has strong foundations: atomic state management, dependency scheduling, escalation routing, and a review loop. The proposals below build on these strengths.

---

## Tier 1: High Impact (Next Sprint)

### 1.1 Multi-Phase Decomposition Pipeline

**Current**: Single-shot `TaskDecomposer.decompose()` asks one LLM call to produce the entire `TaskPlan`.

**Proposed**: Three-phase pipeline inspired by Claude Task Master:

```
Phase 1: Initial Decomposition
  feature_description → flat list of high-level TaskSpecs

Phase 2: Complexity Analysis
  For each TaskSpec → complexity_score (1-10), recommended_subtasks, expansion_prompt

Phase 3: Selective Expansion
  Only expand tasks where complexity_score > threshold → detailed sub-TaskSpecs
```

**Why**: Single-shot decomposition produces either too-coarse or too-granular tasks. Complexity-informed expansion gives each sub-task AI-specific guidance for how to break it down, producing higher quality task plans.

**Implementation sketch**:
```python
# orchestrator/decomposer.py

class ComplexityAnalysis(BaseModel):
    task_id: str
    complexity_score: int  # 1-10
    recommended_subtasks: int
    expansion_prompt: str  # task-specific guidance
    reasoning: str

class TaskDecomposer:
    async def decompose(self, feature_description: str) -> TaskPlan:
        # Phase 1: coarse decomposition
        coarse_plan = await self._initial_decompose(feature_description)

        # Phase 2: complexity scoring
        analyses = await self._analyze_complexity(coarse_plan.tasks)

        # Phase 3: selective expansion
        expanded_tasks = []
        for task, analysis in zip(coarse_plan.tasks, analyses):
            if analysis.complexity_score > 5:
                subtasks = await self._expand_task(task, analysis)
                expanded_tasks.extend(subtasks)
            else:
                expanded_tasks.append(task)

        return TaskPlan(
            feature_name=coarse_plan.feature_name,
            tasks=expanded_tasks,
            max_agents=coarse_plan.max_agents,
        )
```

**Files to modify**: `orchestrator/decomposer.py`, `orchestrator/models.py`

---

### 1.2 Goal-Backward Verification

**Current**: `reviewer.py` does a single code-quality review of agent output. It reads the file and asks "is this good?" — but doesn't verify the task's *goal* was achieved.

**Proposed**: Three-level verification inspired by GSD:

| Level | Check | Example |
|-------|-------|---------|
| **Exists** | File is on disk | `os.path.exists(target_file)` |
| **Substantive** | File has real implementation (not stub) | Line count > threshold, no placeholder patterns |
| **Wired** | File is imported and used | Grep for imports in related files |

**Implementation sketch**:
```python
# orchestrator/verifier.py (new file)

STUB_PATTERNS = [
    r'return\s+<div>.*</div>',           # React placeholder
    r'pass\s*$',                          # Python pass-only
    r'raise\s+NotImplementedError',       # Not implemented
    r'TODO|FIXME|PLACEHOLDER',            # Markers
    r'return\s+\{\}',                     # Empty return
    r'return\s+\[\]',                     # Empty list return
]

class TaskVerifier:
    async def verify(self, task: TaskSpec, repo_path: str) -> VerificationResult:
        results = []

        # Level 1: Exists
        exists = Path(repo_path, task.target_file).exists()
        results.append(("exists", exists))

        if not exists:
            return VerificationResult(passed=False, results=results)

        # Level 2: Substantive (not a stub)
        content = Path(repo_path, task.target_file).read_text()
        stub_matches = [p for p in STUB_PATTERNS if re.search(p, content)]
        is_substantive = len(content.splitlines()) > 10 and not stub_matches
        results.append(("substantive", is_substantive))

        # Level 3: Wired (imported/used by other files)
        is_wired = await self._check_wiring(task, repo_path)
        results.append(("wired", is_wired))

        return VerificationResult(
            passed=all(r[1] for r in results),
            results=results,
        )
```

**Files to create**: `orchestrator/verifier.py`
**Files to modify**: `orchestrator/orchestrator.py` (add verification step after review)

---

### 1.3 Wave-Based Parallel Execution

**Current**: `DependencyScheduler` uses `graphlib.TopologicalSorter` and exposes `get_ready()`, but the orchestrator spawns agents one at a time in a loop.

**Proposed**: Pre-compute dependency waves during decomposition. Execute all tasks in a wave concurrently, wait for wave completion, then start the next wave.

```
Wave 0: [task-1, task-2, task-3]     ← no dependencies, run in parallel
Wave 1: [task-4, task-5]             ← depend on wave 0 tasks
Wave 2: [task-6]                     ← depends on wave 1 tasks
```

**Implementation sketch**:
```python
# orchestrator/scheduler.py — add wave computation

class DependencyScheduler:
    def compute_waves(self) -> list[list[str]]:
        """Pre-compute execution waves from dependency graph."""
        waves = []
        sorter = copy.copy(self._sorter)  # don't mutate original
        sorter.prepare()
        while sorter.is_active():
            wave = list(sorter.get_ready())
            waves.append(wave)
            for task_id in wave:
                sorter.done(task_id)
        return waves

# orchestrator/orchestrator.py — wave-based execution

async def _execute_waves(self, waves: list[list[str]]) -> None:
    for i, wave in enumerate(waves):
        logger.info(f"Starting wave {i} with {len(wave)} tasks")
        # Spawn all tasks in this wave concurrently
        results = await asyncio.gather(
            *[self._run_agent_loop(task_id) for task_id in wave],
            return_exceptions=True,
        )
        # Handle failures before proceeding to next wave
        for task_id, result in zip(wave, results):
            if isinstance(result, Exception):
                logger.error(f"Task {task_id} failed: {result}")
```

**Files to modify**: `orchestrator/scheduler.py`, `orchestrator/orchestrator.py`

---

### 1.4 Structured Agent Status Reporting

**Current**: Agents report freeform text. The orchestrator extracts `result_text` from `StreamMonitor` and passes it to the reviewer.

**Proposed**: Define a structured status protocol inspired by Superpowers:

```python
# orchestrator/models.py

class AgentReport(BaseModel):
    status: Literal["DONE", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT"]
    summary: str
    files_changed: list[str]
    concerns: list[str] = []
    blocking_reason: str | None = None
    context_needed: str | None = None
```

The orchestrator handles each status differently:
- **DONE** → proceed to review
- **DONE_WITH_CONCERNS** → proceed to review, flag concerns for human
- **BLOCKED** → retry with more capable model, or escalate
- **NEEDS_CONTEXT** → provide additional context and retry

**Files to modify**: `orchestrator/models.py`, `orchestrator/identity.py` (add status protocol to system prompt), `orchestrator/orchestrator.py` (handle statuses)

---

## Tier 2: Medium Impact (Next Milestone)

### 2.1 Model Routing Table

**Current**: All agents use the same model (whatever the SDK defaults to).

**Proposed**: Configurable model profiles per task type, inspired by both GSD and ClaudeKit:

```python
# orchestrator/models.py

class ModelProfile(BaseModel):
    """Model assignment per role."""
    decomposer: str = "opus"        # needs best reasoning
    reviewer: str = "sonnet"        # quality-critical
    executor: str = "sonnet"        # balanced
    verifier: str = "haiku"         # fast checks

MODEL_PROFILES = {
    "quality": ModelProfile(decomposer="opus", reviewer="opus", executor="sonnet", verifier="sonnet"),
    "balanced": ModelProfile(decomposer="opus", reviewer="sonnet", executor="sonnet", verifier="haiku"),
    "budget": ModelProfile(decomposer="sonnet", reviewer="sonnet", executor="haiku", verifier="haiku"),
}
```

**Files to modify**: `orchestrator/models.py`, `orchestrator/orchestrator.py`, `acp/client.py`

---

### 2.2 Deviation Classification

**Current**: Agents can do whatever they want within their file scope. No classification of unplanned work.

**Proposed**: Inject deviation rules into agent system prompts (from GSD):

| Rule | Trigger | Permission |
|------|---------|------------|
| Rule 1: Bug | Broken behavior, errors | Auto-fix, document |
| Rule 2: Missing Critical | Missing validation, error handling | Auto-fix, document |
| Rule 3: Blocking | Prevents task completion | Auto-fix, document |
| Rule 4: Architectural | Structural changes, new dependencies | Escalate to orchestrator |

Add deviation tracking to `AgentReport`:
```python
class Deviation(BaseModel):
    rule: Literal[1, 2, 3, 4]
    description: str
    action_taken: str

class AgentReport(BaseModel):
    # ... existing fields ...
    deviations: list[Deviation] = []
```

**Files to modify**: `orchestrator/identity.py`, `orchestrator/models.py`

---

### 2.3 Two-Stage Review

**Current**: Single `review_output()` call checks both spec compliance and code quality.

**Proposed**: Split into two stages (from Superpowers):

1. **Spec Review** — "Did we build the right thing?"
   - Compare output against task description and acceptance criteria
   - Check all required files exist and are wired
   - Independent of code style

2. **Quality Review** — "Did we build it well?"
   - Code quality, patterns, security
   - Only runs if spec review passes

```python
# orchestrator/reviewer.py

async def review_spec_compliance(task: TaskSpec, agent_report: AgentReport, repo_path: str) -> SpecVerdict:
    """Stage 1: Does the output match the task spec?"""
    ...

async def review_code_quality(task: TaskSpec, repo_path: str) -> QualityVerdict:
    """Stage 2: Is the code well-written? Only called after spec passes."""
    ...
```

**Files to modify**: `orchestrator/reviewer.py`, `orchestrator/orchestrator.py`

---

### 2.4 Bounded Iteration Loops

**Current**: The review-revise loop has `max_revisions=2` hardcoded in `_run_agent_loop`.

**Proposed**: Make iteration limits configurable and add explicit escalation:

```python
class OrchestratorConfig(BaseModel):
    max_review_iterations: int = 3
    max_decomposition_retries: int = 2
    max_verification_retries: int = 2
    escalation_on_limit: Literal["fail", "human", "skip"] = "human"
```

When limits are hit, the orchestrator surfaces the issue to the human rather than silently failing or continuing.

**Files to modify**: `orchestrator/orchestrator.py`

---

### 2.5 Context-Lean Agent Spawning

**Current**: `build_system_prompt()` includes task description and file paths. The orchestrator passes the full prompt to `ACPClient.send()`.

**Proposed**: Follow GSD's pattern of passing file paths only, letting agents read their own context:

```python
def build_system_prompt(identity: AgentIdentity) -> str:
    """Build a lean system prompt that tells the agent what to read, not what files contain."""
    return f"""You are {identity.name}, a coding agent.

Your task: {identity.task_description}

Read these files before starting work:
- Target: {identity.target_file}
- Context: {', '.join(identity.material_files)}

Report your work using the structured status protocol (DONE/BLOCKED/NEEDS_CONTEXT).
"""
```

This keeps the orchestrator's context lean and gives each agent fresh context.

**Files to modify**: `orchestrator/identity.py`

---

## Tier 3: Future Enhancements

### 3.1 Progressive Disclosure for Agent Capabilities

From ClaudeKit: maintain a lightweight registry of agent capabilities (name + description) and only load full prompts when dispatching. This allows scaling to many agent types without bloating orchestrator context.

### 3.2 Prompt Template System

From Claude Task Master: externalize prompts into structured JSON/YAML templates with parameter schemas, variants, and interpolation. This makes prompts versionable, testable, and cacheable.

### 3.3 Pre-Decomposition Discussion Phase

From GSD: before decomposing, capture user preferences for gray areas. Distinguish between locked decisions (must follow), deferred items (must not include), and discretionary areas (agent's choice). Store as context that feeds into decomposition.

### 3.4 Automated Guardrail Hooks

From ClaudeKit: implement pre/post execution hooks that:
- **Pre-execution**: validate agent actions against safety rules
- **Post-execution**: check output quality (file size, test pass rates)
- **Non-blocking suggestions**: inject context without stopping pipeline

### 3.5 Cost Tracking and Budget Controls

From ClaudeKit: track token usage per sub-task and per agent. Implement budget limits — if a sub-task exceeds its token budget, escalate rather than allowing unbounded spending.

### 3.6 Failure Journal

From ClaudeKit: when sub-tasks fail after retries, generate structured failure reports documenting what was attempted, what failed, and root cause analysis. Feed these into future decomposition to avoid repeating mistakes.

---

## Priority Implementation Order

| # | Enhancement | Impact | Effort | Dependencies |
|---|-------------|--------|--------|-------------|
| 1 | Wave-based parallel execution (1.3) | High | Low | Already has scheduler |
| 2 | Structured agent status (1.4) | High | Low | Prompt change + model |
| 3 | Goal-backward verification (1.2) | High | Medium | New verifier module |
| 4 | Multi-phase decomposition (1.1) | High | Medium | Refactor decomposer |
| 5 | Two-stage review (2.3) | Medium | Low | Refactor reviewer |
| 6 | Model routing table (2.1) | Medium | Low | Config + plumbing |
| 7 | Deviation classification (2.2) | Medium | Low | Prompt + model change |
| 8 | Bounded iterations (2.4) | Medium | Low | Config extraction |
| 9 | Context-lean spawning (2.5) | Medium | Low | Prompt refactor |
| 10 | Prompt templates (3.2) | Medium | Medium | New module |
| 11 | Pre-decomposition discussion (3.3) | Medium | Medium | New workflow step |
| 12 | Cost tracking (3.5) | Low | Medium | Token counting infra |

---

## Cross-Cutting Themes

### Theme 1: Verify Goals, Not Tasks
Every surveyed project that achieves reliable output has independent verification. Conductor's review step is good but needs the *goal-backward* perspective: check if the objective was met, not just if the code looks OK.

### Theme 2: Fresh Context Per Agent
GSD's central insight. Quality degrades predictably with context size. Conductor already spawns separate agent sessions — we should optimize the prompts to be as lean as possible (paths, not content).

### Theme 3: Defensive Prompt Engineering
Superpowers' key contribution. Agents rationalize skipping steps. Add explicit rationalization prevention to critical prompts (decomposer, reviewer, verifier). Include red-flag lists and "iron law" statements.

### Theme 4: Cost-Conscious Model Routing
All four projects address this. Using opus for planning and haiku for verification is a 10x+ cost difference per token. Conductor should make this configurable from day one.

### Theme 5: Structured Communication Protocols
Freeform text between orchestrator and agents loses information. Structured status reports (DONE/BLOCKED/NEEDS_CONTEXT) with typed fields enable programmatic handling of edge cases.
