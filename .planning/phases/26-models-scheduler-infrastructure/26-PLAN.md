---
phase: 26-models-scheduler-infrastructure
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/src/conductor/orchestrator/models.py
  - packages/conductor-core/src/conductor/orchestrator/scheduler.py
  - packages/conductor-core/src/conductor/orchestrator/__init__.py
  - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
  - packages/conductor-core/tests/test_scheduler.py
  - packages/conductor-core/tests/test_orchestrator_models.py
autonomous: true
requirements: [INFRA-01, INFRA-02, MODEL-01]

must_haves:
  truths:
    - "scheduler.compute_waves() returns list of lists grouping concurrent task IDs"
    - "OrchestratorConfig model exists with max_review_iterations and max_decomposition_retries fields"
    - "Orchestrator reads from OrchestratorConfig instead of hardcoded defaults"
    - "ModelProfile model exists with role-to-model mapping and quality/balanced/budget presets"
    - "All existing tests still pass after changes"
  artifacts:
    - path: "packages/conductor-core/src/conductor/orchestrator/models.py"
      provides: "OrchestratorConfig, ModelProfile, AgentRole enum"
      contains: "class OrchestratorConfig"
    - path: "packages/conductor-core/src/conductor/orchestrator/scheduler.py"
      provides: "compute_waves() method on DependencyScheduler"
      contains: "def compute_waves"
    - path: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      provides: "Orchestrator accepting OrchestratorConfig"
      contains: "OrchestratorConfig"
  key_links:
    - from: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      to: "packages/conductor-core/src/conductor/orchestrator/models.py"
      via: "import OrchestratorConfig"
      pattern: "from conductor\\.orchestrator\\.models import.*OrchestratorConfig"
    - from: "packages/conductor-core/src/conductor/orchestrator/__init__.py"
      to: "packages/conductor-core/src/conductor/orchestrator/models.py"
      via: "re-export new models"
      pattern: "OrchestratorConfig.*ModelProfile"
---

<objective>
Add foundational data models (OrchestratorConfig, ModelProfile) and compute_waves() to the scheduler, then wire OrchestratorConfig into the Orchestrator constructor so hardcoded defaults are replaced.

Purpose: Phase 27-30 all depend on these models and the wave computation. This is pure infrastructure -- no behavioral changes to the spawn loop.
Output: Updated models.py, scheduler.py, orchestrator.py, __init__.py, and new tests.
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md

<interfaces>
<!-- Key types and contracts the executor needs. Extracted from codebase. -->

From packages/conductor-core/src/conductor/orchestrator/models.py:
```python
class TaskSpec(BaseModel):
    id: str
    title: str
    description: str
    role: str
    target_file: str
    material_files: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)

class TaskPlan(BaseModel):
    feature_name: str
    tasks: list[TaskSpec]
    max_agents: int = Field(default=4, ge=1, le=10)
```

From packages/conductor-core/src/conductor/orchestrator/scheduler.py:
```python
class DependencyScheduler:
    def __init__(self, graph: dict[str, set[str]]) -> None: ...
    def get_ready(self) -> tuple[str, ...]: ...
    def done(self, task_id: str) -> None: ...
    def is_active(self) -> bool: ...
```

From packages/conductor-core/src/conductor/orchestrator/orchestrator.py:
```python
class Orchestrator:
    def __init__(
        self,
        state_manager: StateManager,
        repo_path: str,
        mode: str = "auto",
        human_out: asyncio.Queue | None = None,
        human_in: asyncio.Queue | None = None,
        max_agents: int = 10,
        max_revisions: int = 2,
        build_command: str | None = None,
    ) -> None: ...
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add OrchestratorConfig, ModelProfile models and compute_waves() method</name>
  <files>
    packages/conductor-core/src/conductor/orchestrator/models.py,
    packages/conductor-core/src/conductor/orchestrator/scheduler.py,
    packages/conductor-core/src/conductor/orchestrator/__init__.py,
    packages/conductor-core/tests/test_orchestrator_models.py,
    packages/conductor-core/tests/test_scheduler.py
  </files>
  <behavior>
    OrchestratorConfig:
    - OrchestratorConfig() creates instance with max_review_iterations=2, max_decomposition_retries=3, max_agents=10
    - OrchestratorConfig(max_review_iterations=5) overrides default
    - OrchestratorConfig(max_decomposition_retries=1) overrides default
    - JSON round-trip preserves all fields

    ModelProfile:
    - AgentRole enum has at least: decomposer, reviewer, executor, verifier
    - ModelProfile has name: str and role_models: dict[AgentRole, str]
    - ModelProfile.get_model(AgentRole.executor) returns the mapped model string
    - ModelProfile.get_model(role_not_in_map) returns a sensible default (the executor model)
    - ModelProfile.quality() class method returns profile with claude-sonnet-4-20250514 for all roles
    - ModelProfile.balanced() class method returns profile with claude-sonnet-4-20250514 for decomposer/reviewer and claude-haiku-35-20241022 for executor/verifier
    - ModelProfile.budget() class method returns profile with claude-haiku-35-20241022 for all roles

    compute_waves:
    - DependencyScheduler({"a": set(), "b": set()}).compute_waves() returns [["a", "b"]] (single wave, both concurrent) -- order within wave doesn't matter, use sets for comparison
    - DependencyScheduler({"a": set(), "b": {"a"}}).compute_waves() returns [["a"], ["b"]] (two waves)
    - DependencyScheduler({"a": set(), "b": set(), "c": {"a", "b"}, "d": {"c"}}).compute_waves() returns [["a","b"], ["c"], ["d"]] (three waves)
    - DependencyScheduler({}).compute_waves() returns [] (empty graph)
    - compute_waves() does NOT consume the scheduler -- get_ready() and done() still work after calling compute_waves()
  </behavior>
  <action>
    1. In models.py, add an `AgentRole` StrEnum with values: decomposer, reviewer, executor, verifier.

    2. In models.py, add `OrchestratorConfig(BaseModel)` with fields:
       - max_review_iterations: int = 2
       - max_decomposition_retries: int = 3
       - max_agents: int = 10
       Keep it simple -- just data, no methods.

    3. In models.py, add `ModelProfile(BaseModel)` with fields:
       - name: str
       - role_models: dict[AgentRole, str] = Field(default_factory=dict)
       Add method `get_model(role: AgentRole) -> str` that returns role_models.get(role, role_models.get(AgentRole.executor, "claude-sonnet-4-20250514"))
       Add class methods: quality(), balanced(), budget() returning preset profiles.
       Model names to use:
       - quality: claude-sonnet-4-20250514 for all roles
       - balanced: claude-sonnet-4-20250514 for decomposer+reviewer, claude-haiku-35-20241022 for executor+verifier
       - budget: claude-haiku-35-20241022 for all roles

    4. In scheduler.py, add `compute_waves(self) -> list[list[str]]` to DependencyScheduler.
       This must NOT consume the internal TopologicalSorter. Instead, create a SECOND TopologicalSorter from the same graph data.
       Store the original graph dict in `self._graph` during __init__ so compute_waves can rebuild a fresh sorter.
       Algorithm: prepare a new sorter, loop calling get_ready()/done() on the copy, collecting each batch as a wave.

    5. In __init__.py, add OrchestratorConfig, ModelProfile, AgentRole to imports and __all__.

    6. Write tests in test_orchestrator_models.py for OrchestratorConfig (defaults, override, round-trip) and ModelProfile (presets, get_model, get_model fallback).

    7. Write tests in test_scheduler.py in a new TestComputeWaves class covering the behaviors above.

    IMPORTANT: Do NOT modify the Orchestrator class in this task -- that is Task 2.
    IMPORTANT: Do NOT change any existing model fields or defaults -- only ADD new models.
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto && python -m pytest packages/conductor-core/tests/test_orchestrator_models.py packages/conductor-core/tests/test_scheduler.py -x -v 2>&1 | tail -40</automated>
  </verify>
  <done>
    - OrchestratorConfig model exists with max_review_iterations=2, max_decomposition_retries=3, max_agents=10 defaults
    - ModelProfile model exists with quality/balanced/budget presets and get_model() method
    - AgentRole enum exists with decomposer, reviewer, executor, verifier values
    - compute_waves() on DependencyScheduler returns list of lists grouping concurrent task IDs
    - All new and existing tests pass
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire OrchestratorConfig into Orchestrator constructor</name>
  <files>
    packages/conductor-core/src/conductor/orchestrator/orchestrator.py,
    packages/conductor-core/tests/test_orchestrator.py
  </files>
  <action>
    1. In orchestrator.py, import OrchestratorConfig from conductor.orchestrator.models.

    2. Add an optional `config: OrchestratorConfig | None = None` parameter to Orchestrator.__init__,
       AFTER build_command. If None, create a default OrchestratorConfig().

    3. Store as self._config = config or OrchestratorConfig().

    4. Replace self._max_revisions assignment: instead of using the max_revisions parameter directly,
       use `config.max_review_iterations` as the source of truth. BUT keep the existing max_revisions
       parameter for backward compatibility -- if max_revisions is explicitly passed (not the default 2),
       it takes precedence over config. Implementation:
       ```python
       self._config = config or OrchestratorConfig()
       # Explicit max_revisions param overrides config (backward compat)
       if max_revisions != 2:  # non-default means explicitly set
           self._max_revisions = max_revisions
       else:
           self._max_revisions = self._config.max_review_iterations
       ```
       Same pattern for max_agents:
       ```python
       if max_agents != 10:
           self._max_agents = max_agents
       else:
           self._max_agents = self._config.max_agents
       ```

    5. Do NOT change the spawn loop, do NOT use compute_waves() yet, do NOT change agent prompts.
       The spawn loop changes are Phase 27 scope.

    6. Add a test in test_orchestrator.py verifying that Orchestrator can be constructed with
       an OrchestratorConfig and that the config values are accessible. Use a simple unit test
       that constructs Orchestrator with a mock state_manager and a custom config, then checks
       self._max_revisions and self._max_agents reflect the config values. Also test that
       passing explicit max_revisions still overrides the config.

    7. Run the FULL test suite to confirm no regressions:
       `python -m pytest packages/conductor-core/tests/ -x`
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto && python -m pytest packages/conductor-core/tests/ -x -v 2>&1 | tail -50</automated>
  </verify>
  <done>
    - Orchestrator accepts optional config: OrchestratorConfig parameter
    - Default construction (no config) behaves identically to before (max_revisions=2, max_agents=10)
    - Config values flow through to _max_revisions and _max_agents
    - Explicit max_revisions/max_agents parameters still override config (backward compat)
    - ALL existing orchestrator tests pass unchanged
  </done>
</task>

</tasks>

<verification>
1. `python -m pytest packages/conductor-core/tests/ -x -v` -- all tests pass (existing + new)
2. `python -c "from conductor.orchestrator import OrchestratorConfig, ModelProfile, AgentRole; print('imports OK')"` -- new models importable from public API
3. `python -c "from conductor.orchestrator import DependencyScheduler; w = DependencyScheduler({'a': set(), 'b': {'a'}}).compute_waves(); assert w == [['a'], ['b']] or [set(x) for x in w] == [{'a'}, {'b'}]; print('compute_waves OK')"` -- wave computation works
4. `python -c "from conductor.orchestrator import ModelProfile; p = ModelProfile.quality(); print(p.name, p.get_model(p.role_models.__iter__().__next__()))"` -- presets work
</verification>

<success_criteria>
- OrchestratorConfig, ModelProfile, AgentRole are importable from conductor.orchestrator
- compute_waves() returns correct wave groupings for all dependency patterns
- Orchestrator constructor accepts OrchestratorConfig and uses it for defaults
- Backward compatibility: all pre-existing tests pass without modification
- No changes to spawn loop, agent prompts, or execution behavior
</success_criteria>

<output>
After completion, create `.planning/phases/26-models-scheduler-infrastructure/26-01-SUMMARY.md`
</output>
