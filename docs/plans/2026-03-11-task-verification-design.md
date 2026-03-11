# Task Verification Design

**Problem:** Conductor marks tasks as completed even when the target file was never written to disk. In the calendar app build, t11 (EventChip) was marked `completed + approved` but `src/components/EventChip.tsx` doesn't exist — causing downstream tasks (TimeGrid) to fail on import.

**Root cause:** The reviewer checks file existence and returns `approved=False` for missing files, but the orchestrator marks the task as completed anyway (with `NEEDS_REVISION` status). There's no hard gate that forces a retry when the file is missing.

**Approach:** Two-layer verification — per-task file existence gate + post-run build command.

---

## Layer 1: Per-task file existence gate

**Where:** Inside `_run_agent_loop`, after review passes, before marking COMPLETED.

**Logic:**
- After the agent session's review loop completes, check if the target file exists on disk.
- If `target_file` is set and the file does not exist:
  - If revision attempts remain: send revision message ("The target file was not created. Please create it.") and re-enter the revision loop.
  - If retries exhausted: mark task `NEEDS_REVISION` (best-effort).
- If file exists or no target_file specified: mark task COMPLETED as normal.

This reuses the existing revision loop — a missing file is treated the same as a failed review. The agent gets another chance while the session is still open.

For `review_only` mode (resume path): the file already exists on disk (that's how it entered `review_only`), so this gate is a no-op.

**Files modified:** `orchestrator.py` — `_run_agent_loop` method.

---

## Layer 2: Post-run build verification

**Where:** After all tasks complete in `run()` and `resume()`, before returning.

**How it works:**
- The orchestrator accepts an optional `build_command: str | None` parameter (e.g., `"npx tsc --noEmit"`, `"cargo check"`, `"uv run python -m py_compile ..."`)
- After the spawn loop finishes, if `build_command` is set, run it via `asyncio.subprocess`
- If it exits non-zero: log the stderr, set orchestrator status to `BUILD_FAILED`, print the errors
- If it exits zero: log success

**CLI integration:**
- `conductor run --build-command "npx tsc --noEmit"` passes it through to the orchestrator
- `/resume` also respects the build command
- The build command can also be configured in `.conductor/config.json` so it persists across runs

**What it does NOT do:**
- Does not automatically fix build errors (that's a future enhancement)
- Does not block task completion — it's a final report, not a gate
- Does not parse build output to map errors to specific tasks (future enhancement)

**Files modified:** `orchestrator.py` (new `_post_run_build_check` method), `run.py` (new `--build-command` flag), `delegation.py` (pass through on resume).

---

## What this catches

| Failure mode | Layer 1 (file gate) | Layer 2 (build) |
|---|---|---|
| Target file never created | Yes — forces retry | Yes |
| File created but empty/garbage | No | Yes (syntax error) |
| Cross-file import errors | No | Yes |
| Runtime logic bugs | No | No |

---

## Out of scope

- Automatic error remediation (re-running failed tasks based on build output)
- Per-file syntax checking (language-specific, complex)
- Integration/runtime testing
