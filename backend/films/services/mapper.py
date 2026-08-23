"""
Translation from raw Socrata rows to model-ready values.

Kept separate from both the HTTP client and the database writer so each can be tested
alone. This module is also the single place that reads `latitude`/`longitude` — if
DataSF ever stopped publishing coordinates, a geocoding step would slot in here without
touching the model or the API (ADR-0002).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger("films.mapper")

# San Francisco bounding box, generously padded. Guards against transposed
# coordinates and null-island (0, 0) rows, which would otherwise plot a marker
# in the Gulf of Guinea.
SF_LAT_RANGE = (37.6, 37.9)
SF_LNG_RANGE = (-123.2, -122.3)


class MalformedRecord(Exception):
    """A source row cannot be mapped. Logged and skipped, never fatal."""


@dataclass(frozen=True)
class MappedRow:
    """One source row, normalized. Immutable — mapping never mutates its input."""

    title: str
    release_year: int | None
    director: str
    writer: str
    production_company: str
    distributor: str
    actors: list[str] = field(default_factory=list)

    location_text: str = ""
    latitude: float | None = None
    longitude: float | None = None
    is_mappable: bool = False
    neighborhood: str = ""
    supervisor_district: str = ""
    fun_facts: str = ""
    data_as_of: datetime | None = None


def _clean(value: Any) -> str:
    """Normalize a source value to a stripped string. Missing becomes empty."""
    return str(value).strip() if value is not None else ""


def _parse_year(value: Any) -> int | None:
    """
    Parse release_year, tolerating the messiness real municipal data carries.

    Anything outside plausible cinema history is treated as absent rather than
    trusted — the dataset genuinely starts at 1915.
    """
    raw = _clean(value)
    if not raw:
        return None
    try:
        year = int(float(raw))
    except (TypeError, ValueError):
        return None
    return year if 1880 <= year <= 2100 else None


def _parse_coordinates(row: dict[str, Any]) -> tuple[float | None, float | None]:
    """
    Extract and validate coordinates.

    Returns (None, None) when absent or implausible, which drives `is_mappable=False`.
    Out-of-range values are dropped rather than plotted wrongly: a marker in the wrong
    ocean is worse than a missing marker.
    """
    lat_raw, lng_raw = _clean(row.get("latitude")), _clean(row.get("longitude"))
    if not lat_raw or not lng_raw:
        return None, None

    try:
        lat, lng = float(lat_raw), float(lng_raw)
    except (TypeError, ValueError):
        logger.warning("unparseable coordinates lat=%r lng=%r", lat_raw, lng_raw)
        return None, None

    if not (SF_LAT_RANGE[0] <= lat <= SF_LAT_RANGE[1]):
        logger.warning("latitude outside San Francisco lat=%s", lat)
        return None, None
    if not (SF_LNG_RANGE[0] <= lng <= SF_LNG_RANGE[1]):
        logger.warning("longitude outside San Francisco lng=%s", lng)
        return None, None

    return lat, lng


def _parse_timestamp(value: Any) -> datetime | None:
    """
    Parse a source timestamp into an aware datetime.

    Socrata publishes `data_as_of` without an offset. Storing it naive while Django
    runs with `USE_TZ=True` makes every re-run compare naive against aware, which
    always differs — so an idempotent sync would report every row as updated.
    The source timestamps are UTC.
    """
    parsed = parse_datetime(_clean(value) or "")
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, dt_timezone.utc)
    return parsed


def _parse_actors(row: dict[str, Any]) -> list[str]:
    """
    Collapse actor_1..actor_3 into one ordered list.

    Order is preserved (billing order in the source) and duplicates are dropped —
    some rows repeat the same name across columns.
    """
    actors: list[str] = []
    for key in ("actor_1", "actor_2", "actor_3"):
        name = _clean(row.get(key))
        if name and name not in actors:
            actors.append(name)
    return actors


def map_row(row: dict[str, Any]) -> MappedRow:
    """
    Map one Socrata row.

    Raises `MalformedRecord` only when the row lacks a title, which is the single
    field with no sensible fallback — everything else degrades to empty or None.
    """
    title = _clean(row.get("title"))
    if not title:
        raise MalformedRecord("row has no title")

    latitude, longitude = _parse_coordinates(row)

    return MappedRow(
        title=title,
        release_year=_parse_year(row.get("release_year")),
        director=_clean(row.get("director")),
        writer=_clean(row.get("writer")),
        production_company=_clean(row.get("production_company")),
        distributor=_clean(row.get("distributor")),
        actors=_parse_actors(row),
        location_text=_clean(row.get("locations")),
        latitude=latitude,
        longitude=longitude,
        # The definition of mappable, in one place (ADR-0001).
        is_mappable=latitude is not None and longitude is not None,
        neighborhood=_clean(row.get("analysis_neighborhood")),
        supervisor_district=_clean(row.get("supervisor_district")),
        fun_facts=_clean(row.get("fun_facts")),
        data_as_of=_parse_timestamp(row.get("data_as_of")),
    )
