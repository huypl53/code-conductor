import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import type { AgentRecord, Task } from "../types/conductor";
import { AgentGrid } from "./AgentGrid";

const makeAgent = (id: string, name: string): AgentRecord => ({
  id,
  name,
  role: "developer",
  current_task_id: null,
  status: "idle",
  registered_at: "2024-01-01T00:00:00Z",
  session_id: null,
  memory_file: null,
  started_at: null,
});

const mockTasks: Task[] = [];

describe("AgentGrid", () => {
  it("renders one AgentCard per agent in the list", () => {
    const agents = [makeAgent("1", "Alpha"), makeAgent("2", "Beta"), makeAgent("3", "Gamma")];
    render(<AgentGrid agents={agents} tasks={mockTasks} events={[]} />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
  });

  it("renders empty state message when no agents", () => {
    render(<AgentGrid agents={[]} tasks={mockTasks} events={[]} />);
    expect(screen.getByText("No agents running")).toBeInTheDocument();
  });

  it("grid uses CSS grid layout (check className for grid)", () => {
    const agents = [makeAgent("1", "Alpha")];
    const { container } = render(<AgentGrid agents={agents} tasks={mockTasks} events={[]} />);
    const grid = container.querySelector(".grid");
    expect(grid).toBeInTheDocument();
  });
});
