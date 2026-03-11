---
phase: 28-agent-communication-protocol
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/src/conductor/orchestrator/models.py
  - packages/conductor-core/src/conductor/orchestrator/identity.py
  - packages/conductor-core/src/conductor/orchestrator/monitor.py
  - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
  - packages/conductor-core/tests/test_agent_report.py
  - packages/conductor-core/tests/test_orchestrator.py
autonomous: true
requirements: [STAT-01, STAT-02, DEVN-01]

must_haves:
  truths:
    - "AgentReport model parses JSON status blocks from agent output text"
    - "Orchestrator routes DONE to review, BLOCKED to escalation/retry, NEEDS_CONTEXT to context provision"
    - "Agent system prompt includes structured status output instructions and deviation rules"
    - "Missing or malformed JSON status blocks fall through to existing freeform behavior"
  artifacts:
    - path: "packages/conductor-core/src/conductor/orchestrator/models.py"
      provides: "AgentReport model with AgentStatus enum"
      contains: "class AgentReport"
    - path: "packages/conductor-core/src/conductor/orchestrator/identity.py"
      provides: "System prompt with status block instructions and deviation rules"
      contains: "STATUS_BLOCK_INSTRUCTIONS"
    - path: "packages/conductor-core/src/conductor/orchestrator/monitor.py"
      provides: "parse_agent_report function for extracting JSON from result text"
      contains: "def parse_agent_report"
    - path: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      provides: "Status-based routing in _run_agent_loop"
      contains: "parse_agent_report"
    - path: "packages/conductor-core/tests/test_agent_report.py"
      provides: "Tests for AgentReport parsing and status routing"
      min_lines: 50
  key_links:
    - from: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      to: "packages/conductor-core/src/conductor/orchestrator/monitor.py"
      via: "parse_agent_report import"
      pattern: "from conductor\\.orchestrator\\.monitor import.*parse_agent_report"
    - from: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      to: "packages/conductor-core/src/conductor/orchestrator/models.py"
      via: "AgentReport import"
      pattern: "from conductor\\.orchestrator\\.models import.*AgentReport"
    - from: "packages/conductor-core/src/conductor/orchestrator/identity.py"
      to: "agent system prompt output"
      via: "STATUS_BLOCK_INSTRUCTIONS appended to prompt"
      pattern: "STATUS_BLOCK_INSTRUCTIONS"
---

<objective>
Add structured agent communication protocol: agents output JSON status blocks, the orchestrator parses them and routes by status, and deviation rules in the system prompt prevent scope creep.

Purpose: Move from freeform agent output to programmatic status routing, enabling retry/escalation for blocked agents and context provision for context-starved agents.
Output: AgentReport model, parse function, status routing in orchestrator, updated system prompts with status instructions and deviation rules.
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/27-execution-routing-pipeline/27-01-SUMMARY.md

<interfaces>
<!-- Key types and contracts the executor needs. -->

From packages/conductor-core/src/conductor/orchestrator/models.py:
```python
class AgentRole(StrEnum):
    decomposer = "decomposer"
    reviewer = "reviewer"
    executor = "executor"
    verifier = "verifier"

class TaskSpec(BaseModel):
    id: str
    title: str
    description: str
    role: str
    target_file: str
    material_files: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
```

From packages/conductor-core/src/conductor/orchestrator/monitor.py:
```python
class StreamMonitor:
    def __init__(self, task_id: str) -> None: ...
    def process(self, message: object) -> None: ...
    @property
    def result_text(self) -> str | None: ...
    @property
    def tool_events(self) -> list[str]: ...
```

From packages/conductor-core/src/conductor/orchestrator/identity.py:
```python
class AgentIdentity(BaseModel):
    name: str
    role: str
    target_file: str
    material_files: list[str] = Field(default_factory=list)
    task_id: str
    task_description: str

def build_system_prompt(identity: AgentIdentity) -> str: ...
```

From packages/conductor-core/src/conductor/orchestrator/escalation.py:
```python
class EscalationRouter:
    async def resolve(self, input_data: dict) -> PermissionResultAllow | PermissionResultDeny: ...
```

From packages/conductor-core/src/conductor/orchestrator/orchestrator.py:
```python
# _run_agent_loop is where agent output is processed:
# - monitor.result_text captures the final agent output
# - review_output() runs after stream completes
# - revision loop sends feedback via client.send()
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: AgentReport model, parse function, and system prompt updates</name>
  <files>
    packages/conductor-core/src/conductor/orchestrator/models.py,
    packages/conductor-core/src/conductor/orchestrator/monitor.py,
    packages/conductor-core/src/conductor/orchestrator/identity.py,
    packages/conductor-core/tests/test_agent_report.py
  </files>
  <behavior>
    - Test: AgentReport with status=DONE, summary, files_changed, concerns parses from valid dict
    - Test: AgentReportStatus enum has DONE, DONE_WITH_CONCERNS, BLOCKED, NEEDS_CONTEXT values
    - Test: parse_agent_report extracts JSON from text containing ```json\n{"status": "DONE", ...}\n``` block
    - Test: parse_agent_report returns None when no JSON block found (freeform fallback)
    - Test: parse_agent_report returns None when JSON is malformed (best-effort, no crash)
    - Test: parse_agent_report extracts from text with surrounding prose (JSON block in middle of output)
    - Test: build_system_prompt output contains status block instructions mentioning DONE/BLOCKED/NEEDS_CONTEXT
    - Test: build_system_prompt output contains deviation rules mentioning auto-fix and escalation
  </behavior>
  <action>
    1. In models.py, add `AgentReportStatus(StrEnum)` with values: DONE, DONE_WITH_CONCERNS, BLOCKED, NEEDS_CONTEXT.
    2. In models.py, add `AgentReport(BaseModel)` with fields: status (AgentReportStatus), summary (str), files_changed (list[str], default_factory=list), concerns (list[str], default_factory=list).
    3. In monitor.py, add a module-level function `parse_agent_report(text: str) -> AgentReport | None` that:
       - Searches for a fenced JSON block (```json ... ```) in the text using regex
       - Also tries to find a bare JSON object with `"status"` key as fallback
       - Attempts `AgentReport.model_validate_json()` on the extracted JSON
       - Returns None on any failure (no JSON found, parse error, validation error) — this is the freeform fallback
    4. In identity.py, add a module-level constant `STATUS_BLOCK_INSTRUCTIONS` containing the instruction text that tells agents to output a JSON status block at the end of their work. The block should specify the schema: `{"status": "DONE|DONE_WITH_CONCERNS|BLOCKED|NEEDS_CONTEXT", "summary": "...", "files_changed": [...], "concerns": [...]}`.
    5. In identity.py, add a module-level constant `DEVIATION_RULES` containing deviation classification rules:
       - Rule 1: Typos and syntax errors in target file — fix silently
       - Rule 2: Missing imports required by your implementation — add them
       - Rule 3: Broken tests caused by your changes — fix them
       - Rule 4: Architectural changes, new dependencies, scope beyond task description — STOP, set status to BLOCKED with concern explaining the issue
    6. In identity.py, update `build_system_prompt()` to append `STATUS_BLOCK_INSTRUCTIONS` and `DEVIATION_RULES` to the prompt parts.
    7. Create tests/test_agent_report.py with tests per the behavior block above.
  </action>
  <verify>
    <automated>cd packages/conductor-core && python -m pytest tests/test_agent_report.py -x -v</automated>
  </verify>
  <done>AgentReport model exists in models.py. parse_agent_report in monitor.py extracts structured reports from agent text or returns None for freeform. System prompt includes status and deviation instructions. All tests pass.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Status-based routing in orchestrator</name>
  <files>
    packages/conductor-core/src/conductor/orchestrator/orchestrator.py,
    packages/conductor-core/tests/test_orchestrator.py
  </files>
  <behavior>
    - Test: When agent reports DONE, orchestrator proceeds to review_output as before
    - Test: When agent reports BLOCKED, orchestrator logs and escalates (in interactive mode, pushes to human_out; in auto mode, retries with "proceed with best judgment" context)
    - Test: When agent reports NEEDS_CONTEXT, orchestrator sends additional context message via client.send and re-enters stream loop (up to 1 retry)
    - Test: When agent output has no parseable AgentReport (freeform), orchestrator proceeds to review_output unchanged (backward compat)
    - Test: DONE_WITH_CONCERNS proceeds to review but logs concerns
  </behavior>
  <action>
    1. In orchestrator.py, import `parse_agent_report` from monitor and `AgentReport, AgentReportStatus` from models.
    2. In `_run_agent_loop`, after the stream completes and `monitor.result_text` is captured, call `report = parse_agent_report(monitor.result_text or "")`.
    3. Add status routing logic BEFORE the existing `review_output()` call:
       - If `report` is None: fall through to existing review_output behavior (freeform backward compat)
       - If `report.status == DONE` or `report.status == DONE_WITH_CONCERNS`: proceed to review_output. If DONE_WITH_CONCERNS, log the concerns at WARNING level.
       - If `report.status == BLOCKED`:
         - Log the concern at WARNING
         - In interactive mode (self._human_out and self._human_in exist): push a HumanQuery with the blocked concern, await answer, send answer via client.send, then re-enter the stream/monitor loop for one more iteration (reuse the existing revision_num counter — treat as a revision)
         - In auto mode: send "The orchestrator acknowledges your concern. Proceed with your best judgment on the blocked issue." via client.send, then re-enter stream loop
       - If `report.status == NEEDS_CONTEXT`:
         - Log at INFO
         - Send "Additional context: Please read the material files listed in your system prompt. If you need specific information, describe what you need in your next status report with status BLOCKED." via client.send
         - Re-enter stream loop (counts as a revision iteration)
    4. Important: The routing happens INSIDE the existing revision for-loop. After routing for BLOCKED/NEEDS_CONTEXT, the loop naturally continues to the next iteration where the agent's new output will be processed again.
    5. Do NOT change the review_output call signature or the file existence gate — those remain untouched.
    6. Add tests to test_orchestrator.py for each routing path. Use the existing mock patterns (_make_mock_acp_client_with_result). Create a helper that returns a client whose stream yields a ResultMessage with a JSON status block in the result text.
  </action>
  <verify>
    <automated>cd packages/conductor-core && python -m pytest tests/test_orchestrator.py -x -v -k "agent_report or blocked or needs_context or freeform or concerns"</automated>
  </verify>
  <done>Orchestrator parses AgentReport from agent output. DONE proceeds to review. BLOCKED escalates or retries. NEEDS_CONTEXT provides context and retries. Freeform output falls through unchanged. All existing tests still pass.</done>
</task>

</tasks>

<verification>
```bash
cd packages/conductor-core && python -m pytest tests/ -x -v 2>&1 | tail -20
```
All existing tests plus new tests pass. No regressions.
</verification>

<success_criteria>
1. AgentReport model with AgentReportStatus enum exists in models.py
2. parse_agent_report in monitor.py extracts JSON status blocks or returns None
3. build_system_prompt includes status block instructions and deviation rules
4. Orchestrator routes by status: DONE/DONE_WITH_CONCERNS to review, BLOCKED to escalation/retry, NEEDS_CONTEXT to context provision
5. Freeform agent output (no JSON block) falls through to existing review behavior
6. All tests pass (existing + new)
</success_criteria>

<output>
After completion, create `.planning/phases/28-agent-communication-protocol/28-01-SUMMARY.md`
</output>
