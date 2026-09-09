import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { ROOT, venvPython } from './pyenv.mjs';

const synthetic = process.argv.includes('--synthetic');
const manifestPath = path.join(ROOT, 'data', 'processed', synthetic ? 'synthetic.json' : 'flywire.json');

function run(args, label) {
  console.log(`\n[setup:brain] ${label}`);
  const result = spawnSync(python, args, { cwd: ROOT, stdio: 'inherit', windowsHide: true });
  if (result.status !== 0) {
    console.error(`[setup:brain] FAILED: ${label} (exit ${result.status})`);
    process.exit(result.status ?? 1);
  }
}

let python;
try {
  python = venvPython();
} catch (error) {
  console.error('[setup:brain] ' + error.message);
  process.exit(1);
}

if (synthetic) {
  console.log('[setup:brain] --synthetic requested: preparing a labelled synthetic fixture. This is NOT the real Fly Brain and must never be presented as one.');
  run(['-m', 'services.brain.preprocess', '--synthetic'], 'Building synthetic fixture graph');
} else {
  console.log('[setup:brain] Preparing the REAL FlyWire v783-derived connectome subgraph.');
  run(['scripts/download_data.py'], 'Verifying/downloading real FlyWire v783 source data (~131 MB, cached and hash-checked; skipped if already present)');
  run(['-m', 'services.brain.preprocess'], 'Building the deterministic 1,536-neuron real subgraph (seed 783)');
}

if (!fs.existsSync(manifestPath)) {
  console.error(`[setup:brain] FAILED: expected manifest not found at ${manifestPath}`);
  process.exit(1);
}
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
if (manifest.synthetic !== synthetic) {
  console.error(`[setup:brain] FAILED: manifest synthetic=${manifest.synthetic}, expected ${synthetic}`);
  process.exit(1);
}
console.log('\n[setup:brain] Ready.');
console.log(JSON.stringify({
  synthetic: manifest.synthetic,
  neurons: manifest.neurons,
  edges: manifest.edges,
  seed: manifest.seed,
  graph_hash: manifest.graph_hash,
  sources: manifest.sources ?? null,
}, null, 2));
if (synthetic) {
  console.log('\n[setup:brain] SYNTHETIC fixture ready. Run without --synthetic for the real Fly Brain.');
} else {
  console.log('\n[setup:brain] REAL Fly Brain data ready. Run: npm run dev');
}
