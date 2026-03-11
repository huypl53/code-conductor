---
phase: 17
plan: 1
subsystem: conductor-dashboard
tags: [frontend, websocket, configuration, packaging, production]
dependency_graph:
  requires: []
  provides: [runtime-backend-url-config]
  affects: [conductor-dashboard-npm-package]
tech_stack:
  added: []
  patterns: [runtime-global-injection, url-derivation, sirv-middleware]
key_files:
  created: []
  modified:
    - packages/conductor-dashboard/src/vite-env.d.ts
    - packages/conductor-dashboard/src/App.tsx
    - packages/conductor-dashboard/src/App.test.tsx
    - packages/conductor-dashboard/bin/conductor-dashboard.js
    - packages/conductor-dashboard/README.md
decisions:
  - "getWsUrl() called on each render instead of module-level constant — allows tests to set window.__CONDUCTOR_BACKEND_URL__ between renders without module re-import"
  - "JSON.stringify() used in script tag injection for safe URL encoding — handles special characters and quotes in URL"
  - "Inject before </head> so global is available before app bundle executes"
metrics:
  duration_seconds: 126
  completed_date: "2026-03-11"
  tasks_completed: 3
  files_modified: 5
requirements_satisfied: [PKG-02]
---

# Phase 17 Plan 01: Add Runtime Backend URL Configuration for Production WebSocket Summary

**One-liner:** Runtime `window.__CONDUCTOR_BACKEND_URL__` injection via bin script `--backend-url` flag connects the dashboard WebSocket to the FastAPI backend port in production.

## What Was Built

The conductor-dashboard npm package now supports production deployment where the static file server (sirv) and the FastAPI WebSocket backend run on different ports.

### Runtime URL derivation (App.tsx)

The `WS_URL` module-level constant was replaced with a `getWsUrl()` function called on each render. It checks `window.__CONDUCTOR_BACKEND_URL__` first, derives `ws://`/`wss://` from `http://`/`https://` and appends `/ws`, then falls back to same-origin for development.

### TypeScript declaration (vite-env.d.ts)

Added `Window.__CONDUCTOR_BACKEND_URL__?: string` declaration so TypeScript resolves the property without `any` casts.

### Bin script HTML injection (conductor-dashboard.js)

The bin script now parses `--backend-url <url>` from process.argv. When provided, it intercepts requests to `/` and `/index.html`, reads `dist/index.html`, injects `<script>window.__CONDUCTOR_BACKEND_URL__ = "URL";</script>` before `</head>`, and serves the modified response. All other requests still delegate to sirv. Startup output prints the backend URL when configured. A `--help` flag is also supported.

### README documentation

Added "Production Deployment" section covering the two-server architecture, `--backend-url` flag usage, example commands for starting both servers, and a note that dev mode requires no configuration.

## Test Results

All 84 tests pass (`pnpm test`), including 3 new tests in `App.test.tsx`:
- `uses ws:// same-origin fallback when __CONDUCTOR_BACKEND_URL__ is not set`
- `derives ws:// from http:// __CONDUCTOR_BACKEND_URL__`
- `derives wss:// from https:// __CONDUCTOR_BACKEND_URL__`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Design] getWsUrl() called per-render instead of module-level constant**
- **Found during:** Task 1, when writing tests
- **Issue:** A module-level `const WS_URL = getWsUrl()` is evaluated once at module import time. Setting `window.__CONDUCTOR_BACKEND_URL__` in individual tests would not affect the captured value — all tests would share the value computed on first import.
- **Fix:** Changed `const WS_URL = getWsUrl()` to `useConductorSocket(getWsUrl())` — the function is called on each render, so each test render sees the current value of the global.
- **Files modified:** `packages/conductor-dashboard/src/App.tsx`
- **Commit:** bba52cb

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 17-01-01 | bba52cb | feat(17-01): add runtime backend URL support to App.tsx and TypeScript declarations |
| 17-01-02 | d563a83 | feat(17-01): add --backend-url flag to bin script with HTML injection |
| 17-01-03 | 3ab7048 | docs(17-01): add production deployment section to conductor-dashboard README |

## Self-Check: PASSED

Files verified:
- packages/conductor-dashboard/src/vite-env.d.ts — FOUND, contains Window.__CONDUCTOR_BACKEND_URL__
- packages/conductor-dashboard/src/App.tsx — FOUND, contains getWsUrl()
- packages/conductor-dashboard/src/App.test.tsx — FOUND, 6 tests including URL derivation tests
- packages/conductor-dashboard/bin/conductor-dashboard.js — FOUND, contains --backend-url parsing and injection
- packages/conductor-dashboard/README.md — FOUND, contains Production Deployment section

Commits verified: bba52cb, d563a83, 3ab7048 — all present in git log.
