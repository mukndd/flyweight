import { spawnSync, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
const task = process.argv[2];
const commands = {
  dev: [['node_modules/vite/bin/vite.js','--config','vite.config.ts']],
  build: [['node_modules/typescript/bin/tsc','--noEmit'],['node_modules/typescript/bin/tsc','-p','tsconfig.sim.json'],['node_modules/vite/bin/vite.js','build','--config','vite.config.ts']],
  sim: [['node_modules/typescript/bin/tsc','-p','tsconfig.sim.json']],
  test: [['node_modules/vitest/vitest.mjs','run','--config','vite.config.ts']],
  lint: [['node_modules/eslint/bin/eslint.js','apps/web/src','packages','tests']],
  e2e: [['node_modules/playwright/cli.js','test']],
};
if (!Object.hasOwn(commands,task)) throw new Error('Unknown task');
if (task === 'dev') {
  const [file,...args]=commands[task][0];
  const child=spawn(process.execPath,[path.join(root,file),...args],{cwd:root,stdio:'inherit',windowsHide:true});
  process.on('SIGINT',()=>child.kill());
} else for (const [file,...args] of commands[task]) {
  const result=spawnSync(process.execPath,[path.join(root,file),...args],{cwd:root,stdio:'inherit',windowsHide:true,timeout:180000});
  if(result.status !== 0) process.exit(result.status ?? 1);
}
