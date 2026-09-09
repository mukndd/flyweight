import { spawn } from 'node:child_process';
import { ROOT, venvPython } from './pyenv.mjs';

let python;
try { python = venvPython(); }
catch (error) { console.error('[dev:brain] ' + error.message); process.exit(1); }

const child = spawn(python, ['-m', 'scripts.serve_brain'], {
  cwd: ROOT,
  env: { ...process.env, FLYWEIGHT_CONSOLE_LOG: '1' },
  stdio: 'inherit',
  windowsHide: true,
});
child.on('exit', (code) => process.exit(code ?? 0));
process.on('SIGINT', () => child.kill());
process.on('SIGTERM', () => child.kill());
