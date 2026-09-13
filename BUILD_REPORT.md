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
