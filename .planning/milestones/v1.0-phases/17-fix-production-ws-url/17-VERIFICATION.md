---
phase: 17-fix-production-ws-url
verified: 2026-03-11T10:59:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 17: Fix Production WebSocket URL — Verification Report

**Phase Goal:** npm dashboard package connects to the correct FastAPI backend in production — not the sirv static file server port
**Verified:** 2026-03-11T10:59:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Dashboard supports runtime backend URL configuration | VERIFIED | `getWsUrl()` in App.tsx reads `window.__CONDUCTOR_BACKEND_URL__`; TypeScript declaration in vite-env.d.ts |
| 2 | Production deployment connects WebSocket to FastAPI port, not sirv port | VERIFIED | `getWsUrl()` derives `ws://`/`wss://` from injected `http://`/`https://` URL and appends `/ws`; bin script injects the global via `--backend-url` flag |
| 3 | npm package documentation reflects production deployment configuration | VERIFIED | README.md contains "Production Deployment" section with two-server architecture table, `--backend-url` examples, and dev-mode note |

**Score:** 3/3 success criteria verified

### Must-Haves (from PLAN frontmatter)

| # | Must-Have | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Dashboard reads backend URL from `window.__CONDUCTOR_BACKEND_URL__` when present | VERIFIED | App.tsx L21-24: `const backendUrl = window.__CONDUCTOR_BACKEND_URL__; if (backendUrl) { ... return \`${wsUrl}/ws\`; }` |
| 2 | Dashboard falls back to same-origin URL when no backend URL is configured | VERIFIED | App.tsx L26-27: `const protocol = ...; return \`${protocol}//${window.location.host}/ws\`` |
| 3 | bin script accepts `--backend-url` CLI flag and injects it into served HTML | VERIFIED | conductor-dashboard.js L21-22: parses `--backend-url`, L47-51: `injectBackendUrl()` inserts `<script>window.__CONDUCTOR_BACKEND_URL__ = ...;</script>` before `</head>` |
| 4 | TypeScript type declaration for the injected global | VERIFIED | vite-env.d.ts L3-10: `interface Window { __CONDUCTOR_BACKEND_URL__?: string; }` |
| 5 | npm package documentation covers production deployment | VERIFIED | README.md L45-82: "Production Deployment" section with two-server table, startup commands, mechanism explanation, and dev mode note |

**Score:** 5/5 must-haves verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `packages/conductor-dashboard/src/App.tsx` | `getWsUrl()` with `window.__CONDUCTOR_BACKEND_URL__` check and same-origin fallback | VERIFIED | 79 lines; `getWsUrl()` at L20-28; wired into `useConductorSocket(getWsUrl())` at L44 |
| `packages/conductor-dashboard/src/vite-env.d.ts` | `Window.__CONDUCTOR_BACKEND_URL__?: string` declaration | VERIFIED | 10 lines; `interface Window { __CONDUCTOR_BACKEND_URL__?: string; }` |
| `packages/conductor-dashboard/src/App.test.tsx` | Tests for URL derivation from global and same-origin fallback | VERIFIED | 77 lines; 3 URL-derivation tests at L58-76 plus 3 existing integration tests |
| `packages/conductor-dashboard/bin/conductor-dashboard.js` | `--backend-url` arg parsing; HTML injection of script tag; conditional handler | VERIFIED | 84 lines; arg loop at L20-35; `injectBackendUrl()` at L47-51; conditional `handler` at L77 |
| `packages/conductor-dashboard/README.md` | "Production Deployment" section with two-server architecture docs | VERIFIED | 86 lines; section at L45-82 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `App.tsx getWsUrl()` | `window.__CONDUCTOR_BACKEND_URL__` | direct property read | WIRED | L21: `const backendUrl = window.__CONDUCTOR_BACKEND_URL__` |
| `App.tsx getWsUrl()` | `useConductorSocket` | called per-render | WIRED | L44: `useConductorSocket(getWsUrl())` — function called on each render, not captured as module-level constant |
| `conductor-dashboard.js` | `dist/index.html` | `readFileSync` + string replace | WIRED | L57-59: reads index.html, calls `injectBackendUrl(html, backendUrl)`, replaces `</head>` |
| `--backend-url` CLI flag | injected global | `JSON.stringify()` in script tag | WIRED | L48: `window.__CONDUCTOR_BACKEND_URL__ = ${JSON.stringify(url)};` — safe encoding |
| bin script handler | sirv | conditional delegation | WIRED | L77: `const handler = backendUrl ? requestHandler : sirvHandler` — preserves no-op behavior when flag absent |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PKG-02 | 17-01-PLAN.md | Node.js dashboard distributed as npm package (web UI) | SATISFIED | Production WebSocket URL configuration is a prerequisite for correct npm package behavior in production; runtime injection via `--backend-url` + `window.__CONDUCTOR_BACKEND_URL__` is fully implemented and tested |

PKG-02 maps to both Phase 11 (original packaging) and Phase 17 (production WS URL fix). REQUIREMENTS.md confirms both mappings are intentional. No orphaned requirements for Phase 17.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | No anti-patterns found |

No TODOs, FIXMEs, placeholder returns, or stub handlers found in any of the 5 modified files.

### Test Results

All 84 tests pass (`pnpm test --run`):

- `src/App.test.tsx` — 6 tests, all green, including:
  - `uses ws:// same-origin fallback when __CONDUCTOR_BACKEND_URL__ is not set`
  - `derives ws:// from http:// __CONDUCTOR_BACKEND_URL__`
  - `derives wss:// from https:// __CONDUCTOR_BACKEND_URL__`
- All other test files: 78 tests unchanged and passing

### Commits Verified

| Commit | Description | Verified |
|--------|-------------|---------|
| bba52cb | feat(17-01): add runtime backend URL support to App.tsx and TypeScript declarations | Present in git log |
| d563a83 | feat(17-01): add --backend-url flag to bin script with HTML injection | Present in git log |
| 3ab7048 | docs(17-01): add production deployment section to conductor-dashboard README | Present in git log |

### Human Verification Required

None. All behaviors are fully verifiable programmatically:

- URL derivation logic is pure string transformation — verified via unit tests
- Script tag injection is string replacement — inspectable in source
- Conditional handler selection is a simple ternary — readable in source
- README content is static documentation — readable directly

---

## Summary

Phase 17 achieves its goal. The npm dashboard package now correctly connects to the FastAPI backend WebSocket in production instead of same-origin (which would hit the sirv static file server). The mechanism is:

1. The bin script's `--backend-url` flag injects `window.__CONDUCTOR_BACKEND_URL__` into the served HTML at request time
2. `App.tsx getWsUrl()` reads this global on each render and derives `ws://`/`wss://` from the `http://`/`https://` backend URL
3. Without the flag, same-origin fallback preserves development mode behavior unchanged

All 5 must-haves are substantively implemented and wired. 84 tests pass. No stubs, no orphaned code, no missing connections.

---

_Verified: 2026-03-11T10:59:00Z_
_Verifier: Claude (gsd-verifier)_
