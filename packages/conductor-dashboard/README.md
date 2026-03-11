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

## Production Deployment

In production, the dashboard is a static site served by the `conductor-dashboard` bin script (sirv), while the WebSocket endpoint is served by the FastAPI backend (`conductor-ai`). These run on different ports, so you must tell the dashboard where to find the backend.

### Two-server architecture

| Server | Purpose | Default port |
|--------|---------|-------------|
| `conductor-dashboard` (Node/sirv) | Serves the static HTML/JS/CSS bundle | 4173 |
| `conductor-ai` (FastAPI/uvicorn) | Handles WebSocket connections (`/ws`) | 8765 |

### Starting both servers

```bash
# Terminal 1 — start the orchestrator/backend
conductor run "Add a settings page" --auto --dashboard-port 8765

# Terminal 2 — start the dashboard, pointing at the backend
conductor-dashboard --backend-url http://127.0.0.1:8765
```

Or with a custom dashboard port:

```bash
conductor-dashboard 8080 --backend-url http://127.0.0.1:8765
```

When `--backend-url` is provided, the bin script injects a `<script>` tag into the served HTML that sets `window.__CONDUCTOR_BACKEND_URL__`. The dashboard reads this global at startup and connects its WebSocket to `ws://127.0.0.1:8765/ws` instead of the same-origin default.

### Development mode

In development (`pnpm dev`), Vite's dev server proxies `/ws` requests to the FastAPI backend automatically. No `--backend-url` flag is needed:

```bash
# In the conductor-dashboard package directory
pnpm dev
```

## License

MIT — see [LICENSE](https://github.com/conductor-ai/conductor/blob/main/LICENSE).
