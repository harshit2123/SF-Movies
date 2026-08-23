# ADR-0008 — No geolocation or "filmed near me"

**Status:** Accepted

## Context

The app shipped with a "Filmed near me" control: it asked the browser for the
user's position and filtered the map to locations within 1.5 km, backed by a
`GET /api/locations/nearby/` endpoint using Haversine over a bounding-box prefilter.

It worked, and it demoed well from San Francisco. The problem is who actually
uses it. This is a map of **one city's** film permits. The audience is people
interested in San Francisco on film — most of whom are not standing in San
Francisco. For them the feature had one outcome: request a location permission
prompt, then return an empty result set.

A control whose most common response is "nothing near you" is not a feature; it
is a dead end placed at the top of the sidebar.

## Decision

Remove it, end to end:

| Removed | |
|---|---|
| Frontend | the button, `useGeolocation`, the `UserFocus` map layer, the user marker, `nearby` URL state, `useNearby` |
| Backend | `GET /api/locations/nearby/`, `NearbyLocationSerializer`, `films/services/geo.py` |
| Tests | 14 covering the endpoint, its validation, and the Haversine helpers |

The map's own controls replace it. Someone who *is* in San Francisco can pan and
zoom to where they are, and at street level every marker now carries its film's
name (see the marker-labelling work). That serves the same intent without a
permission prompt.

## Alternatives considered

**Keep the endpoint, drop only the button.** Tempting — the API stays a complete,
documented service, which is what the brief asks for, and the geo query is real
work worth showing. Rejected because an endpoint no client calls is dead code with
documentation attached; the repository should not carry a feature nobody can reach.
The Haversine implementation is in the git history if it is ever wanted back.

**Default the location to San Francisco when geolocation fails.** Makes the button
always return something, but it then answers a question the user did not ask —
"near me" silently meaning "near downtown" is worse than no button.

**Keep it and accept the empty result.** The honest version of the current
behaviour. Rejected: a permission prompt is a real cost to the user, and paying it
to be told "nothing found" is a bad trade.

## Tradeoffs

- **Gained:** one fewer permission prompt, one fewer endpoint to document and
  maintain, ~14 tests and a service module removed, and a sidebar whose every
  control does something for every visitor.
- **Cost:** visitors who *are* in San Francisco lose a genuine shortcut. They can
  still pan to their neighbourhood, and the neighbourhood filter covers the common
  case directly.
- **Cost:** the API no longer demonstrates a geo query. The bounding-box index on
  `(latitude, longitude)` remains and still serves the map's viewport filtering,
  so the indexing decision is still visible in the schema.

## Note

This removes a feature that worked. It is recorded because "we built it and then
took it out" is a decision, and a reviewer finding `nearby` in the git history
should be able to see why it is not in the product.
