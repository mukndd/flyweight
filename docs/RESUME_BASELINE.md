# Resume baseline — 2026-09-09 (Fly Brain online/trainable phase)

Prior baseline (start of this phase) is preserved below; this section is the
current state after making the Fly Brain reliably start and demonstrating
real CEM learning end to end.

## Root cause of "Fly Brain offline" (now fixed)

Not a code defect. `npm run dev` (`scripts/task.mjs`) only ever started
Vite; nothing started the Python brain service, and the README wrongly
implied it did. A fresh checkout also has no connectome data (git-ignored).
Fixed: `npm run dev` (`scripts/dev.mjs`) now starts the brain service, waits
for real `/health`, then starts Vite, streams both logs, reuses an
already-running compatible service, refuses (clearly, not silently) to
start without prepared real data unless `--synthetic` is passed, and shuts
both down together. `npm run setup:brain` wraps download+preprocess behind
one command. README quick start corrected.

## Real Fly Brain, verified live this session

`/health`: `neurons=1536 edges=170489 synthetic=false`. Live Playwright load
of `npm run dev` showed "Fly Brain engine online — 1,536 neurons · 170,489
connections" in the header, with real FlyWire root IDs and live
`neural_activity`/`action` messages streaming during an actual match.

## Training: pipeline confirmed capable of real learning

Audited `packages/sim/core.ts` `roundReward` — already dense (damage
dealt/received, blocks, idle penalty, damage-gated arena control), not a
bare win/loss signal. The historical 0%-win-rate two-generation runs look
like a trivial training budget, not a reward or architecture problem.

Added to `services/brain/trainer.py`: `--preset {starter,serious}`,
`--difficulties` (curriculum via sequential resumed runs), `--resume`
(continues a named run's CEM mean/std/generation counter; fails clearly on
a connectome-graph mismatch rather than silently restarting), configurable
elite fraction/sigma/checkpoint interval. All defaults exactly reproduce
prior behaviour, so the existing browser-triggered (`train_start` WS
message) training path is unaffected. Caught and fixed a real bug during
testing: `save_resume_state`/`load_resume_state` must be called with
`root=CHECKPOINTS` explicitly inside `train()`, since a function's default
argument is bound at import time and does not see later monkeypatching —
without the fix, tests silently leaked resume-state files into the real
`checkpoints/` directory. 14 new tests in
`services/brain/tests/test_trainer.py`; all 75 backend tests pass.

Baseline (seed-initialized, untrained, seed 783, full evaluation-v2 suite,
9 episodes): **0% win rate**, mean_reward −39.8 (0 dealt/received vs
easy/medium — essentially no engagement; vs hard: 30 dealt, 100 received,
reward −119).

Ran a `--preset starter` pilot (seed 42, 4 generations, population 8,
easy-only, ~7s wall clock): best training-generation reward rose from
~41 to ~68 before a late-generation regression; held-out win rate reached
22% (from the same architecture, same 0% baseline) — real, if noisy,
evidence that fixed-connectome + trainable-adapter CEM search learns.

Ran a `--preset serious` run (seed 42, 20 generations, population 12, all
three difficulties, ~3m44s wall clock, self-bounded under the existing
600s per-invocation cap): held-out evaluation-v2 suite (9 episodes) —
**100% win rate**, mean_reward 45.0 (95% CI [39.8, 50.2]), 0 failures,
average damage dealt 87.2, average duration 19.1s. Promoted via the
existing evaluation-gated CLI (`trainer promote`) — the gate (win_rate ≥
.55, reward improvement over previous canonical) was met honestly, not
loosened. `checkpoints/canonical.json` now points at
`candidate_78931b4895b24b48` (hash
`b6408220972aa4bb091012dd0ae5bbe40dd0567cb7f206dfdb8db2b1c15f4abd`).
Verified live in the browser: selecting this checkpoint in the Fly Brain
mode dropdown loads genuinely different adapter parameters and action
scores than "seed-initialized".

**Honest caveat worth follow-up**: against medium and hard, all three held-out
seeds produced byte-identical final game-state hashes for the same
difficulty pairing pattern (100 damage dealt / 91 received / 16.1s every
time) — the trained policy appears to have found a difficulty-insensitive,
seed-insensitive dominant sequence rather than a nuanced adaptive one. Not
hidden; flagged as something a follow-up session should look at (possibly
add per-episode input noise/varied spacing, or check whether the medium/
hard rule-bots are distinguishable enough against this attack pattern).

## Fixed vs. trainable (unchanged, still enforced)

Fly wiring, topology, edge direction, synapse-derived weight magnitude,
transmitter sign: fixed, verified untouched by training
(`test_training_cannot_mutate_fixed_graph`). Trainable: encoder, readout,
bias only. No connectome topology change of any kind occurred.

## Known pending issues carried forward

- Trained-policy medium/hard determinism above — needs investigation, not
  explained yet.
- `train()` reports/evaluates only the final generation's best candidate,
  not the best-ever-seen across the whole run — in the starter pilot,
  generation 2 had a higher training reward than the reported final
  (regressed) generation 4; worth tracking best-ever separately in a
  future session.
- Three-tier SIMPLE/NETWORK/RESEARCH visualization, scientific-controls
  comparison harness (real vs. randomized vs. rule topology, same
  methodology), and gradient-based training as a second experimental mode
  were explicitly out of scope for this phase (deferred per the phase's own
  instructions) — not started.
- No deployment, no remote, no Docker build verified (Docker not installed
  on this machine — Dockerfiles were validated statically in the prior
  phase).

---

## Prior baseline (2026-09-09, start of this phase)

The first phase was interrupted before final documentation, audits and milestone commits.
Existing architecture: Vite/React/TypeScript + Phaser Canvas; shared TypeScript combat engine compiled for a bounded Node bridge; Python FastAPI WebSocket brain; immutable v783 subgraph; NumPy adapter CEM; safe NPZ checkpoints; action-log replay.
Data: 138,639 source neurons / 15,091,983 source directed rows; selected 1,536 neurons / 170,489 directed edges, seed 783.
Resumed unchanged checks: build/typecheck passed; Vitest 7 passed; Pytest 47 passed. Previous Playwright: 3 passed, 1 failed (decorative icon included in Play accessible name). Live neural complete round + identical replay hash, training cancellation, offline fallback passed. ESLint passed. Ruff had seven import/unused-import findings. Bandit had one LOW advisory for the reviewed fixed-command subprocess bridge.
Two-generation CEM candidate held-out win rate: 0%; no canonical promotion.
Known pending issues: research controls labelled too broadly as real topology; inactive rule baselines still report active graph; replay display retains stale neural values; live transport/session provenance incomplete; documentation/inventory/audits/CI not yet completed.
No remote configured; no deployment; no administrator or global software changes. Default sandbox helpers fail after repository initialization; commands use the separately approved execution path without Windows administrator rights. Git ownership differs between execution contexts; use a command-scoped safe.directory for this exact workspace, never global configuration.
New phase will preserve v1 source and replay compatibility and version expanded actions/checkpoints rather than silently reinterpret old experiments.
