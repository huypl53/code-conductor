---
phase: 27-execution-routing-pipeline
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/src/conductor/acp/client.py
  - packages/conductor-core/src/conductor/orchestrator/identity.py
  - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
  - packages/conductor-core/tests/test_orchestrator.py
autonomous: true
requirements: [WAVE-01, ROUTE-01, LEAN-01]

must_haves:
  truths:
    - "run() spawns all tasks in a wave concurrently and waits for the wave to complete before starting the next"
    - "ACPClient accepts an optional model parameter and passes it to ClaudeAgentOptions"
    - "Orchestrator passes ModelProfile role-specific model to each ACPClient instance"
    - "Agent system prompts contain file paths only, not file content, and stay under 500 tokens"
    - "All existing tests still pass with new tests covering wave execution and model routing"
  artifacts:
    - path: "packages/conductor-core/src/conductor/acp/client.py"
      provides: "ACPClient with optional model param"
      contains: "model"
    - path: "packages/conductor-core/src/conductor/orchestrator/identity.py"
      provides: "Lean system prompt builder"
      contains: "build_system_prompt"
    - path: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      provides: "Wave-based spawn loop and model routing"
      contains: "compute_waves"
    - path: "packages/conductor-core/tests/test_orchestrator.py"
      provides: "Tests for wave execution and model routing"
      contains: "wave"
  key_links:
    - from: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      to: "packages/conductor-core/src/conductor/orchestrator/scheduler.py"
      via: "scheduler.compute_waves() called in run()"
      pattern: "compute_waves"
    - from: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      to: "packages/conductor-core/src/conductor/acp/client.py"
      via: "ACPClient instantiated with model= kwarg"
      pattern: "ACPClient.*model="
    - from: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      to: "packages/conductor-core/src/conductor/orchestrator/models.py"
      via: "ModelProfile.get_model() called for role routing"
      pattern: "get_model"
---

<objective>
Replace the orchestrator's FIRST_COMPLETED spawn loop with wave-based parallel execution, add model routing through ACPClient, and make agent system prompts context-lean.

Purpose: Wave execution maximizes parallelism by spawning all independent tasks simultaneously. Model routing enables cost control by assigning cheaper models to simpler roles. Lean prompts preserve agent context windows by letting agents read files themselves.

Output: Modified orchestrator with wave-based run(), ACPClient with model param, lean identity prompts, and comprehensive tests.
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/26-models-scheduler-infrastructure/26-01-SUMMARY.md

<interfaces>
<!-- Key types and contracts the executor needs -->

From packages/conductor-core/src/conductor/orchestrator/models.py:
```python
class AgentRole(StrEnum):
    decomposer = "decomposer"
    reviewer = "reviewer"
    executor = "executor"
    verifier = "verifier"

class ModelProfile(BaseModel):
    name: str
    role_models: dict[AgentRole, str] = Field(default_factory=dict)
    def get_model(self, role: AgentRole) -> str: ...

class OrchestratorConfig(BaseModel):
    max_review_iterations: int = 2
    max_decomposition_retries: int = 3
    max_agents: int = 10
```

From packages/conductor-core/src/conductor/orchestrator/scheduler.py:
```python
class DependencyScheduler:
    def compute_waves(self) -> list[list[str]]: ...
    def get_ready(self) -> tuple[str, ...]: ...
    def done(self, task_id: str) -> None: ...
    def is_active(self) -> bool: ...
```

From claude_agent_sdk (installed SDK):
```python
class ClaudeAgentOptions:
    model: str | None = None  # Already supported by SDK
```

From packages/conductor-core/src/conductor/orchestrator/identity.py:
```python
class AgentIdentity(BaseModel):
    name: str
    role: str
    target_file: str
    material_files: list[str]
    task_id: str
    task_description: str

def build_system_prompt(identity: AgentIdentity) -> str: ...
```
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: ACPClient model parameter and lean system prompts</name>
  <files>
    packages/conductor-core/src/conductor/acp/client.py
    packages/conductor-core/src/conductor/orchestrator/identity.py
  </files>
  <action>
**ACPClient model param (ROUTE-01 foundation):**

In `client.py`, add an optional `model: str | None = None` parameter to `ACPClient.__init__()` after `max_turns`. Store as `self._model`. In the `ClaudeAgentOptions` construction (line ~74), pass `model=model` if not None. Since `ClaudeAgentOptions` already has a `model` field, just add it:

```python
def __init__(
    self,
    *,
    cwd: str,
    system_prompt: str = "",
    resume: str | None = None,
    allowed_tools: list[str] | None = None,
    permission_handler: PermissionHandler | None = None,
    max_turns: int = _DEFAULT_MAX_TURNS,
    model: str | None = None,
    setting_sources: list[SettingSource] | None = None,
) -> None:
```

Then in the `ClaudeAgentOptions(...)` constructor call, add `model=model` alongside the other kwargs. The SDK accepts `model: str | None = None` natively.

**Lean system prompts (LEAN-01):**

In `identity.py`, rewrite `build_system_prompt()` to produce a concise prompt that:
1. States agent name and role (1 line)
2. States task ID (1 line)
3. States target file path (1 line)
4. Lists material file paths as "Read these files for context:" with paths only (no content)
5. States memory file path (1 line)
6. States file boundary rule (1 line)

Remove the verbose task description from the system prompt entirely — the task description is already sent as the first user message in `_run_agent_loop` via `client.send(f"Task {task_spec.id}: {task_spec.description}")`.

The prompt should look like:
```
You are {name}, a {role}.

Task: {task_id}
Target file: {target_file}

Read these files for context:
  - {file1}
  - {file2}

Memory: .memory/{name}.md — write decisions here, read other agents' at .memory/.

Stay within your target file and memory file. Do not modify other files.
```

If no material files, omit that section. The entire prompt must stay under 500 tokens (~375 words). The current prompt is already relatively lean but includes task_description which can be arbitrarily long — removing it is the key change.
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto && python -m pytest packages/conductor-core/tests/ -x -q 2>&1 | tail -5</automated>
  </verify>
  <done>ACPClient constructor accepts model param and passes it to ClaudeAgentOptions. build_system_prompt() returns a lean prompt with file paths only, no task description, under 500 tokens.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Wave-based spawn loop, model routing, and tests</name>
  <files>
    packages/conductor-core/src/conductor/orchestrator/orchestrator.py
    packages/conductor-core/tests/test_orchestrator.py
  </files>
  <behavior>
    - Test: run() with 3 tasks (A independent, B independent, C depends on A+B) executes A+B concurrently in wave 1 then C in wave 2
    - Test: ACPClient is instantiated with model= kwarg matching ModelProfile.get_model() for the task's role
    - Test: run() with no model_profile uses default (no model kwarg passed to ACPClient)
    - Test: build_system_prompt produces prompt under 500 tokens and does not contain task_description text
    - Test: ACPClient model=None backward compat (no model kwarg passed to SDK options)
  </behavior>
  <action>
**Add model_profile to Orchestrator (ROUTE-01 wiring):**

In `orchestrator.py`, add `model_profile: ModelProfile | None = None` parameter to `__init__()`. Store as `self._model_profile`. Import `ModelProfile` and `AgentRole` from `conductor.orchestrator.models`.

**Refactor run() to wave-based execution (WAVE-01):**

Replace the current FIRST_COMPLETED spawn loop (lines 202-234) with wave-based execution:

```python
# 6. Compute waves for parallel execution
waves = scheduler.compute_waves()

# 7. Execute wave by wave
for wave in waves:
    # Spawn all tasks in this wave concurrently
    coros = []
    for task_id in wave:
        task_spec = task_map[task_id]
        coros.append(self._run_agent_loop(task_spec, sem))

    # Wait for entire wave to complete
    results = await asyncio.gather(*coros, return_exceptions=True)

    # Log any failures
    for task_id, result in zip(wave, results):
        if isinstance(result, Exception):
            logger.error("Task %s failed: %s", task_id, result)
```

Remove the `pending` dict, `done_futures` loop, and `FIRST_COMPLETED` pattern from `run()`. The stragglers cleanup at the end is also no longer needed since `gather` waits for all.

Keep `self._active_tasks` tracking — populate before gather, clean up after. For each task in a wave, create the asyncio.Task, store in `_active_tasks`, then gather those tasks.

**Do NOT change resume()** — it can keep FIRST_COMPLETED (per constraints).

**Wire model routing into _run_agent_loop (ROUTE-01):**

In `_run_agent_loop`, when constructing `ACPClient`, determine the model to use:

```python
# Determine model from profile
model: str | None = None
if self._model_profile:
    # Map task role string to AgentRole enum for lookup
    try:
        agent_role = AgentRole(task_spec.role) if task_spec.role in AgentRole.__members__ else AgentRole.executor
    except ValueError:
        agent_role = AgentRole.executor
    model = self._model_profile.get_model(agent_role)
```

Pass `model=model` to the `ACPClient(...)` constructor call.

**Tests:**

Add a new test class `TestWaveExecution` in `test_orchestrator.py`:

1. `test_run_executes_waves_sequentially`: Create 3 tasks — A (no deps), B (no deps), C (requires A, B). Mock ACPClient and review_output. Track execution order using a shared list with timestamps or ordering markers. Assert A and B start before C. Use `asyncio.gather` timing: patch `_run_agent_loop` to append task_id to a list and sleep briefly, verify order shows wave grouping.

2. `test_run_passes_model_to_acp_client`: Create orchestrator with `model_profile=ModelProfile.balanced()`. Run with a single task (role="executor"). Assert ACPClient was constructed with `model="claude-haiku-35-20241022"` (balanced executor model).

3. `test_run_no_model_profile_omits_model`: Create orchestrator without model_profile. Run with single task. Assert ACPClient was constructed without model kwarg (or model=None).

4. `test_lean_system_prompt_under_500_tokens`: Build an AgentIdentity with a long task_description (500+ chars). Call build_system_prompt(). Assert len(prompt.split()) < 375 (rough 500 token proxy). Assert task_description text is NOT in the prompt.

5. `test_acp_client_model_param`: Create ACPClient with model="claude-haiku-35-20241022". Assert self._options.model == "claude-haiku-35-20241022". Create without model param. Assert self._options.model is None.

Update `_make_mock_acp_client` helper if needed to accept and ignore model param.

Ensure all existing tests still pass — update any that mock ACPClient constructor to accept the new `model` kwarg.
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto && python -m pytest packages/conductor-core/tests/ -x -q 2>&1 | tail -10</automated>
  </verify>
  <done>
    - run() uses compute_waves() and asyncio.gather per wave (no FIRST_COMPLETED)
    - resume() unchanged (still FIRST_COMPLETED)
    - Orchestrator accepts model_profile and passes role-specific model to ACPClient
    - New tests verify wave ordering, model routing, lean prompts, and ACPClient model param
    - All existing tests pass
  </done>
</task>

</tasks>

<verification>
1. `cd /home/huypham/code/digest/claude-auto && python -m pytest packages/conductor-core/tests/ -x -q` — all tests pass
2. `grep -c "FIRST_COMPLETED\|return_when" packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — only appears in resume(), not run()
3. `grep "compute_waves" packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — present in run()
4. `grep "model=" packages/conductor-core/src/conductor/acp/client.py` — model param exists
5. `grep "model_profile" packages/conductor-core/src/conductor/orchestrator/orchestrator.py` — model routing wired
6. `grep "task_description" packages/conductor-core/src/conductor/orchestrator/identity.py` — not embedded in prompt output
</verification>

<success_criteria>
- run() spawns all tasks per wave concurrently via asyncio.gather, advancing wave-by-wave
- resume() is unchanged (still uses FIRST_COMPLETED pattern)
- ACPClient.__init__ accepts model: str | None = None and passes it to ClaudeAgentOptions
- Orchestrator.__init__ accepts model_profile: ModelProfile | None = None
- _run_agent_loop resolves AgentRole from task_spec.role and calls model_profile.get_model() to get model string
- build_system_prompt() produces a prompt with file paths only (no task description content), under 500 tokens
- All existing tests pass; at least 5 new tests cover wave execution, model routing, lean prompts
</success_criteria>

<output>
After completion, create `.planning/phases/27-execution-routing-pipeline/27-01-SUMMARY.md`
</output>
