# Getting Started with Conductor

Conductor is an AI agent orchestration tool for coding tasks. You describe a feature or task in plain language, and Conductor decomposes it into parallel sub-tasks, spawns specialized AI coding agents to handle each one, monitors their progress, reviews their output, and delivers the result — all while keeping you in control when you want to intervene.

---

## Prerequisites

Before installing Conductor, make sure you have:

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

**Option 1: Export in your shell**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

**Option 2: Use a `.env` file in your project root**

```
ANTHROPIC_API_KEY=sk-ant-...
```

Conductor automatically reads `.env` files in the working directory.

---

## Your First Session (CLI — Automatic Mode)

Change into any project directory — a repository with existing code works best, but an empty directory is fine too.

```bash
cd ~/my-project
conductor run "Add a hello world endpoint to the API" --auto
```

What happens:

1. The orchestrator reviews your request and confirms it is clear and achievable.
2. It decomposes the task into parallel sub-tasks (e.g., route definition, handler logic, tests).
3. It spawns one AI agent per sub-task and monitors all of them simultaneously.
4. Each agent works independently, writes code, and reports back when done.
5. The orchestrator reviews each agent's output. If revisions are needed, it sends feedback and the agent retries.
6. When all sub-tasks pass review, the session ends.

While the session runs, you will see a live agent status table in your terminal:

```
 Agent              Task                              Status
 ─────────────────────────────────────────────────── ───────────
 agent-abc-001      Add hello world route handler     running
 agent-def-002      Add integration test for route    running
 agent-ghi-003      Update OpenAPI docs               complete
```

---

## Your First Session (Interactive Mode)

Run without `--auto` to enable interactive mode, where the orchestrator asks clarifying questions before decomposing the task and you can intervene during execution:

```bash
conductor run "Add dark mode to settings"
```

The orchestrator will ask one or more clarifying questions (e.g., "Should this preference be persisted to localStorage?"). Answer in plain language and press Enter.

During the session, you can:

| Command       | Effect                                           |
|---------------|--------------------------------------------------|
| `cancel`      | Cancel a specific agent and reassign the task    |
| `feedback`    | Send a message to a running agent                |
| `redirect`    | Give the agent a new direction mid-task          |

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

## Project Configuration (Optional)

Conductor supports two optional configuration directories in your project root:

**`.claude/` and `CLAUDE.md`** — Place project-specific context here. Agents read `CLAUDE.md` at session start to understand your codebase conventions, preferred patterns, and constraints. Example:

```markdown
# My Project

- Use TypeScript strict mode
- All API routes go in src/api/
- Write tests in Vitest, not Jest
```

**`.memory/`** — Agents write cross-session knowledge here. If an agent discovers something important about your codebase (e.g., a tricky async pattern), it saves a note to `.memory/<agent-name>.md` so future agents can benefit from the same knowledge without rediscovering it.

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

Conductor could not find your API key. Set it in your shell:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or add it to a `.env` file in your project root. Verify with:

```bash
echo $ANTHROPIC_API_KEY
```

---

**Dashboard not connecting**

Make sure the `--dashboard-port` value passed to `conductor run` matches the backend port that the dashboard frontend is trying to reach. By default the frontend connects to `http://localhost:8000`. If you used a different port, you may need to open the dashboard with a port override.

Also verify the backend process is running:

```bash
conductor run "..." --auto --dashboard-port 8000
```

Check that port 8000 is not already in use by another process:

```bash
lsof -i :8000
```

---

## Next Steps

- Read the [README](../README.md) for a full architecture overview — how the orchestrator, agents, ACP communication layer, and state system fit together.
- Explore `--auto` vs interactive mode to find your preferred workflow.
- For large features, try breaking your request into broad phases: Conductor will decompose each one in parallel.
- Set up `CLAUDE.md` with your project conventions for more targeted agent output.
