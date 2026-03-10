/**
 * WebSocket hook for real-time conductor state management.
 *
 * Connects to the dashboard WebSocket endpoint, receives snapshots and delta
 * events, and maintains local state via useReducer with immutable updates.
 * Reconnects automatically with exponential backoff on disconnect.
 */
import { useReducer, useEffect, useRef, useCallback } from "react";
import type {
  ConductorState,
  DeltaEvent,
  DashboardState,
  InterventionCommand,
  AgentRecord,
} from "../types/conductor";
import { parseMessage } from "../lib/messages";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_EVENTS = 500;
const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30_000;

// ---------------------------------------------------------------------------
// Delta application
// ---------------------------------------------------------------------------

/**
 * Apply a single delta event to the conductor state immutably.
 * Returns null if state is null (cannot apply without a snapshot).
 */
export function applyDelta(
  state: ConductorState | null,
  event: DeltaEvent,
): ConductorState | null {
  if (state === null) return null;

  switch (event.type) {
    case "agent_status_changed": {
      const { agent_id } = event;
      const status = event.payload.status as AgentRecord["status"];
      return {
        ...state,
        agents: state.agents.map((a) =>
          a.id === agent_id ? { ...a, status } : a,
        ),
      };
    }

    case "agent_registered": {
      const newAgent = event.payload as unknown as AgentRecord;
      return {
        ...state,
        agents: [...state.agents, newAgent],
      };
    }

    case "task_status_changed": {
      const { task_id } = event;
      const status = event.payload.status as string;
      return {
        ...state,
        tasks: state.tasks.map((t) =>
          // biome-ignore lint/suspicious/noExplicitAny: status comes from backend enum
          t.id === task_id ? { ...t, status: status as any } : t,
        ),
      };
    }

    case "task_completed": {
      return {
        ...state,
        tasks: state.tasks.map((t) =>
          t.id === event.task_id ? { ...t, status: "completed" } : t,
        ),
      };
    }

    case "task_failed": {
      return {
        ...state,
        tasks: state.tasks.map((t) =>
          t.id === event.task_id ? { ...t, status: "failed" } : t,
        ),
      };
    }

    case "task_assigned": {
      const agent_id = event.payload.agent_id as string;
      return {
        ...state,
        tasks: state.tasks.map((t) =>
          t.id === event.task_id ? { ...t, assigned_agent: agent_id } : t,
        ),
      };
    }

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

type Action =
  | { type: "connected" }
  | { type: "disconnected" }
  | { type: "snapshot"; state: ConductorState }
  | { type: "delta"; event: DeltaEvent };

function reducer(state: DashboardState, action: Action): DashboardState {
  switch (action.type) {
    case "connected":
      return { ...state, connected: true };

    case "disconnected":
      return { ...state, connected: false };

    case "snapshot":
      return { ...state, conductorState: action.state };

    case "delta": {
      const events =
        state.events.length >= MAX_EVENTS
          ? [...state.events.slice(state.events.length - MAX_EVENTS + 1), action.event]
          : [...state.events, action.event];
      return {
        ...state,
        events,
        conductorState: applyDelta(state.conductorState, action.event),
      };
    }

    default:
      return state;
  }
}

const initialState: DashboardState = {
  conductorState: null,
  events: [],
  connected: false,
};

// ---------------------------------------------------------------------------
// Hook return type
// ---------------------------------------------------------------------------

export interface UseConductorSocketResult extends DashboardState {
  sendIntervention: (command: InterventionCommand) => void;
}

// ---------------------------------------------------------------------------
// useConductorSocket
// ---------------------------------------------------------------------------

export function useConductorSocket(url: string): UseConductorSocketResult {
  const [state, dispatch] = useReducer(reducer, initialState);

  const wsRef = useRef<WebSocket | null>(null);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const unmountedRef = useRef(false);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) return;
      retryCountRef.current = 0;
      dispatch({ type: "connected" });
    };

    ws.onmessage = (event: MessageEvent) => {
      if (unmountedRef.current) return;
      const parsed = parseMessage(event.data as string);
      if (parsed.kind === "snapshot") {
        dispatch({ type: "snapshot", state: parsed.state });
      } else if (parsed.kind === "delta") {
        dispatch({ type: "delta", event: parsed.event });
      }
    };

    ws.onclose = () => {
      if (unmountedRef.current) return;
      dispatch({ type: "disconnected" });

      // Exponential backoff reconnection
      const delay = Math.min(
        BACKOFF_BASE_MS * 2 ** retryCountRef.current,
        BACKOFF_MAX_MS,
      );
      retryCountRef.current += 1;

      retryTimeoutRef.current = setTimeout(() => {
        if (!unmountedRef.current) {
          connect();
        }
      }, delay);
    };
  }, [url]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();

    return () => {
      unmountedRef.current = true;
      if (retryTimeoutRef.current !== null) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
      if (wsRef.current !== null) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const sendIntervention = useCallback(
    (command: InterventionCommand) => {
      const ws = wsRef.current;
      if (ws !== null && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(command));
      }
    },
    [],
  );

  return {
    conductorState: state.conductorState,
    events: state.events,
    connected: state.connected,
    sendIntervention,
  };
}
