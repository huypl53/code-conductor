import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import type { DeltaEvent } from "../types/conductor";
import { LiveStream } from "./LiveStream";

const mockEvents: DeltaEvent[] = [
  {
    type: "task_assigned",
    task_id: "task-1",
    agent_id: "agent-1",
    payload: {},
    is_smart_notification: false,
  },
  {
    type: "task_status_changed",
    task_id: "task-2",
    agent_id: "agent-2",
    payload: {},
    is_smart_notification: false,
  },
  {
    type: "task_completed",
    task_id: "task-1",
    agent_id: "agent-1",
    payload: {},
    is_smart_notification: true,
  },
];

describe("LiveStream", () => {
  it("renders events filtered to the given agentId", () => {
    render(<LiveStream agentId="agent-1" events={mockEvents} />);
    // Should show 2 events for agent-1
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(2);
  });

  it("does not render events for other agents", () => {
    render(<LiveStream agentId="agent-1" events={mockEvents} />);
    // agent-2's event should not appear
    expect(screen.queryByText(/agent-2/)).not.toBeInTheDocument();
  });

  it("displays event type for each matching event", () => {
    render(<LiveStream agentId="agent-1" events={mockEvents} />);
    expect(screen.getByText("task_assigned")).toBeInTheDocument();
    expect(screen.getByText("task_completed")).toBeInTheDocument();
  });

  it("displays task_id for each matching event", () => {
    render(<LiveStream agentId="agent-1" events={mockEvents} />);
    const taskIds = screen.getAllByText("task-1");
    expect(taskIds.length).toBeGreaterThanOrEqual(1);
  });

  it("renders empty state when no events match agentId", () => {
    render(<LiveStream agentId="agent-99" events={mockEvents} />);
    expect(screen.getByText("No events yet")).toBeInTheDocument();
  });
});
