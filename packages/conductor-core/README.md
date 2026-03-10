# conductor-ai

AI agent orchestration — a self-organizing team of coding agents that delivers quality, reviewed, tested code.

## What It Does

`conductor-ai` is the Python backend that powers multi-agent orchestration:

- **Orchestrator** — decomposes a feature description into tasks and spawns parallel agents
- **ACP communication** — manages Claude SDK agent sessions with permission handling
- **State management** — tracks agent and task state with atomic writes and file locking
- **CLI** — `conductor run` entry point for launching orchestrated coding sessions

## Installation

```bash
pip install conductor-ai
```

## Quick Start

```bash
# Auto mode: decompose, assign, run, review without human prompts
conductor run "Add a user settings page with theme toggle" --auto

# Interactive mode: approve each agent action
conductor run "Refactor the auth module to use JWT refresh tokens"
```

> **Note:** The import path is `conductor`, not `conductor-ai`:
> ```python
> from conductor.state import StateManager
> ```

## Dashboard

To monitor agents live in a web UI, run the dashboard alongside the backend:

```bash
# Terminal 1: start orchestrator with dashboard port
conductor run "..." --auto --dashboard-port 8765

# Terminal 2: serve the dashboard
npx conductor-dashboard
```

## Documentation

See [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md) for a full walkthrough.

## License

MIT — see [LICENSE](../../LICENSE) at the repo root.
