# Claude Task Master - Comprehensive Survey & Analysis

**Repository:** https://github.com/eyaltoledano/claude-task-master
**Version analyzed:** 0.43.0
**Date:** 2026-03-11

---

## 1. Project Overview

Claude Task Master (published as `task-master-ai` on npm) is a task management system designed for AI-driven software development. Its core thesis: AI coding assistants (Cursor, Claude Code, Cline, etc.) work best when they have a structured, machine-readable task plan rather than free-form instructions. The system bridges the gap between high-level product requirements (PRDs) and individual coding tasks by using AI to decompose, analyze, and manage the work.

Key value propositions:
- **PRD-to-tasks pipeline**: Feed in a product requirements document, get a structured task list with dependencies
- **Complexity-aware task expansion**: AI analyzes tasks for complexity (1-10 score), then recursively expands high-complexity tasks into subtasks
- **Dependency graph management**: Tasks declare dependencies on other tasks; the system validates, detects cycles, and orders work accordingly
- **Multi-AI-provider support**: Works with 18+ AI providers (Anthropic, OpenAI, Google, Groq, Ollama, Claude Code CLI, etc.)
- **MCP server integration**: Exposes all operations as MCP tools so AI assistants can directly manage their own task lists
- **Autopilot loop**: Can iteratively run Claude Code CLI to work through tasks unattended

---

## 2. Architecture Breakdown

### 2.1 High-Level Structure

The project is a monorepo using npm workspaces with the following major components:

```
claude-task-master/
  src/                          # Legacy JS source (still core runtime)
    ai-providers/               # 18+ provider adapters
    constants/                  # Task status, priority, paths
    profiles/                   # IDE/tool-specific integrations (Cursor, Claude, VSCode, etc.)
    prompts/                    # JSON prompt templates with Handlebars-style variables
    schemas/                    # Zod schemas for AI response validation
    progress/                   # Progress tracking UI
    provider-registry/          # Dynamic provider registration
    utils/                      # Path resolution, formatting, etc.
  scripts/modules/              # Core business logic (JS)
    task-manager/               # Individual task operations (expand, analyze, parse-prd, etc.)
    dependency-manager.js       # Dependency graph operations
    ai-services-unified.js      # Centralized AI service layer
    prompt-manager.js           # Template-based prompt management
    config-manager.js           # Configuration resolution
    utils/                      # Context gathering, fuzzy search
  mcp-server/                   # MCP server (FastMCP-based)
    src/core/direct-functions/  # Each MCP tool maps to a "direct function"
    src/tools/                  # MCP tool registrations (parameter schemas, descriptions)
  packages/
    tm-core/                    # New TypeScript core (in progress migration)
      modules/workflow/         # TDD workflow state machine
      modules/loop/             # Autopilot loop service
      modules/tasks/            # Task entity, repository interfaces
      modules/storage/          # File-based and API-based storage
      modules/config/           # Configuration management
      modules/git/              # Git branch/commit generation
    tm-bridge/                  # Bridge for remote API storage
    claude-code-plugin/         # Claude Code plugin integration
```

### 2.2 Data Model

Tasks are stored in a JSON file (`.taskmaster/tasks/tasks.json`). The core task schema:

```javascript
{
  id: number,               // Sequential integer
  title: string,            // Max 200 chars
  description: string,      // Detailed description
  status: "pending" | "in-progress" | "done" | "review" | "deferred" | "cancelled" | "blocked",
  priority: "low" | "medium" | "high" | "critical",
  dependencies: number[],   // IDs of tasks this depends on
  details: string | null,   // Implementation details
  testStrategy: string | null,
  subtasks: Subtask[],      // Nested subtasks with same structure
  metadata: Record<string, unknown>,  // User-defined, preserved across AI updates
  // Complexity analysis fields (populated by analyze-complexity):
  complexity: { score: number, ... },
  recommendedSubtasks: number,
  expansionPrompt: string,
  complexityReasoning: string,
}
```

Subtasks use a dotted ID notation (`parentId.subtaskId`, e.g., "3.2") and have the same core fields minus some optional ones.

### 2.3 Tag System

Tasks can be organized into "tags" (essentially named task lists/workspaces). Each tag has its own `tasks.json` under `.taskmaster/tasks/`. The `state.json` file tracks which tag is active. This is useful for parallel workstreams.

---

## 3. Key Design Patterns and Techniques

### 3.1 PRD-to-Task Decomposition Pipeline

The full pipeline from requirements to execution:

1. **Parse PRD** (`parse-prd`): User provides a PRD document. AI reads it and generates N top-level tasks with descriptions, dependencies, test strategies, and implementation details. Supports streaming (with automatic fallback to non-streaming) and append mode for incremental PRD additions.

2. **Analyze Complexity** (`analyze-complexity`): AI scores each task 1-10 on complexity, recommends number of subtasks, and generates an "expansion prompt" for each task. Results are cached in a complexity report JSON file and merged incrementally.

3. **Expand Tasks** (`expand-task`): For each task, the complexity report's `recommendedSubtasks` count and `expansionPrompt` are fed to the AI to generate subtasks. Subtasks are appended (not replaced) by default. Force flag clears and regenerates.

4. **Scope Adjustment** (`scope-up` / `scope-down`): AI can dynamically adjust task scope. Scope-down simplifies tasks (with light/regular/heavy strength levels). Scope-up adds detail and complexity. Both preserve work already in progress.

5. **Next Task Selection** (`next-task`): Algorithm finds the best next task to work on by checking dependency satisfaction, then sorting by priority > dependency count > ID. Prefers subtasks of in-progress parents over top-level tasks.

6. **Execution** (via autopilot loop or manual): The loop service spawns Claude Code CLI iterations, each working on the next available task.

### 3.2 Structured AI Interaction Pattern

All AI interactions follow a consistent pattern using `generateObjectService`:

```
Prompt Template (JSON) -> PromptManager.loadPrompt() -> Variable interpolation
                                                     -> Variant selection (default/research/complexity-report)
                       -> generateObjectService()    -> Provider selection (main/research/fallback roles)
                                                     -> Zod schema validation of response
                                                     -> Telemetry/cost tracking
```

The prompt templates are JSON files with:
- Declared parameters with types, defaults, and validation
- Multiple prompt variants (default, research, complexity-report)
- Handlebars-style template syntax (`{{#if useResearch}}...{{/if}}`, `{{{json tasks}}}`)
- JSON Schema validation of the template structure itself

Responses are always validated against Zod schemas (e.g., `ExpandTaskResponseSchema`) which enforces `.strict()` for OpenAI compatibility.

### 3.3 Context Gathering System

Before making AI calls, the system gathers relevant context:

1. **ContextGatherer**: Loads all tasks, can include project file tree, specific files, and custom context. Counts tokens to manage context window budgets.

2. **FuzzyTaskSearch**: Uses Fuse.js for semantic similarity search across tasks. Different configurations for different operations (research=lenient, add-task=strict). Searches across title (2x weight), description (1.5x), details (1x), dependency titles (0.5x).

3. **Combined context**: For expand-task, the system searches for the 5 most relevant tasks, gathers their full context, and combines it with the complexity report reasoning and any user-provided additional context.

### 3.4 Provider Abstraction

The provider system is particularly well-designed:

- **Base provider class** with abstract methods for model creation
- **18+ concrete providers** each handling API key resolution, model mapping, and provider-specific quirks
- **Provider Registry** (singleton) for dynamic runtime registration
- **Three roles**: `main` (primary generation), `research` (deeper analysis, often Perplexity), `fallback` (backup provider)
- **MCP Provider**: When running as an MCP server, can use the host client's sampling capability as an AI provider

### 3.5 MCP Server Architecture

The MCP server exposes ~40 tools organized into tiers:

- **Core tools** (lean/default): `get_tasks`, `get_task`, `next_task`, `set_task_status`, `update_task`, `update_subtask`, `add_task`, `expand_task`, `scope_up_task`, `scope_down_task`, `add_subtask`
- **Standard tools**: Core + complexity analysis, dependency management, PRD parsing
- **All tools**: Standard + tag management, project init, model management, research

Each tool has a registration function that defines its FastMCP parameters, description, and execution handler. The handler calls the corresponding "direct function" which wraps the core business logic with path resolution, error handling, and silent mode management.

### 3.6 Workflow State Machine (tm-core)

The newer TypeScript core includes a sophisticated workflow orchestrator:

- **Phases**: PREFLIGHT -> BRANCH_SETUP -> SUBTASK_LOOP -> FINALIZE -> COMPLETE
- **TDD Cycle**: Within SUBTASK_LOOP, each subtask goes through RED -> GREEN -> COMMIT
- **Event system**: ~25 event types (workflow:started, tdd:red:completed, subtask:failed, git:commit:created, etc.)
- **State persistence**: Auto-persist callback system for crash recovery
- **Guard conditions**: Phase-specific guards that can prevent transitions
- **Abort/Retry**: Handles abort and retry at both workflow and subtask levels
- **Max attempts**: Tracks attempts per subtask with configurable max

### 3.7 Autopilot Loop

The loop service (`LoopDomain` / `LoopService`) orchestrates unattended task execution:

- Spawns Claude Code CLI (or Docker sandbox) in iterations
- Each iteration gets a prompt built from: context header + progress file + preset
- Presets: `default` (work on next task), `duplication` (find/fix code duplication), `entropy` (reduce complexity), `linting`, `test-coverage`
- Parses output for `<loop-complete>` or `<loop-blocked>` sentinel tags
- Tracks progress in a text file, appends summaries
- Supports verbose mode with real-time streaming of Claude's output
- Configurable sleep between iterations

---

## 4. Strengths

### 4.1 Excellent Task Decomposition Model
The three-phase approach (PRD -> Complexity Analysis -> Task Expansion) is genuinely clever. Rather than trying to decompose everything at once, it first creates a flat task list, then separately analyzes complexity to determine which tasks need breaking down, and finally expands them with complexity-informed prompts. This is more reliable than single-shot decomposition.

### 4.2 Complexity-Driven Expansion
The complexity scoring system (1-10) with per-task expansion prompts is a standout feature. The AI generates not just a score but a specific prompt for how to expand each task. This means the expansion step has domain-specific guidance rather than generic "break this into subtasks" instructions.

### 4.3 Scope Adjustment
The scope-up/scope-down feature with strength levels (light/regular/heavy) is unique. It preserves work already in progress while adjusting pending items. This handles a real-world problem: initial estimates are often wrong.

### 4.4 Rich Context Gathering
The combination of fuzzy search, dependency chain walking, token counting, and file context creates a sophisticated context window management system. Before any AI call, the system gathers the most relevant information and stays within token budgets.

### 4.5 Provider Abstraction
Supporting 18+ providers with a clean base class pattern is impressive. The three-role system (main/research/fallback) is practical -- different operations benefit from different models.

### 4.6 MCP-First Design
Making every operation available as an MCP tool means AI assistants can self-manage their task lists. The tiered tool exposure (core/standard/all) is thoughtful for managing tool overload.

### 4.7 Prompt Template System
JSON-based prompt templates with parameter schemas, variant selection, and Handlebars interpolation create a maintainable, versionable prompt management system.

### 4.8 Incremental Operation
Almost everything supports incremental operation: PRD append mode, complexity report merging, subtask appending. This is critical for real-world usage where work is ongoing.

---

## 5. Weaknesses and Limitations

### 5.1 File-Based Storage
Tasks are stored as flat JSON files. This creates concurrency issues (read-modify-write without locking), doesn't scale well, and makes querying expensive. The project acknowledges this by building API-based storage, but the core still depends on file I/O.

### 5.2 Numeric Sequential IDs
Task IDs are sequential integers. This makes parallel task creation fragile, doesn't support distributed operation, and the subtask dotted notation (`3.2`) is awkward. The newer tm-core uses string IDs, showing awareness of this limitation.

### 5.3 Legacy JS / New TS Split
The codebase is mid-migration from JavaScript (scripts/modules/) to TypeScript (packages/tm-core/). The legacy code does the actual work while the new code provides better abstractions but incomplete coverage. This creates confusion about where to find implementations and means the architecture benefits aren't fully realized.

### 5.4 No True DAG Execution Engine
While tasks declare dependencies, there's no parallel execution engine that runs independent tasks concurrently. The `next-task` command returns one task at a time. For an orchestrator, this is a significant limitation.

### 5.5 Silent Mode Hack
The pattern of `enableSilentMode()` / `disableSilentMode()` to prevent console.log from interfering with MCP JSON responses is fragile. Every direct function has boilerplate try/finally blocks for this. A proper separation of concerns (structured logging vs. output) would be cleaner.

### 5.6 No Real-Time Dependency Updates
When a task's status changes, dependent tasks aren't automatically unblocked or notified. The system relies on the next `next-task` call to discover newly available work.

### 5.7 Limited Error Recovery
While the workflow orchestrator has retry/abort, the core task operations don't have sophisticated error recovery. A failed AI call during expansion leaves the task in an intermediate state.

### 5.8 Flat Task Hierarchy
Only two levels: tasks and subtasks. No deeper nesting. For complex projects, this is limiting. The system works around this with the scope-up/scope-down features but doesn't support arbitrary depth.

---

## 6. Patterns Applicable to Our Conductor Project

### 6.1 Three-Phase Decomposition Pipeline

**Pattern**: Separate decomposition into distinct phases rather than trying to do it all at once.

Our conductor's decomposer could adopt this approach:
1. **Phase 1 - Initial decomposition**: Convert the user's goal into a flat list of high-level tasks
2. **Phase 2 - Complexity analysis**: Score each task and determine which need further breakdown
3. **Phase 3 - Selective expansion**: Only expand tasks that exceed a complexity threshold

This is more token-efficient and produces better results than one-shot deep decomposition.

### 6.2 Complexity Scoring with Expansion Prompts

**Pattern**: When analyzing complexity, generate not just a score but also a specific prompt for how to break down each complex task.

```python
class ComplexityAnalysis:
    task_id: str
    complexity_score: int  # 1-10
    recommended_subtasks: int
    expansion_prompt: str  # "Focus on separating the auth middleware from the route handlers..."
    reasoning: str
```

This means the expansion step has task-specific guidance rather than generic instructions.

### 6.3 Fuzzy Context Gathering

**Pattern**: Before any AI call, use fuzzy search to find the most relevant existing tasks and include them as context.

For conductor, when decomposing a new goal or reviewing completed work, fuzzy-search the existing task graph to find related tasks. This prevents duplicate work and ensures consistency.

### 6.4 Structured AI Response Validation

**Pattern**: Use schema validation (Zod/Pydantic) for all AI responses. Define strict schemas and reject invalid responses.

Task Master's approach of defining Zod schemas per command and using `generateObject` is directly applicable. For conductor, every AI call (decomposition, review, delegation) should have a validated response schema.

### 6.5 Prompt Template System

**Pattern**: Store prompts as structured data (JSON/YAML) with declared parameters, variants, and template interpolation. Cache rendered prompts.

```json
{
  "id": "decompose-goal",
  "parameters": { "goal": { "type": "string", "required": true } },
  "prompts": {
    "default": { "system": "...", "user": "..." },
    "research": { "system": "...", "user": "..." }
  }
}
```

### 6.6 MCP Tool Tiers

**Pattern**: When exposing MCP tools, organize them into tiers (core/standard/all) to prevent tool overload for AI assistants.

Conductor's MCP integration should expose only essential tools by default and allow configuration to unlock advanced tools.

### 6.7 Next-Task Selection Algorithm

**Pattern**: Deterministic algorithm for selecting the next work item:
1. Prefer subtasks of in-progress parents
2. Filter by dependency satisfaction (all deps must be done)
3. Sort by priority (high > medium > low)
4. Break ties by dependency count (fewer deps = easier to start)
5. Break remaining ties by ID (lowest first for determinism)

This is directly applicable to conductor's task scheduling.

### 6.8 Scope Adjustment Operations

**Pattern**: Support dynamic scope modification with strength levels and work preservation.

For conductor, after initial decomposition, allow scope-up (add detail) and scope-down (simplify) operations that preserve work already completed or in progress. Use AI to regenerate only pending items.

### 6.9 Tag-Based Workspaces

**Pattern**: Support multiple named task lists (tags/workspaces) within a project.

For conductor, this maps to supporting multiple orchestration sessions or parallel workstreams within the same project.

### 6.10 Workflow State Machine with TDD Cycle

**Pattern**: Use a proper state machine for workflow orchestration with well-defined phases, transitions, guards, and event emission.

The PREFLIGHT -> BRANCH_SETUP -> SUBTASK_LOOP (RED/GREEN/COMMIT) -> FINALIZE -> COMPLETE pattern is a good model. Key features to adopt:
- Auto-persistence after each transition for crash recovery
- Guard conditions to prevent invalid transitions
- Max attempt tracking per subtask
- Event system for UI updates and logging

### 6.11 Autopilot Loop with Sentinel Tags

**Pattern**: For unattended execution, run an AI agent in a loop with sentinel tags in output to signal completion or blocking.

Task Master uses `<loop-complete>` and `<loop-blocked>` tags that the AI writes to signal state. This is a simple but effective protocol for agentic loops.

---

## 7. Notable Code Implementations

### 7.1 Next-Task Selection (find-next-task.js)

The two-pass approach -- first checking subtasks of in-progress parents, then falling back to top-level tasks -- is elegant:

```javascript
// Pass 1: Find subtasks of in-progress parent tasks
tasks.filter(t => t.status === 'in-progress' && Array.isArray(t.subtasks))
  .forEach(parent => {
    parent.subtasks.forEach(st => {
      // Check deps satisfied (converting local IDs to full dotted IDs)
      const fullDeps = st.dependencies?.map(d => toFullSubId(parent.id, d)) ?? [];
      const depsSatisfied = fullDeps.every(depId => completedIds.has(String(depId)));
      if (depsSatisfied) candidateSubtasks.push({...});
    });
  });

// Pass 2: Fall back to top-level tasks
if (candidateSubtasks.length === 0) {
  const eligibleTasks = tasks.filter(task => {
    const deps = task.dependencies ?? [];
    return deps.every(depId => completedIds.has(String(depId)));
  });
  // Sort by priority > dep count > ID
}
```

### 7.2 Complexity-Informed Expansion

The expand-task module uses the complexity report to determine both the number of subtasks and the expansion prompt:

```javascript
// Use complexity report data if available
if (taskAnalysis?.recommendedSubtasks) {
  finalSubtaskCount = parseInt(taskAnalysis.recommendedSubtasks, 10);
}

// Select prompt variant based on available data
if (expansionPromptText) {
  variantKey = 'complexity-report';  // Uses the AI-generated expansion guidance
} else if (useResearch) {
  variantKey = 'research';
}
```

### 7.3 Prompt Template Architecture

Prompt templates as JSON with parameter declarations enable validation and caching:

```json
{
  "id": "analyze-complexity",
  "parameters": {
    "tasks": { "type": "array", "required": true },
    "hasCodebaseAnalysis": { "type": "boolean", "default": false }
  },
  "prompts": {
    "default": {
      "system": "You are an expert software architect...",
      "user": "{{#if hasCodebaseAnalysis}}## Codebase Analysis Required\n...{{/if}}Analyze: {{{json tasks}}}"
    }
  }
}
```

### 7.4 Workflow State Machine Transitions

The WorkflowOrchestrator's TDD phase handling within SUBTASK_LOOP is well-structured:

```typescript
case 'RED_PHASE_COMPLETE':
  // Special case: All tests passing means feature already implemented
  if (event.testResults.failed === 0) {
    this.emit('tdd:feature-already-implemented', { ... });
    subtask.status = 'completed';
    this.context.currentSubtaskIndex++;
    // Skip GREEN/COMMIT, go straight to next subtask
    if (moreSubtasks) { this.context.currentTDDPhase = 'RED'; }
    else { await this.transition({ type: 'ALL_SUBTASKS_COMPLETE' }); }
    break;
  }
  // Normal path: proceed to GREEN
  this.context.currentTDDPhase = 'GREEN';
```

### 7.5 Scope Preservation During Adjustment

When scope-down regenerates subtasks, it preserves work in progress:

```javascript
const PRESERVE_STATUSES = ['done', 'in-progress', 'review', 'cancelled', 'deferred', 'blocked'];
const REGENERATE_STATUSES = ['pending'];
// Only regenerate subtasks with pending status; preserve all others
```

---

## 8. Summary of Key Takeaways for Conductor

| Task Master Feature | Conductor Application | Priority |
|---|---|---|
| Three-phase decomposition (Parse -> Analyze -> Expand) | Refactor decomposer into phased pipeline | High |
| Complexity scoring with expansion prompts | Add complexity analysis before expansion | High |
| Fuzzy context gathering before AI calls | Improve context injection for decomposer/reviewer | High |
| Zod/schema-validated AI responses | Add Pydantic validation for all AI responses | High |
| Next-task selection algorithm | Implement priority-based task scheduling | Medium |
| Scope up/down operations | Add scope adjustment to orchestrator | Medium |
| JSON prompt templates with variants | Externalize prompts from code into templates | Medium |
| Workflow state machine (TDD phases) | Adopt state machine pattern for orchestrator | Medium |
| MCP tool tiers | Organize conductor tools into tiers | Low |
| Tag-based workspaces | Support parallel orchestration sessions | Low |
| Autopilot loop with sentinel tags | Enhance conductor's autonomous mode | Low |

The most impactful patterns to adopt are the **phased decomposition pipeline** and **complexity-driven expansion**. These directly address the quality of task breakdown, which is the most critical function of an orchestrator.
