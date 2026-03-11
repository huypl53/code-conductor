---
phase: 25-post-run-build-verification
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - packages/conductor-core/src/conductor/orchestrator/orchestrator.py
  - packages/conductor-core/src/conductor/cli/commands/run.py
  - packages/conductor-core/src/conductor/cli/delegation.py
  - packages/conductor-core/tests/test_orchestrator.py
  - packages/conductor-core/tests/test_run_command.py
autonomous: true
requirements:
  - VRFY-02
  - VRFY-03

must_haves:
  truths:
    - "After all tasks complete, if build_command is set, orchestrator runs it and prints 'Build verification: PASSED' or 'Build verification: FAILED'"
    - "A build failure does not affect any task's status — tasks remain COMPLETED"
    - "conductor run --build-command 'npx tsc --noEmit' passes the command to the orchestrator and runs it post-completion"
    - "build_command set in .conductor/config.json is loaded automatically; CLI flag overrides it"
    - "If build_command is None (not set anywhere), no build step runs"
  artifacts:
    - path: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      provides: "_post_run_build_check() async method + build_command param in __init__"
      contains: "_post_run_build_check"
    - path: "packages/conductor-core/src/conductor/cli/commands/run.py"
      provides: "--build-command CLI flag + _load_conductor_config() helper"
      contains: "_load_conductor_config"
    - path: "packages/conductor-core/src/conductor/cli/delegation.py"
      provides: "build_command param threaded through DelegationManager into Orchestrator"
      contains: "build_command"
    - path: "packages/conductor-core/tests/test_orchestrator.py"
      provides: "TestBuildVerification test class"
      contains: "TestBuildVerification"
    - path: "packages/conductor-core/tests/test_run_command.py"
      provides: "TestBuildCommand test class"
      contains: "TestBuildCommand"
  key_links:
    - from: "packages/conductor-core/src/conductor/cli/commands/run.py"
      to: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      via: "Orchestrator(build_command=resolved_build_command)"
      pattern: "Orchestrator\\(.*build_command"
    - from: "packages/conductor-core/src/conductor/orchestrator/orchestrator.py"
      to: "asyncio.create_subprocess_shell"
      via: "_post_run_build_check() called at tail of run() and resume()"
      pattern: "_post_run_build_check"
---

<objective>
Add post-run build verification to the conductor orchestrator. After all agent tasks complete, if a `build_command` is configured, the orchestrator runs it via `asyncio.create_subprocess_shell` and prints a single-line verdict plus full stderr on failure. The command can be supplied via `--build-command` CLI flag or persisted in `.conductor/config.json`.

Purpose: Catch cross-file import errors, type errors, and syntax errors that per-task review cannot detect — giving the user a single-line pass/fail verdict at the end of every run.

Output:
- `Orchestrator._post_run_build_check()` async method called at the tail of `run()` and `resume()`
- `--build-command` Typer option in `run.py` + `_load_conductor_config()` helper
- `DelegationManager.__init__` accepts `build_command` and threads it to both Orchestrator construction sites
- `TestBuildVerification` class in `test_orchestrator.py`
- `TestBuildCommand` class in `test_run_command.py`
</objective>

<execution_context>
@/home/huypham/.claude/get-shit-done/workflows/execute-plan.md
@/home/huypham/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@packages/conductor-core/src/conductor/orchestrator/orchestrator.py
@packages/conductor-core/src/conductor/cli/commands/run.py
@packages/conductor-core/src/conductor/cli/delegation.py
@packages/conductor-core/tests/test_orchestrator.py
@packages/conductor-core/tests/test_run_command.py

<interfaces>
<!-- Key interfaces the executor needs. Extracted from codebase. -->

From orchestrator.py — Orchestrator.__init__ (lines 108-124):
```python
def __init__(
    self,
    state_manager: StateManager,
    repo_path: str,
    mode: str = "auto",
    human_out: asyncio.Queue | None = None,
    human_in: asyncio.Queue | None = None,
    max_agents: int = 10,
    max_revisions: int = 2,
) -> None:
```
Add `build_command: str | None = None` as the last keyword argument.

From orchestrator.py — run() termination (lines 224-226):
```python
        # Wait for any stragglers (shouldn't normally happen)
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)
        # INSERT: await self._post_run_build_check() here
```

From orchestrator.py — resume() termination (lines 430-431):
```python
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)
        # INSERT: await self._post_run_build_check() here
```

From run.py — _run_async signature (lines 43-50):
```python
async def _run_async(
    description: str,
    *,
    auto: bool,
    repo: Path,
    resume: bool = False,
    dashboard_port: int | None = None,
) -> None:
```
Add `build_command: str | None = None` parameter.

From run.py — conductor_dir pattern (lines 52-55):
```python
    conductor_dir = repo / ".conductor"
    conductor_dir.mkdir(parents=True, exist_ok=True)
    state_manager = StateManager(conductor_dir / "state.json")
```
Config loading goes right after `conductor_dir.mkdir(...)`.

From run.py — Orchestrator construction (lines 59-65):
```python
    orchestrator = Orchestrator(
        state_manager=state_manager,
        repo_path=str(repo),
        mode="auto" if auto else "interactive",
        human_out=human_out,
        human_in=human_in,
    )
```
Add `build_command=resolved_build_command` to this call.

From delegation.py — DelegationManager.__init__ (lines 91-111):
```python
    def __init__(
        self,
        console: Console,
        repo_path: str,
        dashboard_url: str = DEFAULT_DASHBOARD_URL,
        input_fn: Callable[..., Any] | None = None,
    ) -> None:
```
Add `build_command: str | None = None` after `input_fn`.

From delegation.py — handle_delegate Orchestrator construction (lines 144-150):
```python
        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=self._repo_path,
            mode="interactive",
            human_out=self._human_out,
            human_in=self._human_in,
        )
```

From delegation.py — resume_delegation Orchestrator construction (lines 226-232):
```python
        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=self._repo_path,
            mode="interactive",
            human_out=self._human_out,
            human_in=self._human_in,
        )
```
Both need `build_command=self._build_command` added.

From test_orchestrator.py — test class pattern (lines 1-10):
```python
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
# Class-based test groups using @pytest.mark.asyncio
```

From test_run_command.py — patch pattern (lines 17-22):
```python
with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
     patch("conductor.cli.commands.run.Live"), \
     patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
     patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Write failing tests for build verification (Wave 0)</name>
  <files>
    packages/conductor-core/tests/test_orchestrator.py
    packages/conductor-core/tests/test_run_command.py
  </files>
  <behavior>
    TestBuildVerification (append to test_orchestrator.py):
    - test_build_check_skipped_when_no_command: Orchestrator with build_command=None, run() completes — subprocess NOT called
    - test_build_check_passes: Orchestrator with build_command="echo ok", mock subprocess returns returncode=0 — prints "Build verification: PASSED", no stderr printed
    - test_build_check_fails_prints_stderr: mock subprocess returns returncode=1, stderr=b"error: type mismatch" — prints "Build verification: FAILED (exit 1)" and the stderr text
    - test_build_check_called_after_resume: Orchestrator.resume() with build_command set — subprocess called after tasks finish
    - test_build_failure_does_not_affect_task_status: task status remains COMPLETED even when build returns nonzero

    TestBuildCommand (append to test_run_command.py):
    - test_build_command_flag_passed_to_orchestrator: _run_async called with build_command="npx tsc --noEmit" — Orchestrator constructed with build_command="npx tsc --noEmit"
    - test_config_json_provides_build_command: tmp_path has .conductor/config.json with {"build_command": "cargo check"}, no CLI flag — Orchestrator constructed with build_command="cargo check"
    - test_cli_flag_overrides_config_json: both CLI flag and config.json set — CLI flag value wins
    - test_missing_config_json_ok: no .conductor/config.json — _run_async succeeds, Orchestrator built with build_command=None
    - test_malformed_config_json_ok: .conductor/config.json contains invalid JSON — _run_async succeeds (graceful fallback), Orchestrator built with build_command=None
  </behavior>
  <action>
    Append a `TestBuildVerification` class to `packages/conductor-core/tests/test_orchestrator.py`.

    Structure for TestBuildVerification:

    ```python
    class TestBuildVerification:
        """Tests for VRFY-02: post-run build command execution."""

        def _make_orchestrator(self, tmp_path, build_command=None):
            """Helper: build a minimal Orchestrator with mocked state."""
            from conductor.orchestrator.orchestrator import Orchestrator
            mgr = _make_state_manager()
            mgr.read_state = MagicMock(return_value=MagicMock(tasks=[], agents=[]))
            return Orchestrator(
                state_manager=mgr,
                repo_path=str(tmp_path),
                build_command=build_command,
            )

        @pytest.mark.asyncio
        async def test_build_check_skipped_when_no_command(self, tmp_path):
            orch = self._make_orchestrator(tmp_path, build_command=None)
            with patch("asyncio.create_subprocess_shell") as mock_sub:
                await orch._post_run_build_check()
            mock_sub.assert_not_called()

        @pytest.mark.asyncio
        async def test_build_check_passes(self, tmp_path, capsys):
            orch = self._make_orchestrator(tmp_path, build_command="echo ok")
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            with patch("asyncio.create_subprocess_shell", return_value=mock_proc):
                await orch._post_run_build_check()
            captured = capsys.readouterr()
            assert "PASSED" in captured.out

        @pytest.mark.asyncio
        async def test_build_check_fails_prints_stderr(self, tmp_path, capsys):
            orch = self._make_orchestrator(tmp_path, build_command="tsc")
            mock_proc = AsyncMock()
            mock_proc.returncode = 1
            mock_proc.communicate = AsyncMock(return_value=(b"", b"error: type mismatch"))
            with patch("asyncio.create_subprocess_shell", return_value=mock_proc):
                await orch._post_run_build_check()
            captured = capsys.readouterr()
            assert "FAILED" in captured.out
            assert "error: type mismatch" in captured.out

        @pytest.mark.asyncio
        async def test_build_check_called_after_resume(self, tmp_path):
            from conductor.orchestrator.orchestrator import Orchestrator
            mgr = _make_state_manager()
            # Empty state — resume() returns early before agent loop
            empty_state = MagicMock()
            empty_state.tasks = []
            empty_state.agents = []
            mgr.read_state = MagicMock(return_value=empty_state)
            orch = Orchestrator(
                state_manager=mgr,
                repo_path=str(tmp_path),
                build_command="echo check",
            )
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            with patch("asyncio.create_subprocess_shell", return_value=mock_proc) as mock_sub:
                await orch.resume()
            mock_sub.assert_called_once()

        @pytest.mark.asyncio
        async def test_build_failure_does_not_affect_task_status(self, tmp_path):
            """A failing build must not alter any task's status."""
            orch = self._make_orchestrator(tmp_path, build_command="false")
            mock_proc = AsyncMock()
            mock_proc.returncode = 2
            mock_proc.communicate = AsyncMock(return_value=(b"", b"build error"))
            mutate_calls = []
            orch._state.mutate = MagicMock(side_effect=lambda fn: mutate_calls.append(fn))
            with patch("asyncio.create_subprocess_shell", return_value=mock_proc):
                await orch._post_run_build_check()
            # No state mutations should have occurred during build check
            assert mutate_calls == []
    ```

    Append a `TestBuildCommand` class to `packages/conductor-core/tests/test_run_command.py`:

    ```python
    class TestBuildCommand:
        """Tests for VRFY-03: --build-command flag and config.json loading."""

        @pytest.mark.asyncio
        async def test_build_command_flag_passed_to_orchestrator(self, tmp_path):
            from conductor.cli.commands.run import _run_async
            with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
                 patch("conductor.cli.commands.run.Live"), \
                 patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
                 patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
                mock_orch = MockOrch.return_value
                mock_orch.run_auto = AsyncMock()
                await _run_async("desc", auto=True, repo=tmp_path, resume=False,
                                 build_command="npx tsc --noEmit")
            _, kwargs = MockOrch.call_args
            assert kwargs["build_command"] == "npx tsc --noEmit"

        @pytest.mark.asyncio
        async def test_config_json_provides_build_command(self, tmp_path):
            import json
            from conductor.cli.commands.run import _run_async
            conductor_dir = tmp_path / ".conductor"
            conductor_dir.mkdir()
            (conductor_dir / "config.json").write_text(
                json.dumps({"build_command": "cargo check"})
            )
            with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
                 patch("conductor.cli.commands.run.Live"), \
                 patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
                 patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
                mock_orch = MockOrch.return_value
                mock_orch.run_auto = AsyncMock()
                await _run_async("desc", auto=True, repo=tmp_path, resume=False,
                                 build_command=None)
            _, kwargs = MockOrch.call_args
            assert kwargs["build_command"] == "cargo check"

        @pytest.mark.asyncio
        async def test_cli_flag_overrides_config_json(self, tmp_path):
            import json
            from conductor.cli.commands.run import _run_async
            conductor_dir = tmp_path / ".conductor"
            conductor_dir.mkdir()
            (conductor_dir / "config.json").write_text(
                json.dumps({"build_command": "cargo check"})
            )
            with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
                 patch("conductor.cli.commands.run.Live"), \
                 patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
                 patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
                mock_orch = MockOrch.return_value
                mock_orch.run_auto = AsyncMock()
                await _run_async("desc", auto=True, repo=tmp_path, resume=False,
                                 build_command="npx tsc --noEmit")
            _, kwargs = MockOrch.call_args
            assert kwargs["build_command"] == "npx tsc --noEmit"

        @pytest.mark.asyncio
        async def test_missing_config_json_ok(self, tmp_path):
            from conductor.cli.commands.run import _run_async
            with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
                 patch("conductor.cli.commands.run.Live"), \
                 patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
                 patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
                mock_orch = MockOrch.return_value
                mock_orch.run_auto = AsyncMock()
                await _run_async("desc", auto=True, repo=tmp_path, resume=False,
                                 build_command=None)
            _, kwargs = MockOrch.call_args
            assert kwargs["build_command"] is None

        @pytest.mark.asyncio
        async def test_malformed_config_json_ok(self, tmp_path):
            from conductor.cli.commands.run import _run_async
            conductor_dir = tmp_path / ".conductor"
            conductor_dir.mkdir()
            (conductor_dir / "config.json").write_text("NOT JSON {{{")
            with patch("conductor.cli.commands.run.Orchestrator") as MockOrch, \
                 patch("conductor.cli.commands.run.Live"), \
                 patch("conductor.cli.commands.run._display_loop", new_callable=AsyncMock), \
                 patch("conductor.cli.commands.run._input_loop", new_callable=AsyncMock):
                mock_orch = MockOrch.return_value
                mock_orch.run_auto = AsyncMock()
                # Must not raise
                await _run_async("desc", auto=True, repo=tmp_path, resume=False,
                                 build_command=None)
            _, kwargs = MockOrch.call_args
            assert kwargs["build_command"] is None
    ```

    Run tests — they MUST fail (RED):
    ```
    pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification packages/conductor-core/tests/test_run_command.py::TestBuildCommand -x -q 2>&1 | head -40
    ```
    Commit RED state: `test(phase-25): add failing tests for build verification`
  </action>
  <verify>
    <automated>pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification packages/conductor-core/tests/test_run_command.py::TestBuildCommand -x -q 2>&1 | grep -E "^(FAILED|ERROR|passed|failed)" | head -5</automated>
  </verify>
  <done>All TestBuildVerification and TestBuildCommand tests exist and FAIL (AttributeError or ImportError — the production code does not yet have build_command support). No test syntax errors.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement _post_run_build_check in Orchestrator (GREEN)</name>
  <files>
    packages/conductor-core/src/conductor/orchestrator/orchestrator.py
  </files>
  <behavior>
    - Orchestrator.__init__ accepts build_command: str | None = None (stored as self._build_command)
    - _post_run_build_check() is a new async method that early-returns if self._build_command is None
    - When command is set: runs via asyncio.create_subprocess_shell with cwd=self._repo_path, stdout=PIPE, stderr=PIPE
    - returncode == 0: prints "\nBuild verification: PASSED"
    - returncode != 0: prints "\nBuild verification: FAILED (exit {returncode})" and the decoded stderr (errors="replace")
    - Does NOT mutate state, does NOT raise
    - Called at the tail of run() after the straggler-gather block (after line 226)
    - Called at the tail of resume() after the straggler-gather block (after line 431)
    - run_auto() needs no change — it calls run() which already handles it
  </behavior>
  <action>
    Make three targeted edits to `orchestrator.py`:

    **Edit 1 — Add build_command to __init__ (after line 116, before `-> None:`):**
    Add `build_command: str | None = None,` as the last parameter before `-> None:`.
    In the body (after line 124 where `self._max_revisions = max_revisions`), add:
    ```python
        self._build_command = build_command
    ```

    **Edit 2 — Call _post_run_build_check at tail of run() (after line 226):**
    After the existing block:
    ```python
        # Wait for any stragglers (shouldn't normally happen)
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)
    ```
    Add:
    ```python

        await self._post_run_build_check()
    ```

    **Edit 3 — Call _post_run_build_check at tail of resume() (after line 431):**
    After the existing block:
    ```python
        if pending:
            await asyncio.gather(*pending.values(), return_exceptions=True)
    ```
    Add:
    ```python

        await self._post_run_build_check()
    ```

    **Edit 4 — Add _post_run_build_check method to the Private helpers section (after _make_set_agent_status_fn, before EOF):**
    ```python
    async def _post_run_build_check(self) -> None:
        """Run the configured build command and report pass/fail (VRFY-02).

        Called at the tail of run() and resume(). Does NOT raise on build
        failure and does NOT modify task state — it is a final report only.
        """
        if not self._build_command:
            return

        logger.info("Running build verification: %s", self._build_command)
        proc = await asyncio.create_subprocess_shell(
            self._build_command,
            cwd=self._repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            logger.info("Build verification passed.")
            print("\nBuild verification: PASSED")
        else:
            stderr_text = stderr.decode(errors="replace")
            logger.error(
                "Build verification FAILED (exit %d):\n%s",
                proc.returncode,
                stderr_text,
            )
            print(f"\nBuild verification: FAILED (exit {proc.returncode})")
            print(stderr_text)
    ```

    Place `_post_run_build_check` as the last method before the `@staticmethod` helper block (i.e., insert it between the `pause_for_human_decision` method and the `# Private helpers` comment block), OR as the first method after the `# Private helpers` comment — immediately before `_run_agent_loop`. Either location is fine as long as the method is an instance method (not static).

    Run tests — they MUST pass (GREEN):
    ```
    pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification -x -q
    ```
    Commit GREEN state: `feat(phase-25): implement _post_run_build_check in Orchestrator`
  </action>
  <verify>
    <automated>pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification -x -q</automated>
  </verify>
  <done>All 5 TestBuildVerification tests pass. No regressions in the broader test_orchestrator.py suite (`pytest packages/conductor-core/tests/test_orchestrator.py -q` green).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire CLI flag, config.json loading, and delegation propagation (GREEN)</name>
  <files>
    packages/conductor-core/src/conductor/cli/commands/run.py
    packages/conductor-core/src/conductor/cli/delegation.py
  </files>
  <behavior>
    run.py changes:
    - _load_conductor_config(conductor_dir: Path) -> dict: reads config.json, returns {} on missing or malformed JSON (warn via logger)
    - run() Typer command gets build_command: str | None = typer.Option(None, "--build-command", help="Shell command to run after all tasks complete (e.g. 'npx tsc --noEmit')")
    - _run_async() gets build_command: str | None = None parameter
    - Inside _run_async, after conductor_dir.mkdir(): load config, resolve build_command (CLI beats config)
    - Orchestrator(...) call gains build_command=resolved_build_command

    delegation.py changes:
    - DelegationManager.__init__ gets build_command: str | None = None (stored as self._build_command)
    - Both handle_delegate and resume_delegation pass build_command=self._build_command to Orchestrator(...)
  </behavior>
  <action>
    **run.py — four edits:**

    **Edit 1 — Add `import json` at the top** (after `import sys`, before `from contextlib import suppress`):
    ```python
    import json
    ```

    **Edit 2 — Add `_load_conductor_config` helper function** (after the `_console = Console()` line, before the `def run(` function):
    ```python
    def _load_conductor_config(conductor_dir: Path) -> dict:
        """Load .conductor/config.json, returning {} on missing or malformed file."""
        config_path = conductor_dir / "config.json"
        if not config_path.exists():
            return {}
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            import logging
            logging.getLogger("conductor.cli").warning(
                "Failed to parse .conductor/config.json — ignoring."
            )
            return {}
    ```

    **Edit 3 — Add `build_command` parameter to the `run()` Typer command** (after the `dashboard_port` parameter):
    ```python
        build_command: str | None = typer.Option(
            None,
            "--build-command",
            help="Shell command to run after all tasks complete (e.g. 'npx tsc --noEmit').",
        ),
    ```
    Update the `asyncio.run(...)` call to forward it:
    ```python
    asyncio.run(_run_async(
        description or "",
        auto=auto,
        repo=Path(repo).resolve(),
        resume=resume,
        dashboard_port=dashboard_port,
        build_command=build_command,
    ))
    ```

    **Edit 4 — Update `_run_async`** signature and body:

    Signature — add `build_command: str | None = None` after `dashboard_port`:
    ```python
    async def _run_async(
        description: str,
        *,
        auto: bool,
        repo: Path,
        resume: bool = False,
        dashboard_port: int | None = None,
        build_command: str | None = None,
    ) -> None:
    ```

    Body — add after the `conductor_dir.mkdir(...)` line:
    ```python
        config = _load_conductor_config(conductor_dir)
        resolved_build_command = build_command or config.get("build_command")
    ```

    Update the Orchestrator construction to pass `build_command=resolved_build_command`:
    ```python
        orchestrator = Orchestrator(
            state_manager=state_manager,
            repo_path=str(repo),
            mode="auto" if auto else "interactive",
            human_out=human_out,
            human_in=human_in,
            build_command=resolved_build_command,
        )
    ```

    ---

    **delegation.py — two edits:**

    **Edit 1 — Add `build_command` to DelegationManager.__init__** (after `input_fn` parameter):
    ```python
        def __init__(
            self,
            console: Console,
            repo_path: str,
            dashboard_url: str = DEFAULT_DASHBOARD_URL,
            input_fn: Callable[..., Any] | None = None,
            build_command: str | None = None,
        ) -> None:
    ```
    In the body, add after `self._input_fn = input_fn`:
    ```python
            self._build_command = build_command
    ```

    **Edit 2 — Thread build_command into both Orchestrator construction sites:**

    In `handle_delegate` (lines 144-150), change to:
    ```python
            orchestrator = Orchestrator(
                state_manager=state_manager,
                repo_path=self._repo_path,
                mode="interactive",
                human_out=self._human_out,
                human_in=self._human_in,
                build_command=self._build_command,
            )
    ```

    In `resume_delegation` (lines 226-232), change to:
    ```python
            orchestrator = Orchestrator(
                state_manager=state_manager,
                repo_path=self._repo_path,
                mode="interactive",
                human_out=self._human_out,
                human_in=self._human_in,
                build_command=self._build_command,
            )
    ```

    Run full test suite for all new tests:
    ```
    pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification packages/conductor-core/tests/test_run_command.py::TestBuildCommand -x -q
    ```
    Commit: `feat(phase-25): add --build-command CLI flag, config.json loading, and delegation wiring`
  </action>
  <verify>
    <automated>pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification packages/conductor-core/tests/test_run_command.py::TestBuildCommand -x -q</automated>
  </verify>
  <done>All 10 tests (5 TestBuildVerification + 5 TestBuildCommand) pass. Full test suite clean: `pytest packages/conductor-core/tests/ -x -q` exits 0.</done>
</task>

</tasks>

<verification>
Full suite must be green before marking phase done:

```bash
pytest packages/conductor-core/tests/ -x -q
```

Spot-check the key wiring by searching the modified files:

```bash
grep -n "build_command\|_post_run_build_check\|_load_conductor_config" \
  packages/conductor-core/src/conductor/orchestrator/orchestrator.py \
  packages/conductor-core/src/conductor/cli/commands/run.py \
  packages/conductor-core/src/conductor/cli/delegation.py
```

Expected output contains:
- orchestrator.py: `build_command` in `__init__`, `_post_run_build_check` method definition, and two call sites (one in `run()`, one in `resume()`)
- run.py: `_load_conductor_config` function definition, `build_command` in `run()` and `_run_async()`, `resolved_build_command` used in Orchestrator construction
- delegation.py: `build_command` in `__init__`, `self._build_command` stored, passed to Orchestrator in both `handle_delegate` and `resume_delegation`

Verify the CLI flag is registered:

```bash
cd packages/conductor-core && python -m conductor run --help | grep build-command
```

Expected: `--build-command TEXT  Shell command to run after all tasks complete`
</verification>

<success_criteria>
1. `pytest packages/conductor-core/tests/test_orchestrator.py::TestBuildVerification -q` — 5 passed
2. `pytest packages/conductor-core/tests/test_run_command.py::TestBuildCommand -q` — 5 passed
3. `pytest packages/conductor-core/tests/ -x -q` — full suite green, no regressions
4. `conductor run --help` shows `--build-command` option
5. `Orchestrator(build_command="npx tsc --noEmit")` runs the command after tasks complete and prints "Build verification: PASSED" or "Build verification: FAILED (exit N)" + stderr
6. A build failure leaves all task statuses untouched (COMPLETED remains COMPLETED)
7. `.conductor/config.json` with `{"build_command": "..."}` is respected when no CLI flag is given; CLI flag overrides it
8. Malformed or missing config.json does not crash `conductor run`
</success_criteria>

<output>
After all tasks pass, create `.planning/phases/25/25-01-SUMMARY.md` with:
- What was implemented (3 files changed, 2 test classes added)
- Key decisions made (print vs logger: both — logger for testability, print for user-visible output; config loading in run.py not orchestrator)
- Test count and command to verify
- Any deviations from the plan
</output>
