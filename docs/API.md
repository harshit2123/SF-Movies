# API Reference

Read-only JSON API over the DataSF Film Locations dataset.

**Live:** `https://sf-on-film.vercel.app/api`
**Local:** `http://localhost:8000/api`

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
  "count": 352,
  "next": "https://\u2026/api/films/?page=2",
  "previous": null,
  "facets": {
    "decades": [
      1910,
      1920,
      "\u2026",
      2020
    ],
    "neighborhoods": [
      "Bayview Hunters Point",
      "Bernal Heights",
      "\u2026"
    ]
  },
  "results": [
    {
      "slug": "milk-2008",
      "title": "Milk",
      "release_year": 2008,
      "director": "Gus Van Sant",
      "actors": [
        "Sean Penn",
        "Emile Hirsch"
      ],
      "location_count": 12,
      "mappable_count": 12
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
  {
    "slug": "milk-2008",
    "title": "Milk",
    "release_year": 2008,
    "location_count": 12
  },
  {
    "slug": "the-times-of-harvey-milk-1984",
    "title": "The Times of Harvey Milk",
    "release_year": 1984,
    "location_count": 1
  }
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
  "actors": [
    "Sean Penn",
    "Emile Hirsch"
  ],
  "locations": [
    {
      "id": 523,
      "location_text": "29th and Dolores Street",
      "latitude": 37.7437303,
      "longitude": -122.4246468,
      "is_mappable": true,
      "neighborhood": "Noe Valley",
      "supervisor_district": "8",
      "fun_facts": ""
    },
    "\u2026 11 more"
  ]
}
```

Returns `404` for an unknown slug.

---

## `GET /api/locations/`

Map markers. Returns only mappable locations (ADR-0001) — the 87 rows without
coordinates are excluded here but remain visible via film detail.

| Query param | Type | Description |
|---|---|---|
| `film` | string | Film slug — used to draw a single film's route |
| `bbox` | string | `min_lng,min_lat,max_lng,max_lat` viewport filter |
| `neighborhood` | string | Exact match |
| `decade` | int | Filter by decade |
| `search` | string | Same matching as `/api/films/` |

Not paginated — the full mappable set is 2,120 points, and the map needs them all for
clustering.

```json
[
  {
    "id": 523,
    "film_slug": "milk-2008",
    "film_title": "Milk",
    "release_year": 2008,
    "location_text": "29th and Dolores Street",
    "latitude": 37.7437303,
    "longitude": -122.4246468,
    "neighborhood": "Noe Valley"
  }
]
```

---

## `GET /api/locations/nearby/`

Locations within a radius of a point, nearest first.

The bundled SPA does not call this — a "filmed near me" control was removed from the
interface because most visitors to a San Francisco map are not in San Francisco
([ADR-0008](decisions/0008-no-geolocation.md)). The endpoint remains for consumers
that do know their user's position.

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
    "id": 135,
    "film_slug": "after-the-thin-man-1936",
    "film_title": "After the Thin Man",
    "release_year": 1936,
    "location_text": "Coit Tower",
    "latitude": 37.8023949,
    "longitude": -122.4058222,
    "neighborhood": "North Beach",
    "distance_km": 0.0
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
  "film_count": 352,
  "location_count": 2207,
  "mappable_count": 2120,
  "last_sync": "2026-02-20T16:37:46Z"
}
```

Returns `503` with `"status": "degraded"` when the database is unreachable or empty.

---

## Notes for consumers

- **Caching.** Responses are safe to cache; the underlying data changes only when the
  sync command runs (ADR-0003). The SPA uses stale-while-revalidate.
- **CORS.** In production the API and the SPA share an origin (ADR-0007), so CORS
  does not apply. It is configured for local development, where Vite runs on
  `:5173` and Django on `:8000`, via `CORS_ALLOWED_ORIGINS`.
- **Rate limiting.** None (ADR-0006). Add before any real production use.
- **Authentication.** None. Every endpoint is public and read-only; the only
  writer is the sync command, which runs at build time.
