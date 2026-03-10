/**
 * Tests for useConductorSocket hook.
 *
 * Uses a MockWebSocket class to simulate WebSocket behavior in jsdom.
 */
import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import type { ConductorState, DeltaEvent } from "../types/conductor";
import { useConductorSocket } from "./useConductorSocket";

// ---------------------------------------------------------------------------
// MockWebSocket
// ---------------------------------------------------------------------------

class MockWebSocket {
  static lastInstance: MockWebSocket | null = null;

  url: string;
  readyState: number = 0; // CONNECTING
  sentMessages: string[] = [];
  closeCallCount = 0;

  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.lastInstance = this;
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.closeCallCount++;
    this.readyState = MockWebSocket.CLOSED;
  }

  // Test helpers to trigger events
  triggerOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event("open"));
  }

  triggerMessage(data: unknown) {
    const event = new MessageEvent("message", {
      data: JSON.stringify(data),
    });
    this.onmessage?.(event);
  }

  triggerClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.(new CloseEvent("close"));
  }
}

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const mockState: ConductorState = {
  version: "1",
  tasks: [
    {
      id: "task-1",
      title: "Write tests",
      description: "Test description",
      status: "in_progress",
      assigned_agent: "agent-1",
      outputs: {},
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
      requires: [],
      produces: [],
      target_file: "test.ts",
      material_files: [],
      review_status: "pending",
      revision_count: 0,
    },
  ],
  agents: [
    {
      id: "agent-1",
      name: "Agent One",
      role: "developer",
      current_task_id: "task-1",
      status: "working",
      registered_at: "2024-01-01T00:00:00Z",
      session_id: null,
      memory_file: null,
      started_at: null,
    },
  ],
  dependencies: [],
  updated_at: "2024-01-01T00:00:00Z",
};

const makeDelta = (overrides: Partial<DeltaEvent>): DeltaEvent => ({
  type: "agent_status_changed",
  task_id: null,
  agent_id: null,
  payload: {},
  is_smart_notification: false,
  ...overrides,
});

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  MockWebSocket.lastInstance = null;
  vi.useFakeTimers();
  // @ts-expect-error - replacing global WebSocket with mock
  globalThis.WebSocket = MockWebSocket;
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useConductorSocket", () => {
  it("initializes with conductorState=null, events=[], connected=false", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );
    expect(result.current.conductorState).toBeNull();
    expect(result.current.events).toEqual([]);
    expect(result.current.connected).toBe(false);
  });

  it("sets connected=true on WebSocket open", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
    });

    expect(result.current.connected).toBe(true);
  });

  it("sets conductorState on receiving a snapshot message", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
      MockWebSocket.lastInstance?.triggerMessage(mockState);
    });

    expect(result.current.conductorState).toEqual(mockState);
  });

  it("appends delta event to events array", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );
    const delta = makeDelta({ type: "agent_status_changed", agent_id: "agent-1", payload: { status: "idle" } });

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
      MockWebSocket.lastInstance?.triggerMessage(mockState);
      MockWebSocket.lastInstance?.triggerMessage(delta);
    });

    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0]).toEqual(delta);
  });

  it("applies agent_status_changed delta to conductorState", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );
    const delta = makeDelta({
      type: "agent_status_changed",
      agent_id: "agent-1",
      payload: { status: "idle" },
    });

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
      MockWebSocket.lastInstance?.triggerMessage(mockState);
      MockWebSocket.lastInstance?.triggerMessage(delta);
    });

    expect(result.current.conductorState?.agents[0].status).toBe("idle");
  });

  it("applies task_status_changed delta to conductorState", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );
    const delta = makeDelta({
      type: "task_status_changed",
      task_id: "task-1",
      payload: { status: "completed" },
    });

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
      MockWebSocket.lastInstance?.triggerMessage(mockState);
      MockWebSocket.lastInstance?.triggerMessage(delta);
    });

    expect(result.current.conductorState?.tasks[0].status).toBe("completed");
  });

  it("applies agent_registered delta — adds new agent", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );
    const newAgent = {
      id: "agent-2",
      name: "Agent Two",
      role: "reviewer",
      current_task_id: null,
      status: "idle",
      registered_at: "2024-01-01T00:00:00Z",
      session_id: null,
      memory_file: null,
      started_at: null,
    };
    const delta = makeDelta({
      type: "agent_registered",
      agent_id: "agent-2",
      payload: newAgent,
    });

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
      MockWebSocket.lastInstance?.triggerMessage(mockState);
      MockWebSocket.lastInstance?.triggerMessage(delta);
    });

    expect(result.current.conductorState?.agents).toHaveLength(2);
    expect(result.current.conductorState?.agents[1].id).toBe("agent-2");
  });

  it("applies task_assigned delta — updates assigned_agent", () => {
    const stateWithUnassigned: ConductorState = {
      ...mockState,
      tasks: [{ ...mockState.tasks[0], assigned_agent: null }],
    };
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );
    const delta = makeDelta({
      type: "task_assigned",
      task_id: "task-1",
      payload: { agent_id: "agent-1" },
    });

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
      MockWebSocket.lastInstance?.triggerMessage(stateWithUnassigned);
      MockWebSocket.lastInstance?.triggerMessage(delta);
    });

    expect(result.current.conductorState?.tasks[0].assigned_agent).toBe("agent-1");
  });

  it("caps events array at 500 entries (oldest evicted)", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
      MockWebSocket.lastInstance?.triggerMessage(mockState);
      // Send 510 events
      for (let i = 0; i < 510; i++) {
        MockWebSocket.lastInstance?.triggerMessage(
          makeDelta({ type: "agent_status_changed", payload: { index: i } }),
        );
      }
    });

    expect(result.current.events).toHaveLength(500);
    // The first event should be index 10 (oldest 10 evicted)
    expect((result.current.events[0].payload as { index: number }).index).toBe(10);
  });

  it("sets connected=false on WebSocket close", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
    });
    expect(result.current.connected).toBe(true);

    act(() => {
      MockWebSocket.lastInstance?.triggerClose();
    });

    expect(result.current.connected).toBe(false);
  });

  it("sendIntervention sends JSON string over WebSocket", () => {
    const { result } = renderHook(() =>
      useConductorSocket("ws://localhost/ws"),
    );

    act(() => {
      MockWebSocket.lastInstance?.triggerOpen();
    });

    act(() => {
      result.current.sendIntervention({
        action: "cancel",
        agent_id: "agent-1",
        message: "Stop",
      });
    });

    expect(MockWebSocket.lastInstance?.sentMessages).toHaveLength(1);
    expect(JSON.parse(MockWebSocket.lastInstance!.sentMessages[0])).toEqual({
      action: "cancel",
      agent_id: "agent-1",
      message: "Stop",
    });
  });

  it("attempts reconnection with exponential backoff on close", () => {
    renderHook(() => useConductorSocket("ws://localhost/ws"));
    const firstInstance = MockWebSocket.lastInstance!;

    act(() => {
      firstInstance.triggerOpen();
      firstInstance.triggerClose();
    });

    // After close, reconnect should be scheduled at 1s
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    // A new WebSocket should have been created
    expect(MockWebSocket.lastInstance).not.toBe(firstInstance);
  });
});
