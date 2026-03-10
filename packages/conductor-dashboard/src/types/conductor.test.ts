/**
 * Tests for TypeScript types that mirror backend Pydantic models.
 * These tests verify that all types compile and can be instantiated correctly.
 */
import { describe, expect, it } from "vitest";
import type {
  AgentRecord,
  AgentStatus,
  ConductorState,
  DashboardState,
  DeltaEvent,
  Dependency,
  EventType,
  ExpansionLevel,
  InterventionCommand,
  ReviewStatus,
  Task,
  TaskStatus,
} from "./conductor";

describe("TypeScript types compile and can be used", () => {
  it("Task type has all required fields", () => {
    const task: Task = {
      id: "task-1",
      title: "Test Task",
      description: "A test task",
      status: "pending" as TaskStatus,
      assigned_agent: null,
      outputs: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      requires: [],
      produces: [],
      target_file: "",
      material_files: [],
      review_status: "pending" as ReviewStatus,
      revision_count: 0,
    };
    expect(task.id).toBe("task-1");
    expect(task.status).toBe("pending");
    expect(task.review_status).toBe("pending");
  });

  it("AgentRecord type has all required fields", () => {
    const agent: AgentRecord = {
      id: "agent-1",
      name: "TestAgent",
      role: "developer",
      current_task_id: null,
      status: "idle" as AgentStatus,
      registered_at: new Date().toISOString(),
      session_id: null,
      memory_file: null,
      started_at: null,
    };
    expect(agent.id).toBe("agent-1");
    expect(agent.status).toBe("idle");
  });

  it("ConductorState type has all required fields", () => {
    const state: ConductorState = {
      version: "1",
      tasks: [],
      agents: [],
      dependencies: [],
      updated_at: new Date().toISOString(),
    };
    expect(state.version).toBe("1");
    expect(state.tasks).toHaveLength(0);
  });

  it("DeltaEvent type has all required fields", () => {
    const event: DeltaEvent = {
      type: "task_assigned" as EventType,
      task_id: "task-1",
      agent_id: null,
      payload: {},
      is_smart_notification: false,
    };
    expect(event.type).toBe("task_assigned");
  });

  it("InterventionCommand type supports all action values", () => {
    const cancelCmd: InterventionCommand = {
      action: "cancel",
      agent_id: "agent-1",
    };
    const feedbackCmd: InterventionCommand = {
      action: "feedback",
      agent_id: "agent-1",
      message: "looks good",
    };
    const redirectCmd: InterventionCommand = {
      action: "redirect",
      agent_id: "agent-1",
      message: "new instructions",
    };
    expect(cancelCmd.action).toBe("cancel");
    expect(feedbackCmd.message).toBe("looks good");
    expect(redirectCmd.action).toBe("redirect");
  });

  it("ExpansionLevel type accepts all values", () => {
    const levels: ExpansionLevel[] = ["collapsed", "detail", "stream"];
    expect(levels).toHaveLength(3);
  });

  it("DashboardState type has correct shape", () => {
    const dashState: DashboardState = {
      conductorState: null,
      events: [],
      connected: false,
    };
    expect(dashState.connected).toBe(false);
    expect(dashState.conductorState).toBeNull();
  });

  it("Dependency type has correct shape", () => {
    const dep: Dependency = {
      task_id: "task-1",
      depends_on: "task-0",
    };
    expect(dep.task_id).toBe("task-1");
  });

  it("TaskStatus enum values are correct strings", () => {
    const statuses: TaskStatus[] = [
      "pending",
      "in_progress",
      "completed",
      "failed",
      "blocked",
    ];
    expect(statuses).toHaveLength(5);
  });

  it("ReviewStatus enum values are correct strings", () => {
    const statuses: ReviewStatus[] = [
      "pending",
      "approved",
      "needs_revision",
    ];
    expect(statuses).toHaveLength(3);
  });

  it("AgentStatus enum values are correct strings", () => {
    const statuses: AgentStatus[] = ["idle", "working", "waiting", "done"];
    expect(statuses).toHaveLength(4);
  });

  it("EventType values match backend StrEnum", () => {
    const events: EventType[] = [
      "task_assigned",
      "task_status_changed",
      "task_completed",
      "task_failed",
      "agent_registered",
      "agent_status_changed",
      "intervention_needed",
    ];
    expect(events).toHaveLength(7);
  });
});
