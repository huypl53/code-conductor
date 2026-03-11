/**
 * Conductor Dashboard root application component.
 *
 * Connects to the backend WebSocket, manages real-time state, and renders
 * the agent grid with live-updating status.
 */
import { useConductorSocket } from "./hooks/useConductorSocket";
import { AgentGrid } from "./components/AgentGrid";
import { NotificationProvider, useSmartNotifications } from "./components/NotificationProvider";

/**
 * Derive the WebSocket URL for the backend.
 *
 * Priority:
 * 1. `window.__CONDUCTOR_BACKEND_URL__` — injected by the bin script when running in
 *    production with a separate FastAPI backend (e.g. "http://127.0.0.1:8000").
 *    The http/https scheme is replaced with ws/wss and "/ws" is appended.
 * 2. Same-origin fallback — used in dev mode where Vite's proxy forwards /ws to FastAPI.
 */
function getWsUrl(): string {
  const backendUrl = window.__CONDUCTOR_BACKEND_URL__;
  if (backendUrl) {
    const wsUrl = backendUrl.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
    return `${wsUrl}/ws`;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws`;
}

function ConnectionIndicator({ connected }: { connected: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span
        className={`rounded-full w-2 h-2 flex-shrink-0 ${connected ? "bg-green-500" : "bg-red-500"}`}
        aria-hidden="true"
      />
      <span className="text-gray-500">{connected ? "Connected" : "Disconnected"}</span>
    </span>
  );
}

function App() {
  const { conductorState, events, connected, sendIntervention } =
    useConductorSocket(getWsUrl());

  useSmartNotifications(events);

  return (
    <div className="min-h-screen bg-gray-50">
      <NotificationProvider />
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">Conductor Dashboard</h1>
          <ConnectionIndicator connected={connected} />
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 py-6">
        {conductorState === null ? (
          <div className="flex items-center justify-center py-16">
            <p className="text-gray-400">Connecting...</p>
          </div>
        ) : (
          <AgentGrid
            agents={conductorState.agents}
            tasks={conductorState.tasks}
            events={events}
            onIntervene={sendIntervention}
          />
        )}
      </main>
    </div>
  );
}

export default App;
