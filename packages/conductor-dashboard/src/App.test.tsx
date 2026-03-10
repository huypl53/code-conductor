import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import App from "./App";

// Mock useConductorSocket to avoid real WebSocket connections
vi.mock("./hooks/useConductorSocket", () => ({
  useConductorSocket: vi.fn(() => ({
    conductorState: null,
    events: [],
    connected: false,
    sendIntervention: vi.fn(),
  })),
}));

// Mock sonner
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
  Toaster: () => <div data-testid="sonner-toaster" />,
}));

describe("App integration", () => {
  it("renders NotificationProvider (Toaster component present in DOM)", () => {
    render(<App />);
    expect(screen.getByTestId("sonner-toaster")).toBeInTheDocument();
  });

  it("renders the Conductor Dashboard header", () => {
    render(<App />);
    expect(screen.getByText("Conductor Dashboard")).toBeInTheDocument();
  });

  it("shows connecting state when conductorState is null", () => {
    render(<App />);
    expect(screen.getByText("Connecting...")).toBeInTheDocument();
  });
});
