# SF on Film

A map of where films were shot in San Francisco, built from the City's public
permit records. Search by title, director, or actor; filter by decade or
neighborhood; select a film to see its shooting locations drawn as a route.

**▶ Live: https://sf-on-film-15fbku0f3-harshit2123s-projects.vercel.app**

Try `bullitt`, `vertigo`, or `eastwood`. Zoom past street level to see film names
on the map.

**Data:** [DataSF — Film Locations in San Francisco](https://data.sfgov.org/Culture-and-Recreation/Film-Locations-in-San-Francisco/yitu-d5am)
· 2,214 rows · 352 films · 1915–2025

---

## Architecture

```
DataSF Socrata API
        │  scheduled batch pull
        ▼
manage.py sync_film_locations
        │  SocrataClient — timeout, retry + backoff, pagination
        │  mapper — normalize rows
        │  ingest — idempotent upsert on content hash
        ▼
     SQLite
        │
        ▼
   Django + DRF  ── read-only JSON API
        │  HTTP
        ▼
React + TypeScript SPA  ── TanStack Query · Leaflet · URL-as-state
```

Layers are kept strictly separate, and each is testable alone:

| Layer | Location | Knows about |
|---|---|---|
| HTTP client | `films/services/socrata.py` | Socrata only. Returns plain dicts |
| Mapping | `films/services/mapper.py` | Row shapes. No database, no HTTP |
| Ingestion | `films/services/ingest.py` | Models. No HTTP |
| API | `films/views.py`, `serializers.py` | Requests and responses. Never calls DataSF |

The API never makes an outbound call. Data arrives only through the sync command.

```
├── api/index.py           Vercel entrypoint — exposes the WSGI app
├── build.sh               build: migrate → sync from DataSF → build SPA
├── backend/
│   ├── config/            settings, URLs, WSGI
│   └── films/
│       ├── models.py      Film, FilmLocation
│       ├── views.py       read-only endpoints
│       ├── serializers.py three payload shapes: list, detail, marker
│       ├── services/      socrata · mapper · ingest
│       ├── management/    sync_film_locations
│       └── tests/         100 tests, fixture trimmed from real data
├── frontend/src/
│   ├── features/          map · search · filters · film-detail
│   ├── hooks/             url-state · debounce · geolocation
│   ├── lib/               typed API client, query hooks
│   └── styles/            design tokens
└── docs/                  API reference, deployment, 7 ADRs
```

---

## Running it

**Backend** (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate
python manage.py sync_film_locations      # pulls ~2,200 rows, takes ~4s
python manage.py runserver
```

**Frontend** (Node 20+):

```bash
cd frontend
npm install
cp .env.example .env
npm run dev                                # http://localhost:5173
```

**Tests:**

```bash
cd backend && pytest                        # 100 tests, 97% coverage, no network
cd frontend && npx tsc --noEmit             # type check
```

---

## The sync command

```bash
python manage.py sync_film_locations              # fetch and upsert
python manage.py sync_film_locations --dry-run    # full write path, rolled back
python manage.py sync_film_locations --limit 50   # smoke test
```

Safe to re-run. Identity is derived from row content, so a second run against
unchanged data reports nothing changed:

```
  rows fetched        2214
  films               +0 created, 0 updated
  locations           +0 created, 0 updated, 2207 unchanged
  duplicate rows      7 (same identity, conflicting detail upstream)

Already up to date — nothing changed.
```

Scheduling is left to the host (see [ADR-0006](docs/decisions/0006-scope-cuts.md)):

```cron
0 3 * * * cd /app && python manage.py sync_film_locations >> /var/log/sync.log 2>&1
```

---

## API

Full reference: **[docs/API.md](docs/API.md)**

| Endpoint | Purpose |
|---|---|
| `GET /api/films/` | Paginated list. `?search=` `?decade=` `?neighborhood=` `?person=` |
| `GET /api/films/autocomplete/?q=` | Search suggestions, capped at 10 |
| `GET /api/films/{slug}/` | Detail with all locations |
| `GET /api/locations/` | Map markers. `?film=` `?bbox=` |
| `GET /api/health/` | Liveness and data freshness |

```bash
curl "localhost:8000/api/films/autocomplete/?q=bulli"
curl "localhost:8000/api/locations/?film=vertigo-1958"
```

---

## Deploying

Full walkthrough: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

One Vercel project serves both halves — free, no payment card, about 10 minutes:

```bash
npm i -g vercel && vercel login
vercel --prod                    # from the repository root
```

The database is created and loaded from DataSF during the build, then baked into
the deployment and read at runtime. That works because the API never writes: the
only writer is the sync command, which runs at build time ([ADR-0007](docs/decisions/0007-single-vercel-deployment.md)).
Refreshing data is therefore a redeploy.

---

## Decisions

Every meaningful choice is recorded in **[docs/decisions/](docs/decisions/)** as
Context → Decision → Alternatives → Tradeoffs, written in the same commit as the
code it justifies.

| ADR | Decision |
|---|---|
| [0001](docs/decisions/0001-dataset-shape.md) | Dataset shape — coordinates are present upstream; the 86-row gap |
| [0002](docs/decisions/0002-no-geocoding.md) | **No geocoding** — why the usual Nominatim step is unnecessary |
| [0003](docs/decisions/0003-no-websockets.md) | **No WebSockets** — batch data, HTTP GET is correct |
| [0004](docs/decisions/0004-sqlite-and-search.md) | SQLite over Postgres; substring search over trigram |
| [0005](docs/decisions/0005-hosting.md) | Fly.io for the API, Vercel for the SPA — *superseded by 0007* |
| [0006](docs/decisions/0006-scope-cuts.md) | Deliberate scope cuts, each with its trigger to revisit |
| [0007](docs/decisions/0007-single-vercel-deployment.md) | **One Vercel project**, database baked in at build time |
| [0008](docs/decisions/0008-no-geolocation.md) | **No geolocation** — removed after building it |

Two are worth reading first, because both record a **rejection**:

- **No geocoding.** Most implementations of this exercise build a Nominatim
  pipeline, on the assumption that the dataset carries only free-text addresses.
  Querying the live endpoint first showed it already publishes coordinates for
  2,128 of 2,214 rows. That removed the geocoder, its rate limit, its cache, and
  what would have been the project's highest-risk component.
- **No WebSockets.** The data is a batch snapshot of a permit archive spanning
  1915–2025. Nothing pushes. A socket would add an ASGI server and a channel
  layer to deliver silence.

---

## Data quality

The source is real municipal data and behaves like it. Three cases are handled
explicitly rather than papered over:

**86 source rows have no coordinates** (54 have no location text at all), and one
more publishes coordinates outside San Francisco, which the mapper's bounding-box
check rejects rather than plotting a marker near Monterey. All 87 are ingested with
`is_mappable=False`: searchable and visible in film detail, absent from the map.
Dropping them would silently lose 4% of the dataset.

**The source contradicts itself.** `summertime-2015` reports five different
distributors across its rows; two distinct films share the slug
`golden-gate-1994`. Ingestion applies first-write-wins per run, so the result is
deterministic — without it, every sync reported phantom updates forever.

**There is no stable row id.** Identity is `sha256(title|year|location)`, which is
what makes the upsert idempotent. Seven source rows collapse to identities already
seen; they are counted and reported rather than silently dropped.

This is why the published and stored counts differ — 2,214 source rows become
2,207 stored locations, and 350 distinct titles become 352 films once slugs
disambiguate two title-and-year collisions.
[ADR-0001](docs/decisions/0001-dataset-shape.md) reconciles both figures.

---

## Testing

100 tests, 97% coverage. **No test touches the network** —
the Socrata fixture is trimmed from a real response and includes rows with and
without coordinates, a multi-location film, and rows carrying `fun_facts`.

Coverage worth noting:

- **Outgoing calls** — retry on 5xx/429/timeout/connection error, no retry on 4xx,
  `Retry-After` honored and capped, pagination offsets, malformed JSON
- **Idempotency** — re-runs create and update nothing; the contradiction case is a
  named regression test
- **Three bugs the tests caught**, each with regression coverage: naive-vs-aware
  timestamps silently breaking idempotency, a default `Meta.ordering` defeating
  `DISTINCT` on the neighborhoods facet (2,063 entries instead of 40), and
  `load_dotenv` overriding platform-injected secrets, which also made the
  missing-secret guard unreachable

Two more were only found by running the thing — worth naming, because no unit test
would have caught either:

- **SQLite could not open a read-only database.** The deployed API returned 503
  with `unable to open database file` while the file was demonstrably present.
  SQLite creates a journal beside the database even to read it, which a read-only
  filesystem refuses. Fixed by opening it as `file:...?mode=ro&immutable=1`.
- **The map ignored filter changes.** Selecting a neighbourhood filtered the data
  without moving the view, so choosing somewhere off-screen looked like it had done
  nothing. Every focus component only acted on a non-null value, so no code owned
  the camera when a filter changed. (The same flaw stranded the map after
  geolocation, a feature since removed — [ADR-0008](docs/decisions/0008-no-geolocation.md).)

The frontend was verified with Playwright at 390/768/1440px — no horizontal
overflow, no console errors, deep links restoring state, keyboard selection working.

---

## What is generated vs written

The challenge asks for this explicitly.

**Generated by tooling, then modified:**

- `django-admin startproject config .` produced `manage.py`, `config/__init__.py`,
  `config/wsgi.py`, and the initial `config/settings.py` and `config/urls.py`.
  Both settings and urls were then rewritten; `config/asgi.py` was deleted, since
  there is no ASGI server (ADR-0003).
- `npm create vite@latest -- --template react-ts` produced the frontend skeleton:
  `package.json`, `tsconfig*.json`, `vite.config.ts`, `eslint.config.js`, and
  placeholder `App.tsx` / `main.tsx` / `index.css`. The placeholders were replaced;
  the config files are unmodified.
- `manage.py makemigrations` generated `films/migrations/0001_initial.py`.

**Written for this project** — everything else, specifically:

```
backend/films/models.py              backend/films/views.py
backend/films/serializers.py         backend/films/admin.py
backend/films/services/*.py          backend/films/management/commands/*.py
backend/films/tests/*.py             backend/config/settings.py (rewritten)
frontend/src/**                      docs/**
api/index.py                         build.sh
vercel.json
```

No component library, no CSS framework, and no scaffolded UI: the design tokens,
map layers, filmstrip panel, and combobox are written directly.

---

## Experience with this stack

Stated plainly, since the challenge asks.

- **Python** — strongest language. Comfortable with the standard library, typing,
  and packaging.
- **Django / DRF** — competent and productive. Familiar with the ORM, migrations,
  management commands, and DRF's serializer and viewset layers. Less practiced with
  Django's async story, Channels, and multi-database setups — part of why ADR-0003's
  reasoning mattered to get right rather than reach for.
- **TypeScript / React** — comfortable with hooks, component composition, and typed
  API boundaries. Used TanStack Query rather than hand-rolled fetch state.
- **Leaflet** — first substantial use. Clustering and the canvas renderer were
  learned during this build; the marker-styling fix in the frontend commit came from
  discovering that Leaflet writes fill and stroke as inline SVG attributes.
- **SQLite / Postgres** — comfortable with schema design, indexing, and query
  tuning. `pg_trgm` is familiar, which is what made rejecting it a considered call
  (ADR-0004) rather than an avoided one.

---

## Known limits

- **No geolocation.** A "filmed near me" control was built and then removed:
  most visitors to a San Francisco map are not in San Francisco, so its usual
  answer was an empty result after a permission prompt
  ([ADR-0008](docs/decisions/0008-no-geolocation.md)).
- **Search is substring, not fuzzy.** `godfath` matches; `godfathr` does not.
  Documented upgrade path in [ADR-0004](docs/decisions/0004-sqlite-and-search.md).
- **No rate limiting.** Deliberate for a read-only demo
  ([ADR-0006](docs/decisions/0006-scope-cuts.md)); roughly four lines to add.
- **No end-to-end test suite.** Playwright was used to verify the UI during
  development, but the checks are not committed as a suite.
- **Data freshness is tied to deploys.** The database is built during
  `vercel build` (ADR-0007), so refreshing means redeploying. The dataset is
  republished every few months, so this is rarely the constraint it sounds like.
- **The build depends on DataSF being reachable.** A failed sync fails the build
  deliberately — shipping an empty database would deploy a site that reports
  healthy and serves an empty map.
- **Cold starts.** The API is a serverless function, so the first request after
  idle takes a few hundred milliseconds longer.
