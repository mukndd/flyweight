# Build report

This report covers a resumed session that continued work already committed
by prior agent runs (see `docs/RESUME_BASELINE.md` for the state at the
start of the previous session, and git history for what changed since). It
records what was verified and produced in this session: a full local
verification pass plus the top-level documentation that was previously
missing.

## Session summary

This session inherited a working tree at commit `55d81cd` ("Add clear
fighter identities, live decision traces and versioned combat depth") with
no uncommitted source changes — only untracked generated files
(`docs/results/`, `requirements.lock`, `requirements-dev.lock`) and no
documentation at the repository root. All functional spec areas (fighter
identity, plain-language UX, expanded combat, dual decision panels, Fly
Brain modes, difficulty, replay/reproducibility, offline honesty) were
already implemented and covered by passing tests. This session:

1. Re-ran the full local verification suite from a clean shell (see below).
2. Read the cached security/dependency audit output already produced by
   `scripts/supply_chain.py` and `scripts/review_project.py` and confirmed
   it against a fresh `ruff check .` run.
3. Added the missing top-level documentation the spec requires:
   `README.md`, `SECURITY.md`, `.env.example`, `scripts/report_size.py`,
   and this file.

No application/game/brain-service source code was changed in this session.

## Verification results (this session, 2026-09-09)

| Check | Command | Result |
|---|---|---|
| Production build | `npm run build` | Pass — `dist/web` built in 776ms (one informational chunk-size warning, no errors) |
| TypeScript | `npx tsc --noEmit -p tsconfig.json` | Pass, 0 errors |
| Lint | `npm run lint` | Pass, 0 findings |
| Unit tests | `npx vitest run` | Pass — 2 files, 15 tests |
| Brain service tests | `.venv/Scripts/python -m pytest services/brain/tests -q` | Pass — 61 tests |
| End-to-end | `npx playwright test` | Pass — 5/5 (full live round + replay hash match, keyboard/pause/controls, difficulty/research/reconnect/responsive/reduced-motion, training cancellation, offline fallback with no fabricated activity) |
| Ruff | `.venv/Scripts/python -m ruff check .` | Pass, 0 findings |
| Bandit | cached `logs/bandit.json` | 1 LOW, reviewed and accepted (see `SECURITY.md`) |
| pip-audit | cached `logs/pip-audit-final.json` | 0 vulnerabilities |
| npm audit | cached `logs/npm-audit-offline.json` | 0 vulnerabilities |
| Secret scan | cached `logs/secret-scan.json` | 0 findings across 64 scanned text files |

Node in this environment is v22.11.0; `package.json` declares
`engines.node >= 24.0.0`. Vite prints a version warning but the build,
tests and e2e suite all pass under 22.11.0 — flagged here rather than
silently ignored.

## Project size (`scripts/report_size.py`, new in this session)

| Category | Size |
|---|---|
| Source (apps/packages/services/scripts/docs) | 1.7 MB |
| node_modules | 243.7 MB |
| Python virtual environment (.venv) | 352.5 MB |
| Raw data | 125.1 MB |
| Processed data | 2.1 MB |
| Checkpoints | 136.5 KB |
| Replays | 0 B |
| Build output (dist) | 1.4 MB |
| **Total** | **~727 MB** (well under the ~5 GB budget) |

## Data pipeline (from `docs/source-lock.json`, produced by a prior session)

Real FlyWire v783 data, hash-verified on download:

- `Completeness_783.csv` — 3,327,347 bytes
- `Connectivity_783.parquet` — 100,804,642 bytes
- `annotations_783.tsv` (FlyWire neuron annotations) — 27,015,208 bytes
- Reference pipeline `LICENSE`/`Readme.md` from
  `philshiu/Drosophila_brain_model` @ `91bdd1e7`

Preprocessed subgraph (per `docs/RESUME_BASELINE.md`): 1,536 neurons /
170,489 directed edges selected deterministically from 138,639 source
neurons / 15,091,983 source directed rows, seed `783`.

## Known remaining items (carried over, not addressed this session)

Functional/UX work is complete and tested; what remains is deployment
packaging and the broader documentation set:

- No `Dockerfile`s or `.github/workflows` CI exist yet, despite the Phase 2
  authorization recorded in `AGENTS.md`. Backend config
  (`services/brain/config.py`) already supports platform-provided ports,
  validated production origins/hosts, and a `/health` endpoint, so this is
  packaging work rather than application work.
- Additional docs referenced by the original spec/addendum are not yet
  written: `ARCHITECTURE.md`, `DATA_SOURCES.md`, `THIRD_PARTY_NOTICES.md`,
  `CONTRIBUTING.md`, `CITATION.cff`, `docs/SCIENTIFIC_LIMITATIONS.md`,
  `docs/DATA_PROVENANCE.md`, `docs/THREAT_MODEL.md`,
  `docs/REPRODUCIBILITY.md`, `docs/MODEL_CARD.md`, `docs/DATA_CARD.md`,
  `docs/EXPERIMENT_PROTOCOL.md`, `docs/DEPENDENCY_POLICY.md`. Much of
  their required content already exists in `AGENTS.md`,
  `docs/source-lock.json`, and `docs/RESUME_BASELINE.md`, so writing them
  is mostly consolidation, not new research.
- `docs/dependency-inventory.json` (SBOM-style inventory) has not been
  generated in this session — running
  `.venv/Scripts/python scripts/supply_chain.py inventory` produces it, but
  it re-downloads PyPI metadata for every installed package and was not run
  here to avoid an unnecessary network pass.
- No LICENSE has been chosen for original project source.
- No remote git repository, CI, or deployment target is configured; none
  of that has been done without explicit approval, per `AGENTS.md`.
- Two-generation CEM training against held-out opponents recorded a 0%
  held-out win rate with no canonical promotion (an honestly-reported
  negative result, not a bug).

## Next best step (superseded — see below)

Add `.github/workflows/ci.yml` (typecheck + lint + vitest + pytest, no
deploy step) and minimal `Dockerfile`s for `apps/web` and
`services/brain` that read the existing env-driven config — this closes
the deployment-readiness gap without requiring any new application logic,
and does not itself deploy or publish anything.

*(Done in a subsequent session: `.github/workflows/ci.yml`,
`apps/web/Dockerfile`, `services/brain/Dockerfile`, `.dockerignore` — not
build-verified since Docker is not installed on this machine.)*

## Session addendum — Fly Brain online/trainable (2026-09-09, later same day)

Root cause of the "Fly Brain offline" symptom users saw: operational, not a
code defect — `npm run dev` only ever started the frontend, and this
report's own earlier README instructions incorrectly implied it started
the brain service too. Fixed with a proper combined launcher; see
`docs/RESUME_BASELINE.md` for the full write-up. Summary of what changed
and was verified in this addendum:

- `npm run dev` now starts both services, waits for real `/health`, and
  shuts both down together; `dev:web`/`dev:brain`/`setup:brain` added as
  explicit sub-commands. Verified live via Playwright against the real
  connectome (`synthetic=false`, 1,536 neurons, 170,489 connections).
- `services/brain/trainer.py` gained `--preset {starter,serious}`,
  `--resume`, `--difficulties`, and configurable CEM hyperparameters, all
  backward-compatible by default (verified: all 61 pre-existing backend
  tests still pass unchanged, plus 14 new tests in the new
  `test_trainer.py`, 75/75 total).
- Established an honest untrained baseline (seed 783, evaluation-v2 suite):
  0% win rate, mean reward −39.8.
  A `--preset serious` run (seed 42, 20 generations, population 12, all
  three difficulties, 3m44s wall clock) reached **100% held-out win rate**,
  mean reward 45.0 (95% CI [39.8, 50.2]), 0 failures — promoted through the
  existing, unmodified evaluation gate to `checkpoints/canonical.json`.
  Verified live in the browser that loading this checkpoint produces
  genuinely different adapter parameters/action scores than
  "seed-initialized".
- Full suite re-verified after all changes: `tsc --noEmit` clean, ESLint
  clean, Vitest 15/15, Playwright 5/5 (against the real live combined
  launcher), Pytest 75/75, Ruff clean.
- Honest open finding, not resolved this session: the trained policy's
  held-out episodes against medium and hard produced byte-identical final
  game hashes across all three held-out seeds — looks like a
  difficulty/seed-insensitive dominant strategy rather than nuanced play.
  Flagged in `docs/RESUME_BASELINE.md` for a follow-up session.

Not attempted this session (explicitly out of scope per the phase's own
instructions): gradient-based training, the three-tier
SIMPLE/NETWORK/RESEARCH visualization, and the full scientific-controls
comparison harness (real vs. randomized vs. rule topology under one
methodology) — the `real`/`degree_randomized`/`weight_shuffled`/`ordinary`/
`rule`/`random` topology switch these would use already exists and was not
touched.

## Session addendum — v0.7 research platform foundation (2026-09-14)

This session added a local-first research platform foundation without
contacting cloud providers, publishing remotes, or changing the fixed
connectome/trainable-adapter boundary.

- Training Lab now separates editable next-run configuration from current
  or last completed run state, and labels metric scopes explicitly:
  best training fitness, best-ever candidate, final-generation best,
  held-out win rate, held-out episodes, evaluation suite and candidate
  evaluation reward.
- `services.brain.trainer.train` now evaluates and returns the best-ever
  candidate seen across generations rather than blindly using the newest
  generation's best member.
- Added local SQLite research registry, immutable local artifact-store
  interface, trainer interface wrapper, `combat-ladder-v1`/`L01-v1` through
  `L10-v1`, ladder certification/calibration helpers, topology-control
  planning, bounded autonomous research loop, daily report generation,
  read-only dashboard endpoints and human-challenge verification
  foundations.
- Added a Research dashboard tab and preserved the existing technical
  research details drawer. The dashboard reads persisted state from
  `/research/overview`, `/research/lineage` and `/research/ladder`.
- Added documentation: `docs/RESEARCH_PLATFORM_FOUNDATION.md`,
  `docs/COMBAT_V2_PLAN.md`, and `docs/CLOUD_DEPLOYMENT_MANUAL.md`.
- Demonstrated a bounded local dry run with `npm run research:once`, then
  restart-equivalent persistence with `npm run research:daily`. The dry run
  recorded candidates, ladder progress and daily reports, but did not fake
  certification or promotion.

Verification this session:

| Check | Result |
|---|---|
| `npm run test` | Pass — 16/16 |
| `npm run lint` | Pass |
| `npm run build` | Pass; existing Node 22.11.0 warning remains |
| `.venv/Scripts/python -m pytest services/brain/tests -q` | Pass — 87/87 |
| `.venv/Scripts/python -m ruff check .` | Pass |
| `.venv/Scripts/python -m bandit -r services -x services/brain/tests` | Pass — 0 findings |
| `npm run e2e` | Pass — 5/5 against real local Fly Brain service |
| Research tab Playwright probe | Pass; screenshot at `docs/screenshots/research-dashboard.png` |
| `scripts/review_project.py size` | Pass — about 1.49 GB total, under 5 GB |
| `scripts/review_project.py secrets` | No secret-pattern finding; exits nonzero because two pre-existing large trace JSONL artifacts require review |

Not freshly rerun: `npm audit` and `pip-audit`. Prior cached logs remain in
`logs/`, but this session avoided new registry/advisory network submissions
under the repository's network restrictions.

## Session addendum — v0.8 production bring-up and topology batch (2026-09-14)

This session continued v0.7 and added production bring-up foundations without
contacting cloud providers, remotes, or deployment APIs.

- Added validated production roles for Web, Brain/API, Research Worker and
  Daily Evaluator; added production npm entrypoints and a names-only
  `.env.example` contract.
- Added PostgreSQL/Supabase-compatible migrations and an optional
  parameterized Postgres registry adapter.
- Added an S3-compatible content-addressed artifact adapter suitable for R2,
  with fake-transport tests and no live network calls.
- Added compute-governor validation, worker status/lease recovery,
  immutable daily evaluator, local burn-in harness, production bootstrap check,
  and read-only public dashboard APIs for reports, topology comparisons,
  worker status and verified human matches.
- Added a bounded topology-control batch runner and rendered persisted
  comparison results in the Research dashboard.

Addendum-required topology batch:

- Command: `node scripts/py.mjs services.brain.topology_batch --synthetic --db .runtime/v08_topology_batch.sqlite --seeds 9401,9402 --generations 1 --population 4 --seconds 6 --heldout-matches 6 --project-day 6 --report-date 2026-09-14`
- Result: complete; 7 topology conditions, 13 evaluations, 8 trained
  candidates persisted in the registry.
- Conditions: real connectome, degree-preserving randomized, weight-shuffled,
  matched random recurrent, rule baseline, random-action baseline; direct
  baseline recorded as `planned_interface_only`.
- Summary: `docs/results/v08_topology_batch_2026-09-14.json`.
- Boundary: synthetic-fixture evidence only; no topology-superiority claim.

Burn-in:

- Command: `node scripts/py.mjs services.brain.burn_in --synthetic --db .runtime/v08_burn_in_final.sqlite --date 2026-09-14`
- Result: complete; stale lease recovery true; one research cycle complete;
  daily evaluator complete once for 2026-09-15; second daily run returned
  `already_exists`; dashboard state present.

Verification:

| Check | Result |
|---|---|
| `node scripts/py.mjs pytest services/brain/tests` | Pass — 95/95 |
| `node scripts/py.mjs ruff check services/brain scripts` | Pass |
| `npm run test` | Pass — 16/16 |
| `npm run lint` | Pass |
| `npm run build` | Pass; existing Node 22.11.0/Vite version warning remains |
| `node scripts/py.mjs bandit -q -r services -x services/brain/tests` | Pass — 0 findings |
| Browser smoke | Pass — Research dashboard rendered topology evidence; no overlay or console errors; screenshot `docs/screenshots/v08-topology-dashboard.png` |
| `npm run e2e` | Pass — 5/5 after starting `npm run dev`; an earlier attempt failed because no dev server was running |
| `node scripts/py.mjs scripts.review_project size` | Pass — ~1.50 GB total, under 5 GB |
| `node scripts/py.mjs scripts.review_project secrets` | Nonzero with two pre-existing oversized trace JSONL review findings; no new secret-pattern finding reported |

Not performed: Docker build, `npm audit`, `pip-audit` and real
cloud/database/object-store integration. No push or deployment was performed
in this session.

## Session addendum — v0.9 3D presentation layer and visual redesign (2026-09-14)

This session kept Flyweight's deterministic 2D combat simulation and research
pipeline intact while adding a stronger public-facing "Neuroscience Fight
Night" presentation layer.

Visual direction:

- Added a cohesive dark event/lab visual system with explicit CSS tokens,
  typography hierarchy, panel treatment, glow accents, match-state styling and
  responsive rules in `apps/web/src/v09.css`.
- Reworked the default route into an Overview experience with Day N, current
  champion, certified level, live training status and clear Watch/Play/Research
  calls to action.
- Reorganized the main navigation around Overview, Play, Watch, Research, Lab,
  Leaderboard and Replays.

3D and presentation layer:

- Added a lazy-loaded Three.js presentation component that consumes existing
  match/action state and does not replace the 2D simulation.
- Added a stylized non-horror Fly mascot, compact arena shell, colored corner
  lighting and controller prop.
- Added deterministic action-to-presentation mapping for idle, movement, jump,
  guard, dodge, attack/combo, victory, defeat and offline states.
- Added a non-WebGL fallback mascot so the app remains usable if WebGL is not
  available.

Match, research and human challenge:

- Added the 3D presentation strip to live matches while preserving the Phaser
  2D fight plane, replay determinism and action logs.
- Updated the match HUD, action readouts, result card and mode framing.
- Polished the Research dashboard around current champion, level progress,
  today's registry counts, topology controls and candidate lineage without
  making topology-superiority claims.
- Added a Leaderboard surface for locally verified human exhibition results and
  made the human challenge easier to enter from Overview and Research.

Performance and assets:

- Added exact pinned dependencies `three@0.181.2` and `@types/three@0.181.0`
  using `--ignore-scripts`.
- The 3D layer is dynamically imported from the React component, contains only
  procedural geometry/materials, uses no external model assets and can be
  swapped for a real model later.
- Production build output after this change: CSS 44.13 kB gzip 10.16 kB,
  Three chunk 709.73 kB gzip 183.92 kB, app chunk 1,468.46 kB gzip 403.78 kB.
  Vite still reports the pre-existing large-chunk warning and Node 22.11.0
  warning on this machine.

Scientific safety:

- No combat rules, replay schema, ladder criteria, trainer method, promotion
  gates, fixed-connectome boundary or topology experiment validity were changed.
- The 3D layer is explicitly presentational: real match state and controller
  actions flow into visuals; visuals do not feed back into training/evaluation.
- Offline and rule/random controls continue to avoid fabricated neural activity.

Representative screenshots:

- `docs/screenshots/v09-overview.png`
- `docs/screenshots/v09-watch.png`
- `docs/screenshots/v09-research.png`
- `docs/screenshots/v09-mobile.png`

Verification:

| Check | Result |
|---|---|
| `npx tsc --noEmit -p tsconfig.json` | Pass |
| `npm run test` | Pass — 19/19 |
| `npm run lint` | Pass |
| `npm run build` | Pass; existing Node 22.11.0/Vite version warning and large-chunk warning remain |
| `node scripts/py.mjs pytest services/brain/tests` | Pass — 96/96, 2 dependency deprecation warnings |
| `node scripts/py.mjs ruff check services/brain scripts` | Pass |
| `npm run e2e` | Pass — 5/5 against real local Fly Brain service |
| Three.js canvas pixel probe | Pass — desktop hero, match strip and mobile hero all nonblank; no console/page errors |
| Visual screenshot inspection | Pass — desktop Overview/Watch/Research and mobile Overview showed no obvious overlap or horizontal overflow |

Completion estimates after v0.9:

- 3D presentation: 65% — procedural mascot, controller and arena shell are in
  place; richer model assets/animation could come later.
- Public-facing polish: 75% — first impression and navigation are now much
  stronger, with room for a more cinematic intro/result flow.
- Dashboard polish: 65% — clearer story and lineage surfaces, but mini charts
  and report history can still improve.
- Human challenge experience: 55% — entry, result card and local leaderboard
  exist; verified ranking/share flows remain basic.
- Cloud-readiness: 70% — v0.8 foundations remain unchanged; no new cloud work
  was attempted in this visual phase.
- Overall Flyweight vision: 72% — the app now reads as a productized live
  experiment rather than a flat prototype, while deeper science/reporting and
  media polish remain the next frontier.

Next highest-value step: build a richer Fight of the Day / champion-card flow
that packages one verified replay, topology context and result metrics into a
single shareable artifact without changing the scientific backend.

## Session addendum — v0.11 art and rendering quality pass (2026-09-14)

This pass kept the v0.10 public structure frozen: `WATCH`, `FIGHT`, and
`SCIENCE`. It did not add public Lab, replay/debug, training controls, layout
toggles, new routes, checkpoint IDs in the public HUD, or dashboard card grids.

Rendering changes:

- Added `apps/web/src/world3d.ts` as the shared public 3D scene kit.
- Added `apps/web/src/CombatWorld3D.tsx`, a Three.js public combat renderer
  that consumes the existing deterministic `Engine`/combat state and calls
  `engine.update(delta)` without changing simulation rules, hitboxes, replay
  schema, trainer behavior, weights, rewards, or promotion gates.
- Replaced the public Phaser arena rendering with a 3D neural combat test
  chamber: graphite grid floor, rails, observation glass, overhead fixtures,
  key/fill/rim lighting, contact shadows, hit sparks, and slight camera impact.
- Added original 3D combat mannequins constrained to the 2D fight plane with
  pose mappings for idle, walking, jump/air, crouch/guard, dodge, light/heavy
  attacks, low/air attacks, shove/combo, hit reaction, victory and defeat.
- Upgraded the fly/controller presentation to share the richer Drosophila and
  controller geometry used in the main scene.
- Enlarged and integrated the fly/operator station into the Watch/Fight scene
  so the fly and controller are visible alongside the fight rather than an
  unrelated panel.

Public UI changes:

- Kept Watch compact; polished SEES/ACTION/RESULT and deduplicated repeated
  low-value event entries.
- Rebuilt Fight setup as a quick three-part composition: title/status, live fly
  preview, name/appearance/start controls.
- Rebuilt the result screen around the frozen 3D match scene with `YOU WON` /
  `THE FLY WON`, player vs Fly ID, duration, damage dealt/taken, score, Fight
  Again and Share Result.
- Reworked Science into editorial flow with a real visual pipeline diagram:
  `20 game signals -> artificial encoder -> fixed FlyWire connectome ->`
  `artificial readout -> 14 actions`.

Asset and connectome provenance:

- No external 3D model asset was downloaded. The repo network policy allows
  only specific official read-only download sources; the best apparent
  Drosophila model candidate found was on Sketchfab and requires manual
  license/provenance review before ingestion.
- Two small Zenodo FlyWire derivative files were downloaded for coordinate
  investigation only: `coordinates.mat` and `annotations.mat` from record
  `18555170`. They confirmed coordinate data exists externally but did not
  provide the root-ID ordering needed for safe selected-neuron mapping.
- Current runtime assets are original procedural Three.js geometry documented
  in `docs/VISUAL_ASSETS.md`.
- The client still does not receive verified selected-neuron anatomical
  coordinates, centroids, skeletons, meshes, neuropil labels or Codex spatial
  metadata. The brain panel is therefore intentionally labeled
  `CONNECTOME ACTIVITY MAP`, not anatomical brain.

Representative screenshots:

- `docs/screenshots/v11-watch-wide.png`
- `docs/screenshots/v11-watch-fly-controller.png`
- `docs/screenshots/v11-brain-close.png`
- `docs/screenshots/v11-human-setup.png`
- `docs/screenshots/v11-human-fight.png`
- `docs/screenshots/v11-human-result.png`
- `docs/screenshots/v11-science-pipeline.png`
- `docs/screenshots/v11-mobile-watch.png`

Final verification:

| Check | Result |
|---|---|
| `npx tsc --noEmit -p tsconfig.json` | Pass |
| `npm run test` | Pass — 19/19 |
| `npm run lint` | Pass |
| `npm run build` | Pass; existing Node 22.11.0/Vite version warning remains; Three chunk large-warning remains; CSS 14.47 kB gzip 3.94 kB, app chunk 264.38 kB gzip 83.38 kB, Three chunk 709.73 kB gzip 183.92 kB |
| `node scripts/py.mjs pytest services/brain/tests` | Pass — 96/96, 2 dependency deprecation warnings |
| `node scripts/py.mjs ruff check services/brain scripts` | Pass |
| `node scripts/py.mjs bandit -q -r services -x services/brain/tests` | Pass — warnings only for existing `nosec` comment parsing; no failed tests reported |
| `npm run e2e` | Pass — 4/4 against local web and brain services |
| `npm audit` | Pass — 0 vulnerabilities |
| `node scripts/py.mjs pip_audit` | Pass — no known vulnerabilities found |
| `node scripts/py.mjs scripts.review_project size` | Pass — 1.582 GB total, under 5 GB |
| `node scripts/py.mjs scripts.review_project secrets` | Nonzero with two pre-existing oversized trace JSONL review findings; no new secret-pattern finding reported |
| Playwright screenshot capture against `127.0.0.1:5173` and brain service `127.0.0.1:8000` | Pass; no page or console errors, online brain true, activity updates observed, mobile overflow false |

Honest visual self-score after screenshot inspection:

- Fly asset: 6.5/10 — much more recognizable with eyes, wings, abdomen and
  legs, but still original runtime geometry rather than a high-quality scanned
  or rigged GLB.
- Fly animation: 7/10 — wing, antenna, body and leg/controller animation states
  are readable.
- Controller interaction: 7/10 — deterministic button/stick mapping is visible,
  though a rigged external fly could make leg contact more precise.
- Fighters: 7/10 — no longer debug polygons; stylized mannequins read clearly.
- Arena/environment: 7/10 — physical lab chamber, grid, rails and observation
  wall are present.
- Lighting: 7/10 — key/fill/rim/contact shadows added and verified in screenshots.
- Brain visualization: 7/10 — active paths now dominate over dim structure.
- Fight animation: 7/10 — pose states, impact sparks and camera impulse added.
- Watch composition: 7/10 — unified fight/operator/brain layout; no extra routes.
- Fight setup: 7/10 — quicker and visually alive, still sparse by design.
- Result screen: 7.5/10 — final scene gives the match a payoff.
- Overall screenshot quality: 7/10 — materially better than v0.10, but the
  single biggest remaining gap is replacing the original fly geometry with a
  legally reviewed high-quality Drosophila GLB.
