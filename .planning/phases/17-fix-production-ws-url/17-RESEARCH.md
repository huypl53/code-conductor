# Phase 17 Research: Fix Production WebSocket URL

## Problem Statement

The npm `conductor-dashboard` package has a production WebSocket URL mismatch. When deployed via `npm install -g conductor-dashboard`, the dashboard is served by **sirv** (a static file server) on one port (default 4173), while the FastAPI backend (which hosts the `/ws` WebSocket endpoint and `/state` REST endpoint) runs on a different port (typically 8000 via uvicorn). The dashboard's current WebSocket URL construction assumes both are on the same host:port, which only works during Vite development (where Vite proxies `/ws` to the backend).

## Current Architecture

### Dashboard Serving (Production)
- **File:** `packages/conductor-dashboard/bin/conductor-dashboard.js`
- **Mechanism:** sirv static file server serves built `dist/` assets
- **Default port:** 4173
- **Problem:** sirv only serves static files — it cannot proxy WebSocket connections to FastAPI

### WebSocket URL Construction
- **File:** `packages/conductor-dashboard/src/App.tsx` (line 11)
- **Current code:** `const WS_URL = \`\${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws\``
- **Behavior:** Constructs WebSocket URL from the current page host (sirv port), which has no `/ws` endpoint
- **Result:** WebSocket connection fails in production — connects to sirv:4173/ws instead of FastAPI:8000/ws

### Development Proxy (Works Correctly)
- **File:** `packages/conductor-dashboard/vite.config.ts`
- **Mechanism:** Vite dev server proxies `/ws` → `ws://127.0.0.1:8000` and `/state` → `http://127.0.0.1:8000`
- **This proxy only exists during `vite dev`, not in production**

### Backend Server
- **File:** `packages/conductor-core/src/conductor/dashboard/server.py`
- **Endpoints:** `GET /state` (snapshot) and `WS /ws` (live stream + interventions)
- **Started via:** `conductor run --dashboard-port <port>` — runs uvicorn on specified port

### Hook API
- **File:** `packages/conductor-dashboard/src/hooks/useConductorSocket.ts`
- **Accepts:** `url: string` parameter — already supports any WebSocket URL
- **No changes needed** — the hook is already URL-agnostic

## Root Cause

The dashboard assumes a same-origin deployment (browser page and WebSocket on same host:port). In production, two separate processes serve different concerns:
1. sirv (port 4173) — static HTML/JS/CSS
2. uvicorn/FastAPI (port 8000) — WebSocket + REST API

There is no reverse proxy or URL configuration bridge between them.

## Solution Options

### Option A: Runtime Configuration via Environment Variable (Recommended)
- Inject backend URL at build time via Vite `import.meta.env.VITE_CONDUCTOR_BACKEND_URL`
- At runtime, fall back to same-origin if not set (preserves dev experience)
- The bin script can accept a `--backend-url` CLI flag and inject it as a config

**Approach details:**
1. In `App.tsx`, check for `window.__CONDUCTOR_BACKEND_URL__` or a `<meta>` tag before falling back to same-origin
2. In `bin/conductor-dashboard.js`, accept `--backend-url` flag and inject it into the served HTML via sirv middleware or an inline script
3. This requires no rebuild — runtime configuration

### Option B: Single-Server Architecture
- Have the FastAPI server serve the static dashboard files too (via `StaticFiles` mount)
- Eliminates the two-port problem entirely
- Downside: couples the Python backend to the Node.js build output

### Option C: Build-Time Environment Variable Only
- Use `VITE_CONDUCTOR_BACKEND_URL` at `vite build` time
- Requires rebuild for each deployment configuration
- Less flexible than runtime injection

**Recommended:** Option A — runtime configuration via the bin script injecting a backend URL into the served page. This preserves the existing architecture while making production deployment work.

## Implementation Approach (Option A)

### Changes Required

1. **`packages/conductor-dashboard/src/App.tsx`**
   - Read backend URL from `window.__CONDUCTOR_BACKEND_URL__` (injected at runtime)
   - Fall back to same-origin WebSocket URL if not set (dev mode)
   - Similarly derive REST `/state` URL from the same config

2. **`packages/conductor-dashboard/bin/conductor-dashboard.js`**
   - Accept `--backend-url` CLI argument (e.g., `--backend-url http://127.0.0.1:8000`)
   - Inject a `<script>` tag with `window.__CONDUCTOR_BACKEND_URL__ = "..."` into the HTML before serving
   - Use sirv's `onNoMatch` or a custom middleware to intercept `index.html` and inject the config

3. **`packages/conductor-dashboard/src/hooks/useConductorSocket.ts`**
   - No changes needed — already accepts URL as parameter

4. **Tests:**
   - Test that `App.tsx` uses injected URL when present
   - Test that `App.tsx` falls back to same-origin when not present
   - Test bin script URL injection

5. **Documentation:**
   - Update npm package README with production deployment instructions
   - Document `--backend-url` flag

### Key Technical Details

- **sirv HTML injection:** sirv serves files from disk; to inject a script, intercept the request for `index.html` using a custom handler that reads the file, injects the script tag, and responds
- **WebSocket URL derivation:** Given `--backend-url http://127.0.0.1:8000`, derive WS URL as `ws://127.0.0.1:8000/ws`
- **REST URL derivation:** Same base URL for `/state` endpoint
- **Global type declaration:** Add `window.__CONDUCTOR_BACKEND_URL__` to TypeScript declarations in `vite-env.d.ts`

## Files to Modify

| File | Change |
|------|--------|
| `packages/conductor-dashboard/src/App.tsx` | Read injected backend URL, derive WS_URL and REST URL |
| `packages/conductor-dashboard/bin/conductor-dashboard.js` | Accept `--backend-url`, inject into HTML |
| `packages/conductor-dashboard/src/vite-env.d.ts` | TypeScript declaration for `window.__CONDUCTOR_BACKEND_URL__` |
| `packages/conductor-dashboard/src/App.test.tsx` | Test URL configuration behavior |
| `packages/conductor-dashboard/README.md` | Production deployment instructions |

## Dependencies

- Phase 11 (Packaging and Distribution) — the bin script and package structure already exist
- No new npm dependencies required — sirv + custom middleware is sufficient

## Risks

| Risk | Mitigation |
|------|------------|
| HTML injection complexity with sirv | sirv is a simple handler; wrap with custom middleware that intercepts `index.html` requests |
| TypeScript strictness for `window` property | Add declaration in `vite-env.d.ts` |
| Breaking dev experience | Same-origin fallback preserves zero-config dev mode |

## Validation Architecture

### Unit Tests
- `App.test.tsx`: Mock `window.__CONDUCTOR_BACKEND_URL__` and verify correct WS_URL derivation
- `App.test.tsx`: Verify same-origin fallback when global is not set

### Integration Tests
- `bin/conductor-dashboard.js`: Verify `--backend-url` flag injects script into served HTML
- Start bin script with `--backend-url`, fetch `index.html`, verify injected script tag

### Manual Verification
- Start FastAPI backend on port 8000
- Start dashboard with `conductor-dashboard --backend-url http://127.0.0.1:8000`
- Verify WebSocket connects to port 8000, not the sirv port
