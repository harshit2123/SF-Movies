# ADR-0007 — Both halves on Vercel, database baked in at build time

**Status:** Accepted — supersedes [ADR-0005](0005-hosting.md)

## Context

ADR-0005 chose Fly.io for the API and Vercel for the SPA, on the reasoning that
SQLite needs a writable persistent disk and serverless platforms do not provide one.

Two things made that reasoning worth re-examining:

1. **Fly requires a payment card at signup**, even inside the free allowance. For a
   take-home demo that is real friction, and a barrier the reader may simply not clear.
2. **The API never writes.** Every endpoint is read-only; the only writer is the sync
   command. Measured, not assumed — the database is **1.1 MB**, and a `grep` across
   the view and serializer layers finds no `save()`, `create()`, or `delete()`.

The premise of ADR-0005 was that production needs a writable database. It does not.

## Decision

**One Vercel project serves both halves.** The SPA is the static output; the Django
API runs as a serverless function at `/api/*`.

The database is **created and populated during the build**:

```
vercel build
  └─ backend/build.sh
       ├─ migrate
       ├─ sync_film_locations   ← fetches from DataSF
       └─ collectstatic
  └─ npm run build              ← SPA
```

`db.sqlite3` is baked into the deployment bundle and opened **read-only** at runtime.
Vercel's restriction is on *writes*; reading a bundled file is fine.

## Consequences

- **No payment card**, and no second platform or dashboard.
- **Same-origin.** The SPA and API share a domain, so CORS stops applying and
  `VITE_API_BASE_URL` is no longer needed in production.
- **No cold-start database handshake** — the file is local to the function.
- **Refreshing data means redeploying**, not running a command against production.
  For a dataset DataSF republishes every few months, that is an acceptable trade, and
  a redeploy is a single command or a git push.
- **A failed sync fails the build.** `build.sh` runs with `set -e` deliberately:
  shipping an empty database would produce a deployment that reports healthy and
  serves an empty map.

## Alternatives considered

**Fly.io + Vercel (ADR-0005).** Still the right answer if the API needed to write in
production — a real volume, no build-time coupling, and data refreshable without a
deploy. Rejected here for the card requirement, given that nothing writes.

**Render + Vercel.** No card needed. Rejected: the free tier sleeps after inactivity
and the first request afterward takes roughly 50 seconds. A demo reached through a
single link cannot afford that.

**Vercel + a hosted Postgres** (Neon or Supabase, both free-tier). A genuinely
writable production database, and it would restore `pg_trgm` fuzzy search. Rejected
as disproportionate: it reintroduces the database service ADR-0004 removed, to serve
2,214 read-only rows.

**Vercel + Turso** (hosted libSQL, SQLite-compatible, free tier). The closest thing
to "SQLite but writable in serverless". Rejected for the same reason — a network hop
per query, to replace a 1.1 MB local file that is never written to.

## Tradeoffs

- **Gained:** a free, card-free, single-platform deployment; same-origin requests; no
  CORS configuration; the simplest production topology this application can have.
- **Cost:** data freshness is tied to deploys. Documented in the README.
- **Cost:** a serverless function has a cold start of a few hundred milliseconds,
  against a warm Fly machine's zero. Far below Render's ~50 seconds, and acceptable.
- **Cost:** the build now depends on DataSF being reachable. A build during a DataSF
  outage fails rather than silently shipping stale or empty data — the correct
  failure mode, but a real coupling worth naming.

## Note

ADR-0005 is left in place rather than deleted. It records why Fly was chosen and what
its tradeoffs were; this ADR records why that reasoning stopped applying once the
read-only nature of the API was established. The `Dockerfile` and `fly.toml` remain
in the repository and still work, so the Fly path stays available.
