# ADR-0004 — SQLite over Postgres; substring search over trigram

**Status:** Accepted

## Context

Two coupled choices: which database, and how autocomplete search works. They are coupled
because the strongest argument for Postgres here was `pg_trgm` — typo-tolerant fuzzy
search via a GIN trigram index.

Scale, from ADR-0001: **350 films, 2,214 locations, ~1.5 MB.** The entire dataset fits
comfortably in memory.

## Decision

**SQLite**, stored on a Fly.io persistent volume in production.

**Search via `icontains`** — case-insensitive substring match on film title, debounced
250 ms client-side, results capped at 10.

## Alternatives considered

**Postgres + `pg_trgm`.** Typo tolerance is a genuinely nicer demo: `godfathr` still
finds *The Godfather*. Rejected on cost/benefit — it requires a running database service
locally (or Docker), a managed instance in production, connection configuration, and an
extension migration. That is real setup and one more thing to fail on deploy day, to add
fuzzy matching across **350 titles**.

**Postgres full-text search (`tsvector`).** No extension needed, but weaker than trigram
at exactly the thing autocomplete needs — prefix and partial-word matching as the user
types. It would have added Postgres's cost without trigram's benefit.

**In-memory fuzzy match (`difflib`) over SQLite.** Typo tolerance without Postgres; 350
strings is trivial to scan per request. Rejected as the kind of clever-but-surprising
code that is harder to justify than either clean alternative. Kept as a documented
upgrade path.

## Tradeoffs

- **Gained:** zero database setup. `git clone`, `pip install`, `migrate`, `sync`, run.
  No Docker, no service to provision, no connection pooling, no cold-start DB handshake.
- **Cost:** no typo tolerance. `godfath` finds *The Godfather*; `godfathr` does not.
  Mitigated because search is autocomplete-style — users see suggestions from the third
  character, so typos are corrected visually before they matter.
- **Cost:** single-writer concurrency. Irrelevant: the only writer is a periodic
  management command, and the API is read-only.
- **Cost:** `icontains` is an unindexed table scan. At 350 rows this is sub-millisecond.

## Upgrade path

If the dataset grew by an order of magnitude, or fuzzy matching became a requirement:
swap `DATABASES` to Postgres, add `django.contrib.postgres`, run a migration creating a
`GinIndex(fields=["title"], opclasses=["gin_trgm_ops"])`, and replace the `icontains`
filter in `films/views.py` with `TrigramSimilarity`. The change is confined to the
settings module and one queryset — the API contract does not move.
