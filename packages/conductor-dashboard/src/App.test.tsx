import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import App from "./App";

// Capture the URL passed to useConductorSocket for URL-derivation tests
let capturedWsUrl: string | undefined;

// Mock useConductorSocket to avoid real WebSocket connections
vi.mock("./hooks/useConductorSocket", () => ({
  useConductorSocket: vi.fn((url: string) => {
    capturedWsUrl = url;
    return {
      conductorState: null,
      events: [],
      connected: false,
      sendIntervention: vi.fn(),
    };
  }),
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

describe("App WebSocket URL derivation", () => {
  beforeEach(() => {
    capturedWsUrl = undefined;
  });

  afterEach(() => {
    // Clean up any injected global between tests
    delete window.__CONDUCTOR_BACKEND_URL__;
  });

  it("uses ws:// same-origin fallback when __CONDUCTOR_BACKEND_URL__ is not set", () => {
    delete window.__CONDUCTOR_BACKEND_URL__;
    // jsdom sets window.location.host to "localhost" by default
    render(<App />);
    expect(capturedWsUrl).toMatch(/^ws:\/\/localhost/);
    expect(capturedWsUrl).toMatch(/\/ws$/);
  });

  it("derives ws:// from http:// __CONDUCTOR_BACKEND_URL__", () => {
    window.__CONDUCTOR_BACKEND_URL__ = "http://127.0.0.1:8000";
    render(<App />);
    expect(capturedWsUrl).toBe("ws://127.0.0.1:8000/ws");
  });

  it("derives wss:// from https:// __CONDUCTOR_BACKEND_URL__", () => {
    window.__CONDUCTOR_BACKEND_URL__ = "https://api.example.com";
    render(<App />);
    expect(capturedWsUrl).toBe("wss://api.example.com/ws");
  });
});
