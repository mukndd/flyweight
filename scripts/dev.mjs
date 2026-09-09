import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { ROOT, venvPython } from './pyenv.mjs';

const synthetic = process.argv.includes('--synthetic');
const BRAIN_HOST = '127.0.0.1';
const BRAIN_PORT = 8000;

function log(line) { console.log(`[dev] ${line}`); }

function getJson(url, timeoutMs) {
  return new Promise(resolve => {
    const req = http.get(url, { timeout: timeoutMs }, res => {
      let body = '';
      res.on('data', c => { body += c; if (body.length > 100_000) req.destroy(); });
      res.on('end', () => {
        try { resolve({ ok: true, data: JSON.parse(body) }); }
        catch { resolve({ ok: false, reason: 'non-JSON response' }); }
      });
    });
    req.on('timeout', () => { req.destroy(); resolve({ ok: false, reason: 'timeout' }); });
    req.on('error', () => resolve({ ok: false, reason: 'connection refused' }));
  });
}

function isCompatibleHealth(data) {
  return data && data.v === 2 && data.type === 'health' && typeof data.neurons === 'number' && typeof data.edges === 'number' && typeof data.synthetic === 'boolean';
}

async function findExistingBrain() {
  const probe = await getJson(`http://${BRAIN_HOST}:${BRAIN_PORT}/health`, 1500);
  if (!probe.ok) return { present: false };
  if (!isCompatibleHealth(probe.data)) return { present: true, compatible: false };
  return { present: true, compatible: true, data: probe.data };
}

async function waitForHealth(timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const probe = await getJson(`http://${BRAIN_HOST}:${BRAIN_PORT}/health`, 1000);
    if (probe.ok && isCompatibleHealth(probe.data)) return probe.data;
    await new Promise(r => setTimeout(r, 300));
  }
  return null;
}

async function main() {
  let python;
  try { python = venvPython(); }
  catch (error) { console.error('[dev] ' + error.message); process.exit(1); }

  const manifestName = synthetic ? 'synthetic.json' : 'flywire.json';
  const manifestPath = path.join(ROOT, 'data', 'processed', manifestName);
  if (!fs.existsSync(manifestPath)) {
    console.error(`[dev] No prepared ${synthetic ? 'synthetic' : 'REAL'} Fly Brain graph found at data/processed/${manifestName}.`);
    console.error(`[dev] Run this first:  npm run setup:brain${synthetic ? ' -- --synthetic' : ''}`);
    if (!synthetic) console.error('[dev] (or pass --synthetic to this command for a clearly-labelled non-biological fixture while developing UI only)');
    process.exit(1);
  }

  // Mutable session state, declared up front so every closure below (including
  // ones that may fire before the corresponding child is assigned) sees them
  // safely instead of hitting a temporal-dead-zone error.
  let shuttingDown = false;
  let brainChild = null;
  let webChild = null;
  let weOwnBrain = false;

  function shutdown(code) {
    if (shuttingDown) return;
    shuttingDown = true;
    log('Shutting down...');
    if (webChild && webChild.exitCode === null) webChild.kill();
    if (weOwnBrain && brainChild && brainChild.exitCode === null) brainChild.kill();
    process.exitCode = code;
    setTimeout(() => process.exit(code), 3000).unref();
  }
  process.on('SIGINT', () => shutdown(0));
  process.on('SIGTERM', () => shutdown(0));

  log('Checking for an already-running Fly Brain service...');
  const existing = await findExistingBrain();

  if (existing.present && existing.compatible) {
    log(`Reusing already-running Fly Brain service on port ${BRAIN_PORT} (neurons=${existing.data.neurons} edges=${existing.data.edges} synthetic=${existing.data.synthetic}).`);
  } else if (existing.present && !existing.compatible) {
    console.error(`[dev] Port ${BRAIN_PORT} is already in use by an unrelated service (response did not match the Fly Brain health schema). Refusing to connect to it.`);
    console.error('[dev] Free the port or stop the other process, then retry.');
    process.exit(1);
  } else {
    log('Starting Fly Brain service (loading connectome)...');
    weOwnBrain = true;
    brainChild = spawn(python, ['-m', 'scripts.serve_brain'], {
      cwd: ROOT,
      env: { ...process.env, FLYWEIGHT_CONSOLE_LOG: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    const tail = [];
    const relay = (chunk) => {
      for (const line of chunk.toString().split(/\r?\n/)) {
        if (!line) continue;
        tail.push(line); if (tail.length > 40) tail.shift();
        console.log(`[brain] ${line}`);
      }
    };
    brainChild.stdout.on('data', relay);
    brainChild.stderr.on('data', relay);
    brainChild.on('exit', (code) => {
      if (shuttingDown) return;
      console.error(`[dev] Fly Brain service exited unexpectedly (code ${code}). Last log lines:`);
      for (const line of tail) console.error('  ' + line);
      shutdown(1);
    });

    const health = await waitForHealth(30_000);
    if (!health) {
      console.error('[dev] Fly Brain service did not become healthy within 30s. Last log lines:');
      for (const line of tail) console.error('  ' + line);
      shutdown(1);
      return;
    }
    log(`FLY BRAIN ONLINE — ${health.neurons.toLocaleString()} neurons, ${health.edges.toLocaleString()} connections, synthetic=${health.synthetic}.`);
    if (!synthetic && health.synthetic) {
      log('WARNING: requested the real graph but the running service reports synthetic=true. Re-run: npm run setup:brain');
    }
  }

  if (shuttingDown) return;
  log('Starting frontend (Vite)...');
  webChild = spawn(process.execPath, [path.join(ROOT, 'node_modules/vite/bin/vite.js'), '--config', 'vite.config.ts'], {
    cwd: ROOT, stdio: 'inherit', windowsHide: true,
  });
  webChild.on('exit', (code) => { if (!shuttingDown) shutdown(code ?? 0); });
}

main();
