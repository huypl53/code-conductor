import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders 'working' status with green dot and text", () => {
    const { container } = render(<StatusBadge status="working" />);
    expect(screen.getByText("working")).toBeInTheDocument();
    const dot = container.querySelector(".bg-green-500");
    expect(dot).toBeInTheDocument();
  });

  it("renders 'idle' status with gray dot and text", () => {
    const { container } = render(<StatusBadge status="idle" />);
    expect(screen.getByText("idle")).toBeInTheDocument();
    const dot = container.querySelector(".bg-gray-400");
    expect(dot).toBeInTheDocument();
  });

  it("renders 'waiting' status with yellow dot and text", () => {
    const { container } = render(<StatusBadge status="waiting" />);
    expect(screen.getByText("waiting")).toBeInTheDocument();
    const dot = container.querySelector(".bg-yellow-500");
    expect(dot).toBeInTheDocument();
  });

  it("renders 'done' status with blue dot and text", () => {
    const { container } = render(<StatusBadge status="done" />);
    expect(screen.getByText("done")).toBeInTheDocument();
    const dot = container.querySelector(".bg-blue-500");
    expect(dot).toBeInTheDocument();
  });
});
