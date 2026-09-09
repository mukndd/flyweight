import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = fileURLToPath(new URL('../', import.meta.url));

export function venvPython() {
  const candidates = process.platform === 'win32'
    ? [path.join(ROOT, '.venv', 'Scripts', 'python.exe')]
    : [path.join(ROOT, '.venv', 'bin', 'python3'), path.join(ROOT, '.venv', 'bin', 'python')];
  const found = candidates.find(p => fs.existsSync(p));
  if (!found) {
    throw new Error(
      'Project Python virtual environment not found (looked for ' + candidates.join(', ') + ').\n' +
      'Create it first:\n' +
      '  python -m venv .venv\n' +
      (process.platform === 'win32' ? '  .venv\\Scripts\\activate\n' : '  source .venv/bin/activate\n') +
      '  pip install -r requirements-dev.txt'
    );
  }
  return found;
}
