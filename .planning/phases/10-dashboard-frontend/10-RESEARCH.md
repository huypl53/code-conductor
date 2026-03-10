# Phase 10: Dashboard Frontend - Research

**Researched:** 2026-03-11
**Domain:** React 19 real-time WebSocket dashboard with Tailwind CSS 4
**Confidence:** HIGH

## Summary

This phase builds the web dashboard frontend that connects to the Phase 9 backend (FastAPI with WebSocket). The stack is fully fixed: React 19.2, Vite 7.3, TypeScript 5.9, Tailwind CSS 4.2, Biome 2.4. The scaffold already exists at `packages/conductor-dashboard/` with placeholder content.

The core technical challenge is managing real-time WebSocket state in React -- receiving an initial full state snapshot, then applying incremental DeltaEvent updates to keep the UI in sync. The UI requires a layered card pattern: collapsed agent summaries by default, expandable to recent actions, expandable further to live stream. Interventions (cancel, redirect, feedback) must be sent back to the server.

**Primary recommendation:** Build a custom `useConductorSocket` hook (no third-party WebSocket library needed -- the protocol is simple). Use `useReducer` for state management with a reducer that handles both full snapshots and delta events. Keep all UI components as plain React + Tailwind with no component library. Use Sonner for toast notifications on smart events.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DASH-01 | Web dashboard shows agent status summary (name, role, current task, progress) | ConductorState.agents has id, name, role, current_task_id, status; ConductorState.tasks has title, status -- join on current_task_id |
| DASH-02 | Dashboard supports expandable detail view per agent (recent actions, files modified, current activity) | DeltaEvents provide task_status_changed, task_assigned events; accumulate per-agent action history from events; Task model has target_file, material_files |
| DASH-03 | Dashboard supports live stream view per agent (real-time tool calls, streaming output) | WebSocket delivers DeltaEvent stream; filter by agent_id for per-agent live view |
| DASH-05 | Dashboard handles conversation verbosity with layered visibility | Three-tier card expansion pattern: collapsed (summary) -> expanded (recent actions) -> live stream; Tailwind transition utilities for smooth expand/collapse |
| DASH-06 | User can intervene from dashboard (cancel, redirect, provide feedback to agents) | Backend WebSocket currently ignores received messages -- **must extend server.py to handle incoming commands over WebSocket**; CLI already implements cancel/redirect/feedback via orchestrator methods |
</phase_requirements>

## Standard Stack

### Core (Already Installed)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| react | 19.2.4 | UI framework | Installed |
| react-dom | 19.2.4 | DOM rendering | Installed |
| vite | 7.3.1 | Build tool + dev server | Installed |
| typescript | 5.9.3 | Type safety | Installed |
| tailwindcss | 4.2.1 | Utility-first CSS | Installed |
| @tailwindcss/vite | 4.2.1 | Vite plugin for Tailwind | Installed |
| @vitejs/plugin-react | 5.1.4 | React Fast Refresh for Vite | Installed |
| @biomejs/biome | 2.4.6 | Linter + formatter | Installed |

### New Dependencies to Add
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| sonner | 2.0.7 | Toast notifications for smart events | 2-3KB gzipped, React 19 compatible (peer dep: ^18 or ^19), Tailwind-friendly, widely adopted |

### Testing Dependencies (devDependencies)
| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| vitest | 4.0.18 | Test runner | First-class Vite integration, Jest-compatible API, fast |
| @testing-library/react | 16.3.2 | Component testing | Standard React testing, renders components and queries DOM |
| @testing-library/jest-dom | 6.9.1 | DOM matchers | toBeInTheDocument(), toHaveTextContent(), etc. |
| @testing-library/user-event | 14.6.1 | User interaction simulation | click, type, keyboard events |
| jsdom | 28.1.0 | DOM environment for tests | More comprehensive browser API than happy-dom; needed for WebSocket mocking |

### Alternatives Considered
| Instead of | Could Use | Why Not |
|------------|-----------|---------|
| Custom WebSocket hook | react-use-websocket 4.13.0 | No declared React 19 peer dep; our WebSocket protocol is simple (JSON messages, reconnect); custom hook is ~40 lines, zero dependency risk |
| sonner | react-hot-toast | Both work; sonner is smaller (2-3KB vs 5KB), supports React 19 via peer deps, better dark mode |
| No component library | shadcn/ui, Radix UI | Overkill for a developer dashboard with ~5 component types; plain Tailwind is sufficient |
| jsdom | happy-dom 20.8.3 | happy-dom is faster but less complete; jsdom is safer for WebSocket/event testing |

**Installation:**
```bash
cd packages/conductor-dashboard
npm install sonner
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── hooks/
│   ├── useConductorSocket.ts    # WebSocket connection + state management
│   └── useConductorSocket.test.ts
├── components/
│   ├── AgentCard.tsx             # Collapsible card per agent
│   ├── AgentCard.test.tsx
│   ├── AgentGrid.tsx             # Grid layout of agent cards
│   ├── LiveStream.tsx            # Real-time event stream view
│   ├── InterventionPanel.tsx     # Cancel/redirect/feedback actions
│   ├── StatusBadge.tsx           # Status indicator component
│   └── NotificationProvider.tsx  # Sonner Toaster wrapper
├── types/
│   └── conductor.ts             # TypeScript types mirroring backend models
├── lib/
│   └── messages.ts              # WebSocket message serialization
├── test/
│   └── setup.ts                 # Vitest setup (jest-dom matchers)
├── App.tsx                      # Root layout
├── main.tsx                     # Entry point
└── index.css                    # Tailwind import
```

### Pattern 1: Custom WebSocket Hook with useReducer

**What:** A single hook manages the WebSocket connection, receives messages, and maintains the full ConductorState plus accumulated event history via useReducer.

**When to use:** Always -- this is the central state management for the entire dashboard.

**Example:**
```typescript
// types/conductor.ts — mirror backend models
interface Task {
  id: string;
  title: string;
  description: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "blocked";
  assigned_agent: string | null;
  outputs: Record<string, unknown>;
  requires: string[];
  produces: string[];
  target_file: string;
  material_files: string[];
  review_status: "pending" | "approved" | "needs_revision";
  revision_count: number;
}

interface AgentRecord {
  id: string;
  name: string;
  role: string;
  current_task_id: string | null;
  status: "idle" | "working" | "waiting" | "done";
  session_id: string | null;
  memory_file: string | null;
  started_at: string | null;
}

interface ConductorState {
  version: string;
  tasks: Task[];
  agents: AgentRecord[];
  dependencies: { task_id: string; depends_on: string }[];
  updated_at: string;
}

type EventType =
  | "task_assigned"
  | "task_status_changed"
  | "task_completed"
  | "task_failed"
  | "agent_registered"
  | "agent_status_changed"
  | "intervention_needed";

interface DeltaEvent {
  type: EventType;
  task_id: string | null;
  agent_id: string | null;
  payload: Record<string, unknown>;
  is_smart_notification: boolean;
}

// hooks/useConductorSocket.ts
type Action =
  | { type: "snapshot"; state: ConductorState }
  | { type: "delta"; event: DeltaEvent }
  | { type: "connected" }
  | { type: "disconnected" };

interface DashboardState {
  conductorState: ConductorState | null;
  events: DeltaEvent[];       // accumulated event history
  connected: boolean;
}

function reducer(state: DashboardState, action: Action): DashboardState {
  switch (action.type) {
    case "snapshot":
      return { ...state, conductorState: action.state };
    case "delta":
      return {
        ...state,
        events: [...state.events, action.event],
        // Apply delta to conductorState based on event type
        conductorState: applyDelta(state.conductorState, action.event),
      };
    case "connected":
      return { ...state, connected: true };
    case "disconnected":
      return { ...state, connected: false };
  }
}
```

**Key design decisions:**
- First message from WebSocket is always a full ConductorState snapshot (belt-and-suspenders pattern from backend)
- Subsequent messages are DeltaEvent JSON -- detect by checking for `type` field (DeltaEvent has it, ConductorState does not; ConductorState has `version`)
- The `events` array accumulates all DeltaEvents for the "recent actions" and "live stream" views
- `applyDelta` updates the local ConductorState in-place based on event type (e.g., agent_status_changed updates the agent's status field)

### Pattern 2: Layered Card Expansion (Three-tier)

**What:** Each agent is rendered as a card with three visibility tiers: collapsed (summary only), expanded (recent actions), and live stream (real-time events).

**When to use:** DASH-05 requirement -- layered visibility.

**Example:**
```typescript
type ExpansionLevel = "collapsed" | "detail" | "stream";

function AgentCard({ agent, events }: AgentCardProps) {
  const [level, setLevel] = useState<ExpansionLevel>("collapsed");

  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm">
      {/* Always visible: summary row */}
      <button
        className="flex w-full items-center justify-between p-4"
        onClick={() => setLevel(prev =>
          prev === "collapsed" ? "detail" : "collapsed"
        )}
      >
        <div className="flex items-center gap-3">
          <StatusBadge status={agent.status} />
          <div>
            <span className="font-medium">{agent.name}</span>
            <span className="ml-2 text-sm text-gray-500">{agent.role}</span>
          </div>
        </div>
        <ChevronIcon expanded={level !== "collapsed"} />
      </button>

      {/* Tier 2: Recent actions */}
      {level !== "collapsed" && (
        <div className="border-t px-4 pb-4">
          <RecentActions events={agentEvents} />
          <button
            className="mt-2 text-sm text-blue-600"
            onClick={() => setLevel(prev =>
              prev === "detail" ? "stream" : "detail"
            )}
          >
            {level === "detail" ? "Show live stream" : "Hide live stream"}
          </button>
        </div>
      )}

      {/* Tier 3: Live stream */}
      {level === "stream" && (
        <div className="border-t bg-gray-50 p-4 font-mono text-xs">
          <LiveStream agentId={agent.id} events={events} />
        </div>
      )}
    </div>
  );
}
```

### Pattern 3: Intervention Commands over WebSocket

**What:** Send intervention commands (cancel, redirect, feedback) as JSON messages over the existing WebSocket connection.

**When to use:** DASH-06 requirement.

**Critical finding:** The backend WebSocket endpoint currently calls `receive_text()` but ignores the content. **The backend must be extended to parse incoming messages as intervention commands.** This requires a small backend change in `server.py`.

**Proposed message format (frontend sends):**
```typescript
interface InterventionCommand {
  action: "cancel" | "redirect" | "feedback";
  agent_id: string;
  message?: string;  // for feedback and redirect
}

// In the useConductorSocket hook:
function sendIntervention(command: InterventionCommand) {
  if (ws.current?.readyState === WebSocket.OPEN) {
    ws.current.send(JSON.stringify(command));
  }
}
```

**Backend change needed (server.py):**
```python
# In websocket_endpoint, replace the bare receive_text() with:
while True:
    data = await websocket.receive_text()
    try:
        command = json.loads(data)
        await handle_intervention(command, orchestrator)
    except Exception:
        pass  # ignore malformed messages
```

This backend change is small but **must be planned as a Wave 0 task** or handled as part of the frontend phase.

### Anti-Patterns to Avoid
- **Polling GET /state instead of using WebSocket:** The GET endpoint exists for initial load fallback, not as a polling target. Always use WebSocket for live data.
- **Storing full ConductorState on every DeltaEvent:** Don't re-fetch the full state on each delta. Apply deltas incrementally to the local state.
- **Unthrottled re-renders on rapid events:** During heavy agent activity, many DeltaEvents arrive quickly. Use React 19's automatic batching (already built-in) but also consider limiting the `events` array size (e.g., keep last 200 events per agent).
- **Direct DOM manipulation for animations:** Use Tailwind's `transition-all`, `duration-200`, `overflow-hidden` utilities for expand/collapse. No need for Framer Motion or similar.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Toast notifications | Custom toast system | Sonner | Positioning, stacking, auto-dismiss, accessibility, animation -- deceptively complex |
| WebSocket reconnection | Basic retry logic | Exponential backoff in custom hook | Must handle: connection drop, server restart, tab sleep/wake, network change |
| State type definitions | Freehand types | Mirror backend models exactly | Backend Pydantic models are the source of truth -- copy field names and types 1:1 |
| Status badge colors | Ad-hoc className logic | A StatusBadge component with a status-to-color map | Ensures consistency across all cards and avoids color drift |

**Key insight:** The dashboard is a read-heavy, event-driven UI. The complexity is in state management and event processing, not in component variety. Keep the component count small and the data flow clear.

## Common Pitfalls

### Pitfall 1: CORS Blocking in Development
**What goes wrong:** Vite dev server runs on port 5173; FastAPI backend runs on a different port (e.g., 8000). Browser blocks cross-origin requests.
**Why it happens:** No CORS middleware on the backend server.
**How to avoid:** Configure Vite proxy in `vite.config.ts`:
```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/state": "http://127.0.0.1:8000",
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
      },
    },
  },
});
```
**Warning signs:** `Failed to fetch` or WebSocket connection refused in console.

### Pitfall 2: First Message Is a Full State, Not a DeltaEvent
**What goes wrong:** Code treats all WebSocket messages as DeltaEvent and crashes on the initial snapshot.
**Why it happens:** Backend sends full ConductorState as first message (belt-and-suspenders), then switches to DeltaEvent messages.
**How to avoid:** Detect message type by checking for `version` field (ConductorState) vs. `type` field (DeltaEvent):
```typescript
function handleMessage(data: string) {
  const parsed = JSON.parse(data);
  if ("version" in parsed) {
    dispatch({ type: "snapshot", state: parsed as ConductorState });
  } else if ("type" in parsed) {
    dispatch({ type: "delta", event: parsed as DeltaEvent });
  }
}
```
**Warning signs:** `Cannot read property 'type' of undefined` on first load.

### Pitfall 3: Memory Leak from Unbounded Event History
**What goes wrong:** The events array grows indefinitely during long sessions, causing memory pressure and slow renders.
**Why it happens:** Every DeltaEvent is appended and never removed.
**How to avoid:** Cap the events array (e.g., keep last 500 total or last 100 per agent). Implement in the reducer.

### Pitfall 4: WebSocket Not Reconnecting After Tab Sleep
**What goes wrong:** User switches tabs for a while, comes back, and the dashboard shows stale data.
**Why it happens:** Browser may close idle WebSocket connections; no reconnect logic.
**How to avoid:** Implement reconnect with exponential backoff in the custom hook. On reconnect, the backend sends a fresh full snapshot automatically (belt-and-suspenders), so the client state is fully recovered.

### Pitfall 5: Intervention Commands Require Backend Changes
**What goes wrong:** Frontend sends intervention commands but nothing happens.
**Why it happens:** The backend `websocket_endpoint` currently ignores received messages.
**How to avoid:** Plan a backend extension task in Wave 0 to handle incoming WebSocket messages as intervention commands. The orchestrator methods (`cancel_agent`, `inject_guidance`) already exist -- the backend just needs to wire WebSocket messages to them.

## Code Examples

### Vitest Setup Configuration

```typescript
// vite.config.ts (updated with test config)
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/state": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
```

```typescript
// src/test/setup.ts
import "@testing-library/jest-dom/vitest";
```

```json
// Add to package.json scripts:
{
  "test": "vitest run",
  "test:watch": "vitest"
}
```

### WebSocket Hook with Reconnection

```typescript
// hooks/useConductorSocket.ts — core pattern
function useConductorSocket(url: string) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout>>();
  const retryCount = useRef(0);

  const connect = useCallback(() => {
    const ws = new WebSocket(url);

    ws.onopen = () => {
      retryCount.current = 0;
      dispatch({ type: "connected" });
    };

    ws.onmessage = (event) => {
      const parsed = JSON.parse(event.data);
      if ("version" in parsed) {
        dispatch({ type: "snapshot", state: parsed });
      } else if ("type" in parsed) {
        dispatch({ type: "delta", event: parsed });
      }
    };

    ws.onclose = () => {
      dispatch({ type: "disconnected" });
      // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
      const delay = Math.min(1000 * 2 ** retryCount.current, 30000);
      retryCount.current += 1;
      reconnectTimeout.current = setTimeout(connect, delay);
    };

    wsRef.current = ws;
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimeout.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const sendIntervention = useCallback((command: InterventionCommand) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(command));
    }
  }, []);

  return { ...state, sendIntervention };
}
```

### Smart Notification Integration

```typescript
// In App.tsx or NotificationProvider.tsx
import { Toaster, toast } from "sonner";

function useSmartNotifications(events: DeltaEvent[]) {
  const lastProcessed = useRef(0);

  useEffect(() => {
    const newEvents = events.slice(lastProcessed.current);
    lastProcessed.current = events.length;

    for (const event of newEvents) {
      if (!event.is_smart_notification) continue;

      switch (event.type) {
        case "task_completed":
          toast.success(`Task ${event.task_id} completed`);
          break;
        case "task_failed":
          toast.error(`Task ${event.task_id} failed`);
          break;
        case "intervention_needed":
          toast.warning(`Agent ${event.agent_id} needs intervention`, {
            duration: Infinity,  // Don't auto-dismiss
          });
          break;
      }
    }
  }, [events]);
}
```

### Component Test Example

```typescript
// components/AgentCard.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AgentCard } from "./AgentCard";

const mockAgent = {
  id: "agent-1",
  name: "Frontend Builder",
  role: "developer",
  current_task_id: "task-1",
  status: "working" as const,
  session_id: null,
  memory_file: null,
  started_at: null,
};

test("renders agent name and role in collapsed state", () => {
  render(<AgentCard agent={mockAgent} events={[]} tasks={[]} />);
  expect(screen.getByText("Frontend Builder")).toBeInTheDocument();
  expect(screen.getByText("developer")).toBeInTheDocument();
});

test("expands to show detail view on click", async () => {
  const user = userEvent.setup();
  render(<AgentCard agent={mockAgent} events={[]} tasks={[]} />);
  await user.click(screen.getByRole("button"));
  expect(screen.getByText(/recent actions/i)).toBeInTheDocument();
});
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| useEffect + useState for WebSocket | Custom hook with useReducer | React 18+ (2022) | Cleaner state transitions, batched updates |
| Redux/Zustand for real-time state | useReducer + context (for small apps) | Ongoing | No external state library needed for <10 components |
| CSS-in-JS (styled-components) | Tailwind utility classes | Tailwind v3+ (2022) | Zero runtime CSS overhead |
| Jest + enzyme | Vitest + React Testing Library | 2023+ | 10x faster test runs, better React 18/19 support |
| react-toastify (heavy) | Sonner (lightweight) | 2024+ | 2-3KB vs 30KB+, better animations |

**Deprecated/outdated:**
- **Enzyme:** Does not support React 18+, let alone 19. Use React Testing Library.
- **Create React App:** Deprecated. Vite is the standard.
- **Tailwind CSS v3 config files:** Tailwind v4 uses `@import "tailwindcss"` in CSS, no `tailwind.config.js` needed. Already configured correctly in the scaffold.

## Open Questions

1. **Backend Intervention Endpoint**
   - What we know: CLI uses `orchestrator.cancel_agent()` and `orchestrator.inject_guidance()`. The WebSocket `receive_text()` currently ignores incoming messages.
   - What's unclear: Whether the backend extension should happen as part of Phase 10 or requires a separate backend task.
   - Recommendation: Add a small backend extension task in Wave 0 of this phase. The change is ~15 lines in `server.py` -- parse incoming WebSocket messages as JSON commands and route to orchestrator methods. The orchestrator reference needs to be passed to `create_app()`.

2. **Event History Granularity**
   - What we know: DeltaEvents provide task/agent status changes. They do NOT include granular tool calls or file edit details.
   - What's unclear: Whether DASH-03 ("real-time tool calls, streaming output") can be fully satisfied with current DeltaEvent types alone.
   - Recommendation: For v1, the "live stream" view shows DeltaEvents filtered by agent. This covers status transitions and task assignments. True tool-call streaming would require backend ACP event forwarding (v2 scope). Document this as a known limitation.

3. **Dashboard Port Configuration for Vite Proxy**
   - What we know: Backend port is user-specified via `--dashboard-port`. Vite proxy needs a fixed target.
   - What's unclear: Best way to make the proxy port configurable.
   - Recommendation: Default to port 8000 in vite.config.ts proxy. Allow override via `VITE_API_PORT` env variable. In production, both are served from the same origin (no proxy needed).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Vitest 4.0.18 + React Testing Library 16.3.2 |
| Config file | `vite.config.ts` (test section) -- Wave 0 |
| Quick run command | `cd packages/conductor-dashboard && npx vitest run` |
| Full suite command | `cd packages/conductor-dashboard && npx vitest run --coverage` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | Agent summary card renders name, role, task, status | unit | `npx vitest run src/components/AgentCard.test.tsx` | No -- Wave 0 |
| DASH-02 | Expanded view shows recent actions and files | unit | `npx vitest run src/components/AgentCard.test.tsx` | No -- Wave 0 |
| DASH-03 | Live stream view shows real-time events | unit | `npx vitest run src/components/LiveStream.test.tsx` | No -- Wave 0 |
| DASH-05 | Cards default collapsed, expand on click | unit | `npx vitest run src/components/AgentCard.test.tsx` | No -- Wave 0 |
| DASH-06 | Intervention actions send WebSocket commands | unit | `npx vitest run src/components/InterventionPanel.test.tsx` | No -- Wave 0 |
| -- | WebSocket hook connects, receives snapshot, applies deltas | unit | `npx vitest run src/hooks/useConductorSocket.test.ts` | No -- Wave 0 |
| -- | Smart notifications fire on smart events | unit | `npx vitest run src/components/NotificationProvider.test.tsx` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `cd packages/conductor-dashboard && npx vitest run`
- **Per wave merge:** `cd packages/conductor-dashboard && npx vitest run`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `vite.config.ts` -- add test configuration section (globals, jsdom, setupFiles)
- [ ] `src/test/setup.ts` -- jest-dom matcher setup
- [ ] `package.json` -- add test scripts and dev dependencies
- [ ] Install: `npm install sonner && npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom`
- [ ] `src/types/conductor.ts` -- TypeScript types mirroring backend models (shared by all tests)

## Sources

### Primary (HIGH confidence)
- Backend source code: `packages/conductor-core/src/conductor/dashboard/server.py`, `events.py`, `watcher.py` -- exact API contract
- Backend models: `packages/conductor-core/src/conductor/state/models.py` -- exact data shapes
- Existing scaffold: `packages/conductor-dashboard/package.json` -- installed versions confirmed
- npm registry (via `npm view`) -- confirmed latest versions of all recommended packages

### Secondary (MEDIUM confidence)
- [Vitest official docs](https://vitest.dev/guide/) -- test configuration patterns
- [React Testing Library setup](https://testing-library.com/docs/) -- setup patterns
- [Sonner GitHub](https://github.com/emilkowalski/sonner) -- React 19 compatibility confirmed via peer deps

### Tertiary (LOW confidence)
- WebSearch results on React 19 WebSocket patterns -- general community patterns, not React 19-specific docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions confirmed via npm registry and installed package.json
- Architecture: HIGH -- patterns derived from actual backend API contract (read source code)
- Pitfalls: HIGH -- CORS and first-message detection verified against actual server.py code
- Intervention gap: HIGH -- confirmed by reading server.py line 103 (receive_text with no processing)

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable stack, no fast-moving dependencies)
