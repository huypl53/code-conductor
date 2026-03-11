#!/usr/bin/env node
import sirv from 'sirv';
import { createServer } from 'node:http';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distDir = join(__dirname, '..', 'dist');

// ---------------------------------------------------------------------------
// Argument parsing
// Supports: conductor-dashboard [port] [--backend-url <url>]
// ---------------------------------------------------------------------------

let port = 4173;
let backendUrl = null;

const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--backend-url' && args[i + 1]) {
    backendUrl = args[i + 1];
    i++; // skip next arg (the URL value)
  } else if (args[i] === '--help' || args[i] === '-h') {
    console.log('Usage: conductor-dashboard [port] [--backend-url <url>]');
    console.log('');
    console.log('Options:');
    console.log('  port               Port to serve the dashboard on (default: 4173)');
    console.log('  --backend-url URL  FastAPI backend URL for WebSocket (e.g. http://127.0.0.1:8000)');
    console.log('  --help             Show this help message');
    process.exit(0);
  } else if (/^\d+$/.test(args[i])) {
    port = parseInt(args[i], 10);
  }
}

// ---------------------------------------------------------------------------
// Request handler
// ---------------------------------------------------------------------------

const sirvHandler = sirv(distDir, { single: true });

/**
 * Inject a global __CONDUCTOR_BACKEND_URL__ script tag into index.html.
 * Returns the modified HTML string.
 */
function injectBackendUrl(html, url) {
  const scriptTag = `<script>window.__CONDUCTOR_BACKEND_URL__ = ${JSON.stringify(url)};</script>`;
  // Inject before </head> so the global is available before app scripts run
  return html.replace('</head>', `${scriptTag}\n</head>`);
}

function requestHandler(req, res) {
  const pathname = req.url?.split('?')[0] ?? '/';
  if (pathname === '/' || pathname === '/index.html') {
    try {
      const indexPath = join(distDir, 'index.html');
      const html = readFileSync(indexPath, 'utf8');
      const modified = injectBackendUrl(html, backendUrl);
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(modified);
      return;
    } catch {
      // Fall through to sirv if index.html is unreadable (shouldn't happen in production)
    }
  }
  sirvHandler(req, res, () => {
    res.writeHead(404);
    res.end('Not found');
  });
}

// ---------------------------------------------------------------------------
// Server startup
// ---------------------------------------------------------------------------

const handler = backendUrl ? requestHandler : sirvHandler;

createServer(handler).listen(port, () => {
  console.log(`Conductor Dashboard: http://localhost:${port}`);
  if (backendUrl) {
    console.log(`Backend URL: ${backendUrl}`);
  }
});
