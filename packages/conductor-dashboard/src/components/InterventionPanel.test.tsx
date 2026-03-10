import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import type { InterventionCommand } from "../types/conductor";
import { InterventionPanel } from "./InterventionPanel";

describe("InterventionPanel", () => {
  const agentId = "agent-1";

  it("renders Cancel, Feedback, and Redirect buttons", () => {
    render(<InterventionPanel agentId={agentId} onIntervene={vi.fn()} />);
    expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /feedback/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /redirect/i })).toBeInTheDocument();
  });

  it("clicking Cancel calls onIntervene with cancel action", async () => {
    const user = userEvent.setup();
    const onIntervene = vi.fn();
    render(<InterventionPanel agentId={agentId} onIntervene={onIntervene} />);

    await user.click(screen.getByRole("button", { name: /cancel/i }));

    expect(onIntervene).toHaveBeenCalledWith<[InterventionCommand]>({
      action: "cancel",
      agent_id: agentId,
    });
  });

  it("clicking Feedback opens a text input", async () => {
    const user = userEvent.setup();
    render(<InterventionPanel agentId={agentId} onIntervene={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /feedback/i }));

    expect(screen.getByPlaceholderText("Send feedback to agent...")).toBeInTheDocument();
  });

  it("submitting Feedback calls onIntervene with feedback action and message", async () => {
    const user = userEvent.setup();
    const onIntervene = vi.fn();
    render(<InterventionPanel agentId={agentId} onIntervene={onIntervene} />);

    await user.click(screen.getByRole("button", { name: /feedback/i }));
    await user.type(screen.getByPlaceholderText("Send feedback to agent..."), "Good job");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(onIntervene).toHaveBeenCalledWith<[InterventionCommand]>({
      action: "feedback",
      agent_id: agentId,
      message: "Good job",
    });
  });

  it("Feedback input clears after submission", async () => {
    const user = userEvent.setup();
    render(<InterventionPanel agentId={agentId} onIntervene={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /feedback/i }));
    const input = screen.getByPlaceholderText("Send feedback to agent...");
    await user.type(input, "Some feedback");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // Input should be gone or cleared
    expect(screen.queryByPlaceholderText("Send feedback to agent...")).not.toBeInTheDocument();
  });

  it("clicking Redirect opens a text input", async () => {
    const user = userEvent.setup();
    render(<InterventionPanel agentId={agentId} onIntervene={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /redirect/i }));

    expect(screen.getByPlaceholderText("New instructions for agent...")).toBeInTheDocument();
  });

  it("submitting Redirect calls onIntervene with redirect action and message", async () => {
    const user = userEvent.setup();
    const onIntervene = vi.fn();
    render(<InterventionPanel agentId={agentId} onIntervene={onIntervene} />);

    await user.click(screen.getByRole("button", { name: /redirect/i }));
    await user.type(screen.getByPlaceholderText("New instructions for agent..."), "New task");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(onIntervene).toHaveBeenCalledWith<[InterventionCommand]>({
      action: "redirect",
      agent_id: agentId,
      message: "New task",
    });
  });

  it("Redirect input clears after submission", async () => {
    const user = userEvent.setup();
    render(<InterventionPanel agentId={agentId} onIntervene={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /redirect/i }));
    const input = screen.getByPlaceholderText("New instructions for agent...");
    await user.type(input, "Some instructions");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(screen.queryByPlaceholderText("New instructions for agent...")).not.toBeInTheDocument();
  });

  it("Feedback submit button is disabled when input is empty", async () => {
    const user = userEvent.setup();
    render(<InterventionPanel agentId={agentId} onIntervene={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /feedback/i }));

    const sendButton = screen.getByRole("button", { name: /send/i });
    expect(sendButton).toBeDisabled();
  });

  it("Redirect submit button is disabled when input is empty", async () => {
    const user = userEvent.setup();
    render(<InterventionPanel agentId={agentId} onIntervene={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: /redirect/i }));

    const sendButton = screen.getByRole("button", { name: /send/i });
    expect(sendButton).toBeDisabled();
  });
});
