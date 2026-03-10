import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import type { AgentRecord, Task, DeltaEvent } from "../types/conductor";
import { AgentCard } from "./AgentCard";

const mockAgent: AgentRecord = {
  id: "agent-1",
  name: "Agent Alpha",
  role: "developer",
  current_task_id: "task-1",
  status: "working",
  registered_at: "2024-01-01T00:00:00Z",
  session_id: null,
  memory_file: null,
  started_at: null,
};

const mockTasks: Task[] = [
  {
    id: "task-1",
    title: "Build the feature",
    description: "A feature",
    status: "in_progress",
    assigned_agent: "agent-1",
    outputs: {},
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    requires: [],
    produces: [],
    target_file: "feature.ts",
    material_files: ["dep.ts", "util.ts"],
    review_status: "pending",
    revision_count: 0,
  },
];

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
    task_id: "task-1",
    agent_id: "agent-1",
    payload: {},
    is_smart_notification: false,
  },
];

describe("AgentCard", () => {
  it("renders agent name and role in collapsed state", () => {
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);
    expect(screen.getByText("Agent Alpha")).toBeInTheDocument();
    expect(screen.getByText("developer")).toBeInTheDocument();
  });

  it("renders current task title when agent has assigned task", () => {
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);
    expect(screen.getByText("Build the feature")).toBeInTheDocument();
  });

  it("renders StatusBadge with agent's status", () => {
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);
    expect(screen.getByText("working")).toBeInTheDocument();
  });

  it("defaults to collapsed — no detail section visible", () => {
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);
    expect(screen.queryByText("Recent Actions")).not.toBeInTheDocument();
  });

  it("click expands to show 'detail' content area with Recent Actions", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={mockEvents} />);

    await user.click(screen.getByRole("button", { name: /agent alpha/i }));

    expect(screen.getByText("Recent Actions")).toBeInTheDocument();
  });

  it("detail level shows files modified (target_file and material_files)", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);

    await user.click(screen.getByRole("button", { name: /agent alpha/i }));

    expect(screen.getByText("feature.ts")).toBeInTheDocument();
    expect(screen.getByText("dep.ts")).toBeInTheDocument();
    expect(screen.getByText("util.ts")).toBeInTheDocument();
  });

  it("detail level shows InterventionPanel", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} onIntervene={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /agent alpha/i }));

    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /feedback/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /redirect/i })).toBeInTheDocument();
  });

  it("detail level shows recent events for the agent", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={mockEvents} />);

    await user.click(screen.getByRole("button", { name: /agent alpha/i }));

    expect(screen.getByText("task_assigned")).toBeInTheDocument();
    expect(screen.getByText("task_status_changed")).toBeInTheDocument();
  });

  it("does NOT show live stream terminal in 'detail' level", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);

    await user.click(screen.getByRole("button", { name: /agent alpha/i }));

    // LiveStream terminal has bg-gray-900 class, absent in detail-only view with no events
    expect(screen.queryByText("No events yet")).not.toBeInTheDocument();
    // The "Show live stream" button should be visible but stream not shown
    expect(screen.getByRole("button", { name: /show live stream/i })).toBeInTheDocument();
  });

  it("stream level shows LiveStream component", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={mockEvents} />);

    // Expand to detail
    await user.click(screen.getByRole("button", { name: /agent alpha/i }));
    // Expand to stream
    await user.click(screen.getByRole("button", { name: /show live stream/i }));

    // LiveStream renders — "Hide live stream" button now visible
    expect(screen.getByRole("button", { name: /hide live stream/i })).toBeInTheDocument();
    // And the events are shown in the stream (event type visible)
    const taskAssignedElements = screen.getAllByText("task_assigned");
    // Should appear in both Recent Actions list and LiveStream
    expect(taskAssignedElements.length).toBeGreaterThanOrEqual(1);
  });

  it("stream level still shows InterventionPanel", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} onIntervene={vi.fn()} />);

    // Expand to detail
    await user.click(screen.getByRole("button", { name: /agent alpha/i }));
    // Expand to stream
    await user.click(screen.getByRole("button", { name: /show live stream/i }));

    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
  });

  it("renders 'No task assigned' when current_task_id is null", () => {
    const agentWithoutTask: AgentRecord = { ...mockAgent, current_task_id: null };
    render(<AgentCard agent={agentWithoutTask} tasks={mockTasks} events={[]} />);
    expect(screen.getByText("No task assigned")).toBeInTheDocument();
  });
});
