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

## Next best step

Add `.github/workflows/ci.yml` (typecheck + lint + vitest + pytest, no
deploy step) and minimal `Dockerfile`s for `apps/web` and
`services/brain` that read the existing env-driven config — this closes
the deployment-readiness gap without requiring any new application logic,
and does not itself deploy or publish anything.
