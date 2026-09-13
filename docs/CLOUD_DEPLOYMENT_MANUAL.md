# Cloud Readiness and Manual Deployment Notes

No cloud resources were contacted or created in this phase.

## Target Shape

- Web service: public frontend.
- Brain/API service: public only where required for browser play and status.
- Research worker: private process with no public endpoint.
- Daily evaluator: scheduled one-shot process.
- Metadata: PostgreSQL-compatible store, later Supabase/Neon.
- Large immutable artifacts: S3-compatible object store, later Cloudflare R2.

The local code now has SQLite metadata and local immutable artifact storage
interfaces that can be replaced by Postgres/S3-compatible implementations.

## Railway

Manual later:

1. Create separate services for web, brain/API, research worker and daily
   evaluator.
2. Set production environment variables from `.env.example`.
3. Give the research worker and daily evaluator no public route.
4. Configure health checks against `/health` for the brain/API service.
5. Attach persistent volumes or configure external metadata/artifact stores
   before allowing worker restarts to matter.

## Supabase or Neon

Manual later:

1. Create a Postgres database.
2. Add a private connection string as a secret, not a committed file.
3. Port `research_registry` schema to migrations.
4. If using Supabase exposed schemas, apply RLS/access decisions deliberately
   before exposing anything through a public Data API.
5. Keep service-role credentials out of browser-visible variables.

## Cloudflare R2

Manual later:

1. Create a private bucket for checkpoints, replays, traces and result bundles.
2. Provide S3-compatible endpoint, access key and secret via environment
   variables.
3. Store immutable artifacts by content hash.
4. Keep canonical graph/checkpoint artifacts read-only to public clients.

## GitHub

Manual later:

1. Confirm repository publication is allowed.
2. Add CI secrets only through GitHub settings.
3. Keep workflows non-deploying until production origin, auth, rate limits,
   backups and cost ceilings are approved.

## Still Required Before Real Production

- Auth/access decision for admin research controls.
- TLS and exact production origins.
- Production CSP/proxy review.
- Non-root isolated workers.
- Read-only canonical graph/checkpoint access.
- Debug global removal verification.
- Dependency, license and secret review.
- Backup/rollback procedure.
- Cost ceiling and abuse monitoring.
