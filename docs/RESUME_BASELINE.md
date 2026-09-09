# Resume baseline — 2026-09-09

The first phase was interrupted before final documentation, audits and milestone commits.
Existing architecture: Vite/React/TypeScript + Phaser Canvas; shared TypeScript combat engine compiled for a bounded Node bridge; Python FastAPI WebSocket brain; immutable v783 subgraph; NumPy adapter CEM; safe NPZ checkpoints; action-log replay.
Data: 138,639 source neurons / 15,091,983 source directed rows; selected 1,536 neurons / 170,489 directed edges, seed 783.
Resumed unchanged checks: build/typecheck passed; Vitest 7 passed; Pytest 47 passed. Previous Playwright: 3 passed, 1 failed (decorative icon included in Play accessible name). Live neural complete round + identical replay hash, training cancellation, offline fallback passed. ESLint passed. Ruff had seven import/unused-import findings. Bandit had one LOW advisory for the reviewed fixed-command subprocess bridge.
Two-generation CEM candidate held-out win rate: 0%; no canonical promotion.
Known pending issues: research controls labelled too broadly as real topology; inactive rule baselines still report active graph; replay display retains stale neural values; live transport/session provenance incomplete; documentation/inventory/audits/CI not yet completed.
No remote configured; no deployment; no administrator or global software changes. Default sandbox helpers fail after repository initialization; commands use the separately approved execution path without Windows administrator rights. Git ownership differs between execution contexts; use a command-scoped safe.directory for this exact workspace, never global configuration.
New phase will preserve v1 source and replay compatibility and version expanded actions/checkpoints rather than silently reinterpret old experiments.

