"""
Distance helpers for the "filmed near me" feature.

Haversine in Python over a bounding-box-prefiltered queryset, rather than PostGIS.
At 2,120 mappable points the box prefilter typically leaves a few dozen rows, and
the distance maths on those is microseconds — a spatial database would be a service
to run and a dependency to install for no measurable gain (ADR-0006).

The threshold where this flips: roughly 100k points, or as soon as a query needs
polygon containment or nearest-neighbour ordering pushed into the database.
"""

import math

EARTH_RADIUS_KM = 6371.0088

# Guard rails on user-supplied input.
MAX_RADIUS_KM = 20.0
DEFAULT_RADIUS_KM = 1.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(
    lat: float, lng: float, radius_km: float
) -> tuple[float, float, float, float]:
    """
    Square bounding box enclosing the search circle.

    Used as an indexed prefilter so Haversine runs over a handful of candidate rows
    instead of the whole table. The box is deliberately larger than the circle — it
    over-selects, and the exact distance check that follows discards the corners.
    """
    lat_delta = math.degrees(radius_km / EARTH_RADIUS_KM)

    # Longitude degrees shrink toward the poles; guard against division by zero
    # at the poles even though San Francisco is nowhere near them.
    cos_lat = math.cos(math.radians(lat))
    lng_delta = (
        math.degrees(radius_km / (EARTH_RADIUS_KM * cos_lat)) if abs(cos_lat) > 1e-9
        else 180.0
    )

    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)
