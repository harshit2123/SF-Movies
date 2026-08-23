# ADR-0003 — No WebSockets; batch ingestion over live proxy

**Status:** Accepted

## Context

Two related questions, decided together because they share one root cause: how fresh is
this data, and who pushes changes?

The dataset is a municipal film-permit archive spanning 1915–2025. `data_as_of` on the
sampled rows is a single timestamp across the whole set — DataSF republishes it in
batches, not as a stream. Nothing about a 1927 filming location changes while a user has
the map open.

## Decision

**No WebSockets. No Django Channels, no ASGI server, no Redis channel layer.**

Data reaches the database through a scheduled batch pull:

```
DataSF Socrata API
      │  manage.py sync_film_locations
      ▼
SocrataClient (timeout, retry+backoff, pagination)
      │  idempotent upsert on content hash
      ▼
   SQLite  ──►  DRF read-only API  ──►  SPA
```

The API is plain HTTP `GET`. The frontend caches through TanStack Query with
stale-while-revalidate.

## Alternatives considered

**WebSockets for live map updates.** The reflexive "real-time" feature. Rejected because
there is no event source: the server has nothing to push. A socket would deliver silence,
while adding an ASGI deployment target, a channel layer, connection lifecycle handling,
and reconnect-with-backoff logic on the client. Complexity with a zero-sized payoff.

**WebSockets for ingestion progress.** A real use case — streaming sync progress to an
admin view. Rejected on proportion: the sync finishes in seconds on a 1.5 MB payload, so
the progress bar would be shorter-lived than the connection setup. The management command
already prints a run summary to stdout.

**Live proxy to Socrata per request.** No local database; Django forwards and caches each
call. Rejected: it puts a third-party service on the critical path of every page load,
inherits their rate limits and downtime, and makes indexed filtering and search impossible.
The dataset is 1.5 MB — small enough that a local copy is strictly better.

**Server-Sent Events.** Lighter than WebSockets for one-directional push, and correct if
there were something to push. Same rejection as above: no event source.

## Tradeoffs

- **Gained:** the backend is a WSGI application with no persistent connections and no
  broker. Simpler to deploy, reason about, and test. Responses are cacheable.
- **Cost:** data is as fresh as the last sync run. For a dataset republished in monthly-ish
  batches, this is not a real limitation.
- **Cost:** no live multi-user features (shared cursors, presence). None are in scope.

## Note

This ADR exists to record a **rejection**. The absence of WebSockets here is a deliberate
engineering choice, not an oversight — and choosing not to build the impressive-sounding
thing is the decision worth documenting.
