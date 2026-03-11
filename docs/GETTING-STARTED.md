# Getting Started with Conductor

Conductor is an AI agent orchestration tool for coding tasks. You describe a feature in plain language, and Conductor decomposes it into parallel sub-tasks, spawns specialized AI coding agents, monitors their progress, reviews their output, verifies the results, and delivers working code.

---

## Prerequisites

- **Python 3.12 or later** — required for the conductor-ai package
- **Node.js 22 or later** — optional, only needed for the web dashboard
- **An Anthropic API key** — get one at [console.anthropic.com](https://console.anthropic.com)

---

## Installation

Install the core Conductor CLI via pip:

```bash
pip install conductor-ai
```

Optionally, install the web dashboard (requires Node.js 22+):

```bash
npm install -g conductor-dashboard
```

Verify the CLI is available:

```bash
conductor --help
```

> **Note:** If `conductor` is not found after installation, ensure your pip binary directory is in your `PATH`. On most systems this is `~/.local/bin`. Add it with: `export PATH="$HOME/.local/bin:$PATH"`

---

## Configuration

Conductor reads your Anthropic API key from the environment. Set it before running any session.

**Option 1: Export in your shell (current session only)**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Option 2: Add to your shell profile (persistent across sessions)**

```bash
echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
source ~/.bashrc
```

---

## Interactive Chat (Recommended)

The fastest way to start is the interactive chat TUI. Run `conductor` with no arguments:

```bash
cd ~/my-project
conductor
```

You'll see a `conductor>` prompt. Type requests naturally:

```
conductor> Add a hello world endpoint to the API
Handling directly — reading existing routes...
✓ Created src/api/hello.ts
✓ Updated src/api/index.ts

conductor> Now add OAuth login with Google
Delegating to team...
Dashboard: http://127.0.0.1:8321

 Agent              Task                           Status
 ─────────────────────────────────────────────── ───────────
 agent-abc-001      OAuth provider config           running
 agent-def-002      Login callback handler          running
 agent-ghi-003      Session middleware               waiting
```

The orchestrator decides whether to handle requests directly (simple edits) or delegate to a sub-agent team (complex features). You see a delegation decision for every request.

### Slash commands

| Command    | Effect                                     |
|------------|--------------------------------------------|
| `/help`    | Show all available commands                 |
| `/status`  | Show active sub-agents and their progress   |
| `/resume`  | Resume a previous orchestration             |
| `/exit`    | Exit the chat                               |

### Session persistence

Chat sessions are automatically saved to disk. If the process crashes or you exit, resume where you left off:

```bash
conductor --resume pick
```

This shows a numbered list of recent sessions. Select one to restore the full conversation history.

---

## Batch Mode (Automatic)

For fire-and-forget execution, use `conductor run` with `--auto`:

```bash
cd ~/my-project
conductor run "Add a REST endpoint for user profiles" --auto
```

What happens:

1. The orchestrator reviews your request and confirms it is clear and achievable.
2. It decomposes the task into parallel sub-tasks (e.g., route definition, handler logic, tests).
3. It spawns one AI agent per sub-task and monitors all of them simultaneously.
4. Each agent works independently, writes code, and reports back when done.
5. The orchestrator reviews each agent's output. If revisions are needed, it sends structured feedback and the agent retries.
6. Target files are verified — if an agent was marked complete but its output file doesn't exist on disk, it's sent back for another attempt.
7. When all sub-tasks pass review and verification, the session ends.

While the session runs, you see a live agent status table in your terminal.

---

## Batch Mode (Interactive)

Run without `--auto` to enable interactive mode, where the orchestrator asks clarifying questions before decomposing the task and you can intervene during execution:

```bash
conductor run "Add dark mode to settings"
```

During the session, you can:

| Command       | Effect                                           |
|---------------|--------------------------------------------------|
| `cancel`      | Cancel a specific agent and reassign the task    |
| `feedback`    | Send a message to a running agent                |
| `redirect`    | Give the agent a new direction mid-task          |

---

## Build Verification

Conductor can run a build command after all tasks complete to catch cross-file errors (broken imports, type mismatches, syntax errors) that per-task review cannot detect.

**Via CLI flag:**

```bash
conductor run "Add payment processing" --auto --build-command "npx tsc --noEmit"
```

**Via config file** (persists across runs):

Create `.conductor/config.json` in your project root:

```json
{
  "build_command": "npx tsc --noEmit"
}
```

The CLI flag takes priority over the config file. If both are set, the CLI flag wins.

**Common build commands:**

| Language   | Command                          |
|------------|----------------------------------|
| TypeScript | `npx tsc --noEmit`               |
| Rust       | `cargo check`                    |
| Go         | `go build ./...`                 |
| Python     | `mypy src/` or `ruff check src/` |
| C/C++      | `make` or `cmake --build build`  |

After all tasks finish, you'll see:

```
Build verification: PASSED
```

Or, if there are errors:

```
Build verification: FAILED (exit 1)
src/components/TimeGrid.tsx(5,23): error TS2307: Cannot find module './EventChip'
```

Build failures are reported but do not roll back completed tasks. They serve as a diagnostic for what still needs fixing.

---

## Resuming Interrupted Work

### Batch mode resume

If an orchestration is interrupted (crash, Ctrl+C, network issue), resume it:

```bash
conductor run --resume --repo ~/my-project
```

Resume is smart about what it re-runs:

| Task state | File on disk? | Action |
|------------|---------------|--------|
| Completed | Yes | Skip (already done) |
| Completed | No | Re-run (file missing — the original agent failed silently) |
| In progress | Yes | Review only (file exists, just needs verification) |
| In progress | No | Full re-run (agent didn't finish) |
| Pending | — | Run normally |

This verification catches the case where an agent was marked complete but never actually wrote its output file.

### Chat session resume

```bash
# Pick from recent sessions
conductor --resume pick

# Resume a specific session by ID
conductor --resume abc123
```

---

## Using the Web Dashboard (Optional)

The dashboard gives you a real-time visual view of agent activity with expandable detail cards and intervention controls.

**Step 1:** Start a session with the dashboard enabled:

```bash
conductor run "Refactor the authentication module" --auto --dashboard-port 8000
```

**Step 2:** In a separate terminal, start the dashboard server:

```bash
conductor-dashboard 4173
```

**Step 3:** Open your browser:

```
http://localhost:4173
```

You will see:

- **Agent cards** — one per running agent, showing task name and current status
- **Expandable detail** — click any card to see the agent's live output stream
- **Intervention controls** — cancel, send feedback, or redirect agents directly from the UI

---

## Project Configuration

Conductor supports optional configuration in your project root:

### `CLAUDE.md`

Agents read this at session start to understand your codebase conventions:

```markdown
# My Project

- Use TypeScript strict mode
- All API routes go in src/api/
- Write tests in Vitest, not Jest
```

### `.conductor/config.json`

Persistent orchestrator configuration:

```json
{
  "build_command": "npx tsc --noEmit"
}
```

| Key | Type | Description |
|-----|------|-------------|
| `build_command` | `string` | Shell command to run after all tasks complete |

### `.memory/`

Agents write cross-session knowledge here. If an agent discovers something important about your codebase (e.g., a tricky async pattern), it saves a note so future agents can benefit without rediscovering it.

---

## Troubleshooting

**`conductor: command not found`**

The pip binary directory is not in your `PATH`. Find it with:

```bash
python3 -m site --user-base
```

Then add `<output>/bin` to your `PATH` in `~/.bashrc` or `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Restart your shell or run `source ~/.bashrc`.

---

**`ANTHROPIC_API_KEY not set`**

Set it in your shell:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Verify with `echo $ANTHROPIC_API_KEY`.

---

**Dashboard not connecting**

Make sure the `--dashboard-port` value matches the backend port the frontend connects to. Verify the backend is running and the port isn't in use:

```bash
lsof -i :8000
```

---

**Build verification shows FAILED but tasks are complete**

Build verification is a post-run report — it does not roll back completed tasks. The errors shown are real build errors (type mismatches, broken imports, etc.) that need manual fixing or another conductor run to address.

---

**Resume re-runs tasks that were already complete**

This means the completed task's target file is missing from disk. The agent was marked complete but never wrote the file. Resume correctly detects this and re-runs the task. This is expected behavior.

---

## Next Steps

- Read the [README](../README.md) for a full architecture overview.
- Set up `.conductor/config.json` with your preferred `build_command`.
- Add `CLAUDE.md` with your project conventions for more targeted agent output.
- See [CONTRIBUTING.md](../CONTRIBUTING.md) if you want to contribute to Conductor.
