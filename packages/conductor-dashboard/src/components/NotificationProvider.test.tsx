import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { DeltaEvent } from "../types/conductor";
import { useSmartNotifications } from "./NotificationProvider";

// Mock sonner toast
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
  Toaster: () => null,
}));

import { toast } from "sonner";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockToast = toast as any as {
  success: ReturnType<typeof vi.fn>;
  error: ReturnType<typeof vi.fn>;
  warning: ReturnType<typeof vi.fn>;
};

describe("useSmartNotifications", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not fire toast for non-smart events", () => {
    const events: DeltaEvent[] = [
      {
        type: "task_status_changed",
        task_id: "task-1",
        agent_id: "agent-1",
        payload: {},
        is_smart_notification: false,
      },
    ];

    renderHook(() => useSmartNotifications(events));

    expect(mockToast.success).not.toHaveBeenCalled();
    expect(mockToast.error).not.toHaveBeenCalled();
    expect(mockToast.warning).not.toHaveBeenCalled();
  });

  it("fires toast.success for task_completed smart event", () => {
    const events: DeltaEvent[] = [
      {
        type: "task_completed",
        task_id: "task-1",
        agent_id: "agent-1",
        payload: {},
        is_smart_notification: true,
      },
    ];

    renderHook(() => useSmartNotifications(events));

    expect(mockToast.success).toHaveBeenCalledWith("Task completed: task-1");
  });

  it("fires toast.error for task_failed smart event", () => {
    const events: DeltaEvent[] = [
      {
        type: "task_failed",
        task_id: "task-2",
        agent_id: "agent-1",
        payload: {},
        is_smart_notification: true,
      },
    ];

    renderHook(() => useSmartNotifications(events));

    expect(mockToast.error).toHaveBeenCalledWith("Task failed: task-2");
  });

  it("fires toast.warning with duration=Infinity for intervention_needed smart event", () => {
    const events: DeltaEvent[] = [
      {
        type: "intervention_needed",
        task_id: null,
        agent_id: "agent-3",
        payload: {},
        is_smart_notification: true,
      },
    ];

    renderHook(() => useSmartNotifications(events));

    expect(mockToast.warning).toHaveBeenCalledWith(
      "Agent agent-3 needs intervention",
      { duration: Infinity }
    );
  });

  it("does not re-fire toasts for already-processed events", () => {
    const events: DeltaEvent[] = [
      {
        type: "task_completed",
        task_id: "task-1",
        agent_id: "agent-1",
        payload: {},
        is_smart_notification: true,
      },
    ];

    const { rerender } = renderHook(
      ({ evts }) => useSmartNotifications(evts),
      { initialProps: { evts: events } }
    );

    expect(mockToast.success).toHaveBeenCalledTimes(1);

    // Re-render with same events — should NOT fire again
    rerender({ evts: events });

    expect(mockToast.success).toHaveBeenCalledTimes(1);
  });

  it("fires toast for new events added after first render", () => {
    const firstEvent: DeltaEvent = {
      type: "task_completed",
      task_id: "task-1",
      agent_id: "agent-1",
      payload: {},
      is_smart_notification: true,
    };
    const secondEvent: DeltaEvent = {
      type: "task_failed",
      task_id: "task-2",
      agent_id: "agent-1",
      payload: {},
      is_smart_notification: true,
    };

    const { rerender } = renderHook(
      ({ evts }) => useSmartNotifications(evts),
      { initialProps: { evts: [firstEvent] } }
    );

    expect(mockToast.success).toHaveBeenCalledTimes(1);

    rerender({ evts: [firstEvent, secondEvent] });

    expect(mockToast.error).toHaveBeenCalledTimes(1);
    // success still only once (not re-fired)
    expect(mockToast.success).toHaveBeenCalledTimes(1);
  });
});
