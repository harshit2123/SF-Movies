# API Reference

Read-only JSON API over the DataSF Film Locations dataset.

**Base URL (local):** `http://localhost:8000/api`

All responses are `application/json`. All endpoints are `GET` and unauthenticated
(ADR-0006). Errors use DRF's default shape: `{"detail": "..."}` with an accurate status
code.

---

## `GET /api/films/`

Paginated list of films. One film groups many filming locations.

| Query param | Type | Description |
|---|---|---|
| `search` | string | Case-insensitive substring match on title, director, and actors |
| `decade` | int | Filter by decade, e.g. `1970` matches 1970–1979 |
| `neighborhood` | string | Exact match on `analysis_neighborhood` |
| `person` | string | Substring match across director, writer, and actors |
| `page` | int | 1-indexed |
| `page_size` | int | Default 20, max 100 |

```json
{
  "count": 350,
  "next": "http://localhost:8000/api/films/?page=2",
  "previous": null,
  "facets": {
    "decades": [1910, 1920, 1930, 1940, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020],
    "neighborhoods": ["Bayview Hunters Point", "Chinatown", "..."]
  },
  "results": [
    {
      "slug": "milk-2008",
      "title": "Milk",
      "release_year": 2008,
      "director": "Gus Van Sant",
      "actors": ["Sean Penn", "Emile Hirsch"],
      "location_count": 24,
      "mappable_count": 24
    }
  ]
}
```

Facets ship with the response rather than requiring a second round trip (ADR-0006).

---

## `GET /api/films/autocomplete/?q=`

Lightweight endpoint powering the search box. Capped at 10 results, no pagination.
Returns an empty list for queries shorter than 2 characters.

Matching is case-insensitive substring (ADR-0004) — `godfath` matches *The Godfather*,
`godfathr` does not.

```json
[
  { "slug": "milk-2008", "title": "Milk", "release_year": 2008, "location_count": 24 }
]
```

---

## `GET /api/films/{slug}/`

Full detail for one film, including every location.

```json
{
  "slug": "milk-2008",
  "title": "Milk",
  "release_year": 2008,
  "director": "Gus Van Sant",
  "writer": "Dustin Lance Black",
  "production_company": "Focus Features",
  "distributor": "Focus Features",
  "actors": ["Sean Penn", "Emile Hirsch"],
  "locations": [
    {
      "id": 1,
      "location_text": "El Camino Del Mar",
      "latitude": 37.7857806,
      "longitude": -122.4962354,
      "is_mappable": true,
      "neighborhood": "Lincoln Park",
      "supervisor_district": "1",
      "fun_facts": null
    }
  ]
}
```

Returns `404` for an unknown slug.

---

## `GET /api/locations/`

Map markers. Returns only mappable locations (ADR-0001) — the 86 rows without
coordinates are excluded here but remain visible via film detail.

| Query param | Type | Description |
|---|---|---|
| `film` | string | Film slug — used to draw a single film's route |
| `bbox` | string | `min_lng,min_lat,max_lng,max_lat` viewport filter |
| `neighborhood` | string | Exact match |
| `decade` | int | Filter by decade |
| `search` | string | Same matching as `/api/films/` |

Not paginated — the full mappable set is 2,128 points, and the map needs them all for
clustering.

```json
[
  {
    "id": 1,
    "film_slug": "milk-2008",
    "film_title": "Milk",
    "release_year": 2008,
    "location_text": "El Camino Del Mar",
    "latitude": 37.7857806,
    "longitude": -122.4962354,
    "neighborhood": "Lincoln Park"
  }
]
```

---

## `GET /api/locations/nearby/`

Locations within a radius of a point, nearest first. Backs the "filmed near me" feature.

| Query param | Type | Required | Description |
|---|---|---|---|
| `lat` | float | yes | −90 to 90 |
| `lng` | float | yes | −180 to 180 |
| `radius_km` | float | no | Default 1.0, max 20.0 |
| `limit` | int | no | Default 50, max 200 |

Distance uses the Haversine formula with a bounding-box prefilter (ADR-0006). Returns
`400` when `lat`/`lng` are missing or out of range.

```json
[
  {
    "id": 42,
    "film_slug": "chance-season-2-2017",
    "film_title": "Chance Season 2",
    "location_text": "Coit Tower",
    "latitude": 37.8023949,
    "longitude": -122.4058222,
    "distance_km": 0.08
  }
]
```

---

## `GET /api/health/`

Liveness and data-freshness check.

```json
{
  "status": "ok",
  "database": "ok",
  "film_count": 350,
  "location_count": 2214,
  "mappable_count": 2128,
  "last_sync": "2026-02-20T16:37:46Z"
}
```

Returns `503` with `"status": "degraded"` when the database is unreachable or empty.

---

## Notes for consumers

- **Caching.** Responses are safe to cache; the underlying data changes only when the
  sync command runs (ADR-0003). The SPA uses stale-while-revalidate.
- **CORS.** Allowed origins come from `CORS_ALLOWED_ORIGINS` (ADR-0005).
- **Rate limiting.** None (ADR-0006). Add before public production use.
