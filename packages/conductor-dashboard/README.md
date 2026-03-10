# conductor-dashboard

Web dashboard for Conductor AI agent orchestration — monitor running agents, watch live output streams, and intervene when needed.

## What It Provides

- **Agent overview** — real-time table of all agents with status, task assignment, and review state
- **Live stream** — SSE-powered output stream from each agent as it works
- **Intervention controls** — pause agents, redirect tasks, or provide feedback mid-run
- **Notifications** — toast alerts for task completion, escalations, and review decisions

## Installation

```bash
npm install -g conductor-dashboard
```

## Usage

```bash
# Serve dashboard on default port 4173
conductor-dashboard

# Serve on a custom port
conductor-dashboard 8080
```

Then open [http://localhost:4173](http://localhost:4173) in your browser.

## Requirements

The dashboard requires the Python `conductor-ai` backend running with the `--dashboard-port` flag:

```bash
# Start the orchestrator with dashboard support
conductor run "Add a settings page" --auto --dashboard-port 8765
```

Install the backend with:

```bash
pip install conductor-ai
```

## License

MIT — see [LICENSE](https://github.com/conductor-ai/conductor/blob/main/LICENSE).
