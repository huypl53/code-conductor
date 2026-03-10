/**
 * Tests for WebSocket message parsing and intervention command serialization.
 */
import { describe, expect, it } from "vitest";
import { parseMessage, serializeIntervention } from "./messages";

describe("parseMessage", () => {
  it("returns snapshot kind when message has version field", () => {
    const snapshot = {
      version: "1",
      tasks: [],
      agents: [],
      dependencies: [],
      updated_at: new Date().toISOString(),
    };
    const result = parseMessage(JSON.stringify(snapshot));
    expect(result.kind).toBe("snapshot");
    if (result.kind === "snapshot") {
      expect(result.state.version).toBe("1");
      expect(result.state.tasks).toEqual([]);
    }
  });

  it("returns delta kind when message has type field", () => {
    const delta = {
      type: "task_assigned",
      task_id: "task-1",
      agent_id: null,
      payload: {},
      is_smart_notification: false,
    };
    const result = parseMessage(JSON.stringify(delta));
    expect(result.kind).toBe("delta");
    if (result.kind === "delta") {
      expect(result.event.type).toBe("task_assigned");
      expect(result.event.task_id).toBe("task-1");
    }
  });

  it("returns error kind for invalid JSON", () => {
    const result = parseMessage("{not valid json}");
    expect(result.kind).toBe("error");
  });

  it("returns error kind for empty string", () => {
    const result = parseMessage("");
    expect(result.kind).toBe("error");
  });

  it("returns error kind for JSON without version or type field", () => {
    const result = parseMessage(JSON.stringify({ foo: "bar" }));
    expect(result.kind).toBe("error");
  });

  it("snapshot with tasks and agents parses correctly", () => {
    const snapshot = {
      version: "1",
      tasks: [
        {
          id: "t1",
          title: "Task 1",
          description: "desc",
          status: "pending",
          assigned_agent: null,
          outputs: {},
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
          requires: [],
          produces: [],
          target_file: "",
          material_files: [],
          review_status: "pending",
          revision_count: 0,
        },
      ],
      agents: [],
      dependencies: [],
      updated_at: "2024-01-01T00:00:00Z",
    };
    const result = parseMessage(JSON.stringify(snapshot));
    expect(result.kind).toBe("snapshot");
    if (result.kind === "snapshot") {
      expect(result.state.tasks).toHaveLength(1);
      expect(result.state.tasks[0]?.id).toBe("t1");
    }
  });
});

describe("serializeIntervention", () => {
  it("serializes cancel command to valid JSON string", () => {
    const json = serializeIntervention({ action: "cancel", agent_id: "a1" });
    expect(typeof json).toBe("string");
    const parsed = JSON.parse(json);
    expect(parsed.action).toBe("cancel");
    expect(parsed.agent_id).toBe("a1");
  });

  it("serializes feedback command with message", () => {
    const json = serializeIntervention({
      action: "feedback",
      agent_id: "a1",
      message: "looks good",
    });
    const parsed = JSON.parse(json);
    expect(parsed.action).toBe("feedback");
    expect(parsed.message).toBe("looks good");
  });

  it("serializes redirect command with message", () => {
    const json = serializeIntervention({
      action: "redirect",
      agent_id: "a1",
      message: "new instructions here",
    });
    const parsed = JSON.parse(json);
    expect(parsed.action).toBe("redirect");
    expect(parsed.agent_id).toBe("a1");
    expect(parsed.message).toBe("new instructions here");
  });

  it("produces valid JSON for round-trip", () => {
    const cmd = { action: "cancel" as const, agent_id: "agent-xyz" };
    const json = serializeIntervention(cmd);
    const parsed = JSON.parse(json);
    expect(parsed).toEqual(cmd);
  });
});
