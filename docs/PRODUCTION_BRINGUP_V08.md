# Flyweight v0.8 Production Bring-Up

No cloud provider was contacted and no remote was configured, pushed to, or
deployed during this phase.

## Roles

The production entrypoints are split by `FLYWEIGHT_SERVICE_ROLE`:

- `WEB`: `npm run prod:web`
- `BRAIN_API`: `npm run prod:brain`
- `RESEARCH_WORKER`: `npm run prod:research`
- `DAILY_EVALUATOR`: `npm run prod:daily`

Each role validates its expected production environment before starting. Web
and Brain/API may expose public routes later; research worker and daily
evaluator are private worker processes.

## Required Environment

Use `.env.example` as the names-only contract. Secrets stay in the target
platform, never in committed files.

- Web: `PUBLIC_APP_URL`, `BRAIN_PUBLIC_URL`, `BRAIN_UPSTREAM`,
  `FLYWEIGHT_PUBLIC_ORIGINS`, `FLYWEIGHT_ALLOWED_HOSTS`.
- Brain/API: `DATABASE_URL`, `BRAIN_PUBLIC_URL`, exact origins/hosts, optional
  `FLYWEIGHT_RESEARCH_DB` for local/volume SQLite compatibility, and a prepared
  `data/processed/flywire.*` plus validated `checkpoints/canonical.json`.
- Research worker and daily evaluator: `DATABASE_URL`, compute-governor values,
  and optional S3/R2 artifact variables when `ARTIFACT_BACKEND=s3`.
- R2/S3: `S3_ENDPOINT`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`,
  `S3_SECRET_ACCESS_KEY`.

## Data And Metadata

- SQLite remains the local development registry.
- `services/brain/migrations/001_research_platform.sql` defines the
  PostgreSQL/Supabase-compatible schema for experiments, runs, candidates,
  champions, canonical champion pointer, evaluations, ladder certifications,
  topology controls, daily reports, human challenge sessions/matches,
  leaderboard entries, worker leases/status, and artifact metadata.
- `services/brain/postgres_registry.py` is a parameterized, optional adapter.
  Unit tests use a fake connection; no live database is required.
- `services/brain/artifact_store.py` now includes a small S3-compatible
  content-addressed store for R2-style immutable objects. Tests inject a fake
  transport; no network call is made.

## Compute Governor

`services/brain/production.py` validates bounded CPU-only settings:

- `MAX_DAILY_EXPERIMENTS`
- `MAX_CONCURRENT_EXPERIMENTS`
- `MAX_GENERATIONS_PER_EXPERIMENT`
- `MAX_POPULATION`
- `MAX_EXPERIMENT_RUNTIME`
- `MAX_RETRIES`
- `MAX_FAILURES`
- `MAX_STORAGE_BYTES`
- `MAX_WORKERS`
- `DAILY_CPU_TIME_BUDGET`

The research worker rejects selected jobs that exceed the configured
generation, population, or runtime bounds and reports `budget_exhausted`.

## Evidence Batch Before Cloud Work

The addendum-required bounded topology batch was run locally:

```powershell
node scripts/py.mjs services.brain.topology_batch --synthetic --db .runtime/v08_topology_batch.sqlite --seeds 9401,9402 --generations 1 --population 4 --seconds 6 --heldout-matches 6 --project-day 6 --report-date 2026-09-14
```

Persisted counts: 7 topology condition records, 13 evaluation records, 8
trained candidates. Summary is committed at
`docs/results/v08_topology_batch_2026-09-14.json`.

This was synthetic-fixture evidence, not real FlyWire production evidence and
not a superiority claim. `DIRECT_BASELINE` is recorded honestly as
`planned_interface_only`.

## Burn-In

Local burn-in command:

```powershell
node scripts/py.mjs services.brain.burn_in --synthetic --db .runtime/v08_burn_in_final.sqlite --date 2026-09-14
```

Result: stale lease recovery succeeded, one research cycle completed, daily
evaluator wrote a report for 2026-09-15, the second daily evaluator run was
idempotent, and dashboard state was present.

## Still Required Before Real Production

- Real FlyWire processed graph artifact and canonical champion pointer must be
  present in the production image/volume; production refuses synthetic fallback.
- Docker images were edited but not built on this machine because Docker is not
  installed.
- No live Supabase/Postgres, Railway, Cloudflare R2, GitHub remote, CI secret,
  or deployment was touched.
- Public release still requires auth decisions, TLS/origin/CSP/proxy review,
  backups/rollback, cost ceilings, abuse monitoring, and a final dependency,
  license, and secret review.
