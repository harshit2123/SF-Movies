# ADR-0008 — No geolocation in the interface; the endpoint stays

**Status:** Accepted

## Context

The app shipped with a "Filmed near me" control: it asked the browser for the
user's position and filtered the map to locations within 1.5 km, backed by
`GET /api/locations/nearby/`.

It worked, and it demoed well from San Francisco. The problem is who actually
uses it. This is a map of **one city's** film permits. The audience is people
interested in San Francisco on film — most of whom are not standing in San
Francisco. For them the control had one outcome: a location permission prompt,
followed by an empty result set.

A button whose most common answer is "nothing near you" is not a feature; it is a
dead end at the top of the sidebar.

## Decision

**Remove the control from the interface. Keep the endpoint.**

Removed from the frontend:

| | |
|---|---|
| `FilterPanel` | the button and its props |
| `hooks/useGeolocation.ts` | deleted |
| `MapView` | the `UserFocus` layer and the user-position marker |
| `useUrlState` | the `nearby` parameter |
| `lib/queries.ts`, `lib/api.ts` | `useNearby`, `NearbyMarker`, `api.nearby` |

Kept in the backend, unchanged and tested:

- `GET /api/locations/nearby/?lat=&lng=&radius_km=`
- `films/services/geo.py` — Haversine with a bounding-box prefilter
- `NearbyLocationSerializer`
- 14 tests covering the endpoint, its input validation, and the distance maths

## Why keep the endpoint

The brief asks for an API written and documented **as if other services will use
it**. Geographic proximity is an obvious query for a dataset of coordinates, and
it is genuinely useful to a consumer that *does* know where its user is — a mobile
client, or a walking-tour app built on this data.

Removing a correct, documented, tested endpoint because this particular frontend
stopped calling it would narrow the API to exactly one client's current needs.
That is the opposite of what the brief asks for.

It stays documented in [docs/API.md](../API.md), with a note that the bundled SPA
does not call it.

## Alternatives considered

**Remove it end to end.** Smaller codebase, and no code without a caller. Rejected:
it would delete a working endpoint, its geo service, and 14 tests to serve a
frontend styling decision, and it narrows the API to one consumer.

**Keep the button, default to San Francisco when geolocation fails.** Makes the
control always return something, but it then answers a question the user did not
ask — "near me" quietly meaning "near downtown" is worse than no button at all.

**Keep the button and accept the empty result.** The honest version of the previous
behaviour. Rejected: a permission prompt is a real cost, and paying it to be told
"nothing found" is a bad trade.

## Tradeoffs

- **Gained:** no permission prompt, and a sidebar where every control does
  something for every visitor.
- **Kept:** the API still demonstrates a geo query and stays useful to consumers
  that know their user's position.
- **Cost:** an endpoint the bundled SPA does not call. Deliberate, and stated in
  the API reference so it does not read as an oversight.
- **Cost:** visitors who *are* in San Francisco lose a shortcut. They can pan to
  their neighbourhood, and the neighbourhood filter covers the common case.

## Note

Recorded because "built, then taken out of the UI" is a decision. A reviewer
finding `nearby` in `views.py` but not in the interface should be able to see that
the split was intentional.
