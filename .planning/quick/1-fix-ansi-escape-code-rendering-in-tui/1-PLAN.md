---
phase: quick-fix
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/src/conductor/cli/chat.py
  - packages/conductor-core/src/conductor/cli/commands/run.py
  - packages/conductor-core/src/conductor/cli/commands/status.py
  - packages/conductor-core/src/conductor/cli/input_loop.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "ANSI escape codes from agent output render as terminal formatting, not raw text like ?[2m"
    - "Rich markup (e.g., [bold], [dim]) still works correctly on all Console instances"
  artifacts:
    - path: "packages/conductor-core/src/conductor/cli/chat.py"
      provides: "Console instances with highlight=False"
    - path: "packages/conductor-core/src/conductor/cli/commands/run.py"
      provides: "Console instances with highlight=False"
    - path: "packages/conductor-core/src/conductor/cli/commands/status.py"
      provides: "Console instance with highlight=False"
    - path: "packages/conductor-core/src/conductor/cli/input_loop.py"
      provides: "Console instances with highlight=False"
  key_links: []
---

<objective>
Fix ANSI escape code rendering in the TUI by disabling Rich's automatic highlighting on all Console instances that display agent/streaming output.

Purpose: Rich's `Console(highlight=True)` (the default) escapes ANSI control characters, causing raw sequences like `?[2m` to appear instead of proper terminal formatting (dim, bold, etc.).

Output: All CLI Console instances pass `highlight=False`, preserving ANSI pass-through while keeping Rich markup functional.
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@packages/conductor-core/src/conductor/cli/chat.py
@packages/conductor-core/src/conductor/cli/commands/run.py
@packages/conductor-core/src/conductor/cli/commands/status.py
@packages/conductor-core/src/conductor/cli/input_loop.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Add highlight=False to all CLI Console instantiations</name>
  <files>
    packages/conductor-core/src/conductor/cli/chat.py
    packages/conductor-core/src/conductor/cli/commands/run.py
    packages/conductor-core/src/conductor/cli/commands/status.py
    packages/conductor-core/src/conductor/cli/input_loop.py
  </files>
  <action>
Add `highlight=False` to every `Console(...)` call in the four files. Specific locations:

1. **chat.py line 76** — `Console(force_terminal=True)` in `pick_session()` fallback
   Change to: `Console(force_terminal=True, highlight=False)`

2. **chat.py line 151** — `Console(force_terminal=True)` in `ChatSession.__init__()` fallback
   Change to: `Console(force_terminal=True, highlight=False)`

3. **run.py line 21** — module-level `_console = Console()`
   Change to: `_console = Console(highlight=False)`

4. **run.py line 97** — `Console(stderr=True)` for `input_console`
   Change to: `Console(stderr=True, highlight=False)`

5. **run.py line 120** — `Console(stderr=False)` inside `Live()`
   Change to: `Console(stderr=False, highlight=False)`

6. **status.py line 18** — `Console()` in `status()` function
   Change to: `Console(highlight=False)`

7. **input_loop.py line 39** — `Console(stderr=True)` fallback in `_dispatch_command()`
   Change to: `Console(stderr=True, highlight=False)`

8. **input_loop.py line 126** — `Console(stderr=True)` fallback in `_input_loop()`
   Change to: `Console(stderr=True, highlight=False)`

Do NOT change anything else in these files. Only add the `highlight=False` keyword argument.
  </action>
  <verify>
    <automated>cd /home/huypham/code/digest/claude-auto && python -c "from conductor.cli.chat import ChatSession, pick_session; from conductor.cli.commands.run import run; from conductor.cli.commands.status import status; from conductor.cli.input_loop import _input_loop; print('All imports OK')" && grep -rn "Console(" packages/conductor-core/src/conductor/cli/ | grep -v "highlight=False" | grep -v "TYPE_CHECKING" | grep -v "import" | grep -v "__pycache__" | grep -v ".pyc" && echo "--- Any lines above are Console() calls missing highlight=False ---"</automated>
  </verify>
  <done>Every Console instantiation in the four CLI files includes highlight=False. No Console() call in conductor/cli/ is missing the flag. Modules import without errors.</done>
</task>

</tasks>

<verification>
1. All Console instantiations in conductor/cli/ include `highlight=False`
2. All four modules import without errors
3. Rich markup like `[bold]`, `[dim]`, `[red]` still renders (highlight controls auto-detection of URLs/numbers/etc., not markup parsing)
</verification>

<success_criteria>
- Zero Console() calls in packages/conductor-core/src/conductor/cli/ without highlight=False
- All CLI modules import successfully
- ANSI escape codes in agent output will render as terminal formatting instead of raw text
</success_criteria>

<output>
After completion, create `.planning/quick/1-fix-ansi-escape-code-rendering-in-tui/1-SUMMARY.md`
</output>
