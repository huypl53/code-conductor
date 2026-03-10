#!/usr/bin/env node
import sirv from 'sirv';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const distDir = join(__dirname, '..', 'dist');
const port = parseInt(process.argv[2] || '4173', 10);

const handler = sirv(distDir, { single: true });
createServer(handler).listen(port, () => {
  console.log(`Conductor Dashboard: http://localhost:${port}`);
});
