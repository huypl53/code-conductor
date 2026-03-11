---
status: complete
phase: 17-fix-production-ws-url
source: 17-01-SUMMARY.md
started: 2026-03-11T11:07:00Z
updated: 2026-03-11T11:08:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Same-origin fallback when no backend URL configured
expected: Without window.__CONDUCTOR_BACKEND_URL__, getWsUrl() returns ws://{window.location.host}/ws (same-origin)
result: pass

### 2. HTTP backend URL derives ws:// WebSocket URL
expected: Setting window.__CONDUCTOR_BACKEND_URL__ = "http://127.0.0.1:8000" produces ws://127.0.0.1:8000/ws
result: pass

### 3. HTTPS backend URL derives wss:// WebSocket URL
expected: Setting window.__CONDUCTOR_BACKEND_URL__ = "https://example.com" produces wss://example.com/ws
result: pass

### 4. Bin script --backend-url flag injects global
expected: conductor-dashboard.js parses --backend-url and injects <script>window.__CONDUCTOR_BACKEND_URL__=...</script> before </head>
result: pass

### 5. Full dashboard test suite passes
expected: All 84 dashboard tests pass including 3 new URL derivation tests
result: pass

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0

## Gaps

[none]
