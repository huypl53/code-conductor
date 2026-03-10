import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import type { AgentRecord, Task } from "../types/conductor";
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
    material_files: [],
    review_status: "pending",
    revision_count: 0,
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
    expect(screen.queryByText("Recent actions")).not.toBeInTheDocument();
  });

  it("click expands to show 'detail' content area", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);

    await user.click(screen.getByRole("button"));

    expect(screen.getByText("Recent actions")).toBeInTheDocument();
  });

  it("does NOT show live stream section in 'detail' level", async () => {
    const user = userEvent.setup();
    render(<AgentCard agent={mockAgent} tasks={mockTasks} events={[]} />);

    await user.click(screen.getByRole("button"));

    expect(screen.queryByText("Live stream")).not.toBeInTheDocument();
  });

  it("renders 'No task assigned' when current_task_id is null", () => {
    const agentWithoutTask: AgentRecord = { ...mockAgent, current_task_id: null };
    render(<AgentCard agent={agentWithoutTask} tasks={mockTasks} events={[]} />);
    expect(screen.getByText("No task assigned")).toBeInTheDocument();
  });
});
