import { spawnSync } from 'node:child_process';
import { ROOT, venvPython } from './pyenv.mjs';

let python;
try { python = venvPython(); }
catch (error) { console.error(error.message); process.exit(1); }

const result = spawnSync(python, ['-m', ...process.argv.slice(2)], { cwd: ROOT, stdio: 'inherit', windowsHide: true });
process.exit(result.status ?? 1);
