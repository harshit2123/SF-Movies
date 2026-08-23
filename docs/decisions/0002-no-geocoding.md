# ADR-0002 — No geocoding pipeline

**Status:** Accepted

## Context

The obvious design for "map the film locations" is:

```
fetch rows → parse address text → geocode each address → cache → store lat/lng
```

That shape assumes the source has no coordinates. ADR-0001 establishes it does: 2,128
of 2,214 rows ship `latitude`, `longitude`, and a GeoJSON `point`.

That leaves 86 rows. Of those, 54 have no `locations` text whatsoever — there is nothing
to geocode. The genuinely addressable gap is **~32 rows out of 2,214: 1.4%**.

## Decision

**Do not geocode.** No Nominatim, no Google Geocoding, no geocode cache table, no
rate-limit handling for a geocoding provider.

## Alternatives considered

**Nominatim (OpenStreetMap).** Free, no API key. The usual pick for this exercise.
Rejected: it would exist to resolve ~32 rows, while introducing a 1 req/sec rate limit,
a cache table and its invalidation rules, retry/backoff for a second external service,
and a required `User-Agent` policy. Meaningful infrastructure for a 1.4% gain.

**Google Geocoding API.** Better hit rate on messy SF strings like
`"Geary from 22nd Ave to Arguello"`. Rejected: requires a billing-enabled API key for a
public demo repository, which is a credential-management burden disproportionate to
32 rows.

**Optional opt-in backfill flag.** A `--geocode-missing` flag, off by default. Genuinely
tempting — it demonstrates outgoing-call resilience without making the demo depend on it.
Rejected on scope grounds: `SocrataClient` already demonstrates timeouts, retry with
backoff, and pagination against a real external service. A second HTTP client would
duplicate that evidence rather than extend it.

## Tradeoffs

- **Gained:** one fewer external dependency, one fewer failure mode, one fewer rate
  limit, and no cache staleness question. Ingestion is a single network hop and finishes
  in seconds.
- **Cost:** 32 rows with usable address text stay off the map. They remain searchable and
  visible in film detail, flagged via `is_mappable`.
- **Cost:** correctness is delegated to DataSF's own geocoding. Acceptable — it is the
  authoritative publisher of this dataset.

## Fallback

If DataSF stops publishing coordinates, the ingestion mapper is the single place that
reads them (`films/services/mapper.py`). A geocoding step would slot in there, behind
the same `SocrataClient` retry/timeout conventions, writing to the existing
`latitude` / `longitude` / `is_mappable` fields. No model migration and no API change
would be required.
