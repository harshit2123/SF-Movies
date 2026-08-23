# ADR-0006 — Deliberate scope cuts

**Status:** Accepted

## Context

The evaluation criteria reward logging, error handling, testing, environment
configuration, and documentation. There is a failure mode where a demo project answers
each criterion with its heaviest possible implementation — structured-logging libraries,
custom error envelopes, generated API specs, request tracing — and ends up with more
infrastructure than product.

This is a prototype. The cuts below are recorded so their absence reads as a decision
rather than a gap.

## Decisions

**No OpenAPI schema generation (`drf-spectacular`).**
The challenge asks for machine-readable API documentation on the *back-end track*, where
the API is the deliverable. This is the full-stack track: the SPA is the client, and it is
typed against hand-written TypeScript interfaces. `docs/API.md` documents every endpoint
for a human. *Add when a second, unknown consumer needs to generate a client.*

**No `structlog`.**
Django's stdlib `LOGGING` configuration produces adequately structured output in ~20 lines
of settings, with no dependency. Ingestion logs a run summary; request errors log with
context. *Add when logs are shipped to a system that parses JSON fields.*

**No custom exception handler or error envelope.**
DRF already returns consistent JSON error bodies with correct status codes. Wrapping them
in `{"error": {"code", "message", "details"}}` would be re-formatting for its own sake.
*Add when a client contractually depends on a stable machine-readable error code.*

**No request-ID middleware.**
Request correlation solves log-tracing across distributed services. There is one service.
*Add on the second service.*

**No rate limiting / throttling.**
The API is read-only, unauthenticated, and serves a 350-row dataset from a demo instance.
There is no abuse surface worth the configuration. *Add before any public production use —
DRF's `AnonRateThrottle` on the autocomplete endpoint is roughly four lines.*

**No split settings modules.**
A single `settings.py` reads environment variables with sane defaults. A
`base/dev/prod/test` package for one deployment target is indirection without benefit.
*Add on the second deployment environment.*

**No Celery / Redis / cron.**
Ingestion is one command against a 1.5 MB payload that finishes in seconds, on a dataset
republished in batches. A broker, a worker, and a scheduler are three services for one
occasional job. The README documents the crontab line for anyone who wants it scheduled.

**No frontend unit tests.**
Backend tests are kept in full — they cover the ingestion client's retry and timeout
behavior, upsert idempotency, and every endpoint. Frontend testing effort would go into
asserting that Leaflet renders markers, which is low-signal relative to its cost.
*Add Playwright end-to-end coverage before this becomes a product; it would catch more
than component-level assertions.*

**No `/api/meta/` facet endpoint.**
Facet values are 41 neighborhoods and 11 decades, and they change when DataSF republishes.
They ship with the films response rather than requiring a second round trip.

## Tradeoffs

- **Gained:** a smaller dependency surface, a faster path to a working demo, and a
  codebase where every file present has a reason to be.
- **Cost:** several of these would be genuinely required in production. Each is listed
  above with its specific trigger condition, so the upgrade path is explicit rather than
  rediscovered later.

## What was deliberately **not** cut

`SocrataClient`'s timeout, retry-with-backoff, and pagination handling; content-hash
upsert idempotency; the backend test suite; `.env` configuration with startup validation;
and this decision log. These are the load-bearing parts — cutting them would remove the
engineering the project is meant to show.
