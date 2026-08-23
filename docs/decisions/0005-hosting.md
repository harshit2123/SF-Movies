# ADR-0005 — Fly.io for the API, Vercel for the SPA

**Status:** Accepted

## Context

The challenge requires the result to be hosted. Two constraints shaped the choice:

1. **SQLite needs a writable, persistent filesystem** (ADR-0004). The sync command writes
   to the database file, and those writes must survive restarts.
2. **A reviewer clicks the link once.** Whatever they hit first is the impression the
   project makes. A cold start measured in tens of seconds reads as "broken" before
   anything is evaluated.

## Decision

- **API:** Fly.io — Django on a shared-cpu machine with a persistent volume mounted for
  the SQLite file.
- **Frontend:** Vercel — static Vite build on the CDN.

## Alternatives considered

**Both on Vercel, SQLite baked in at build time.** Attractive: one platform, one domain,
no CORS at all. The sync command would run during `vercel build`, writing `db.sqlite3`
into the deployment bundle, with the runtime reading it read-only — which works, since
Vercel's filesystem restriction is on *writes*.

Rejected because it inverts the data-refresh model: updating data requires a full
redeploy rather than running the management command. That weakens the thing the ingestion
pipeline is meant to demonstrate — a re-runnable, idempotent sync against a live external
API. Worth recording as genuinely viable, and the right answer for a purely static build.

**Render + Vercel.** The most common pick and the simplest deploy UX. Rejected: the free
tier sleeps after inactivity, and the first request afterward takes roughly 50 seconds.
For a demo whose entire audience arrives via one cold link, that is the wrong failure mode.

**Railway + Vercel.** No sleeping, very smooth deploys. Rejected: the free allowance is
credit- and time-limited, so the demo link risks going dark weeks after submission —
precisely when someone might revisit it.

**Vercel + Neon Postgres.** Would restore `pg_trgm` fuzzy search and give a genuinely
writable production database via the Vercel Marketplace. Rejected together with ADR-0004:
it reintroduces the database service that decision deliberately removed.

## Tradeoffs

- **Gained:** no cold-start penalty on the API. A persistent volume means the production
  sync command behaves exactly as it does locally.
- **Cost:** two platforms and two dashboards instead of one.
- **Cost:** cross-origin requests, so `CORS_ALLOWED_ORIGINS` must name the deployed Vercel
  origin. Verified against the live origin during deployment, not just against localhost.
- **Cost:** a single Fly machine is a single point of failure with no redundancy.
  Appropriate for a demo; a managed database and multiple instances would be the
  production answer.

## Note

The frontend reads the API base URL from `VITE_API_BASE_URL` at build time, so pointing
the SPA at a different backend requires no code change.
