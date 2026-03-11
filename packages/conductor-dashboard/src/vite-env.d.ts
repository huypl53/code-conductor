/// <reference types="vite/client" />

interface Window {
  /**
   * Optional backend URL injected at runtime by the conductor-dashboard bin script.
   * When set, the dashboard connects its WebSocket to this URL instead of same-origin.
   * Example: "http://127.0.0.1:8000"
   */
  __CONDUCTOR_BACKEND_URL__?: string;
}
