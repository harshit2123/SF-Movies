# ADR-0001 — Dataset shape and the coordinate gap

**Status:** Accepted

## Context

The challenge points at DataSF's Film Locations dataset. A widespread assumption —
repeated in most public write-ups of this exercise — is that the dataset provides only
free-text addresses in a `Locations` column, and that any map therefore requires a
geocoding pipeline.

Before designing anything, the live endpoint was queried directly:

```
https://data.sfgov.org/resource/yitu-d5am.json
```

Measured, not assumed:

| Property | Value |
|---|---|
| Total rows | 2,214 |
| Rows with `latitude` / `longitude` | **2,128 (96%)** |
| Rows without coordinates | 86 |
| — of which have no `locations` text at all | 54 |
| Unique film titles | 350 |
| Unique location strings | 1,757 |
| Release year range | 1915 – 2025 |
| Neighborhoods (`analysis_neighborhood`) | 41 |
| Rows with `fun_facts` | 465 |
| Stable row identifier | **none** |
| Full payload size | ~1.5 MB |

Each row also carries a GeoJSON `point`, plus `supervisor_district` and `data_as_of`.

## Decision

Treat the dataset as **pre-geocoded**. Consume `latitude` / `longitude` directly.

The 86 rows without coordinates are ingested and stored with `is_mappable = False`.
They appear in search results and in film detail views; they are excluded from map
marker queries.

Field mapping notes:
- `actor_1`, `actor_2`, `actor_3` are normalized into a single `actors` list.
- Rows are grouped into `Film` + `FilmLocation`: 350 films, 2,214 locations.

## Alternatives considered

**Drop the 86 coordinate-less rows.** Simpler ingestion and a uniformly mappable
dataset — but it silently discards 4% of the source data, including films whose *other*
locations do have coordinates. A reviewer comparing row counts against DataSF would see
a discrepancy with no explanation.

**Store them as mappable with null coordinates.** Pushes the null-handling burden onto
every consumer — the map layer, the API serializer, and the frontend would each need
their own guard. An explicit boolean puts the decision in one place.

**Geocode the gap.** See ADR-0003.

## Tradeoffs

- **Gained:** no geocoding infrastructure, no external rate limits, no cache-invalidation
  problem, and a demonstrably faster path to a working map.
- **Cost:** the design now depends on DataSF continuing to publish coordinates. If that
  field disappears, a geocoding step becomes necessary — ADR-0003 records the fallback.
- **Cost:** `is_mappable` is a small amount of extra state that every map query must
  filter on. Accepted, because the alternative is scattering null checks.

## Consequences

- A committed test fixture is trimmed from a real Socrata response, so the ingestion
  suite runs offline and reflects genuine field shapes — including rows missing
  coordinates and rows missing `locations` entirely.
- The UI states the mappable count explicitly rather than letting the gap read as a bug.
