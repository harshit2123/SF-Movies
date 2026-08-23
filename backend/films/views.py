"""
Read-only API views.

Views own request/response concerns only. Anything reusable lives in `services/`,
and nothing here reaches out to DataSF — the API serves the local database, which the
sync command populates (ADR-0003).
"""

import logging

from django.db.models import Count, Q, QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response

from films.models import Film, FilmLocation
from films.serializers import (
    FilmAutocompleteSerializer,
    FilmDetailSerializer,
    FilmListSerializer,
    MapMarkerSerializer,
    NearbyLocationSerializer,
)
from films.services.geo import (
    DEFAULT_RADIUS_KM,
    MAX_RADIUS_KM,
    bounding_box,
    haversine_km,
)

logger = logging.getLogger("films.views")

AUTOCOMPLETE_MIN_LENGTH = 2
AUTOCOMPLETE_LIMIT = 10
NEARBY_DEFAULT_LIMIT = 50
NEARBY_MAX_LIMIT = 200


# Film fields searched by `?search=`. Written as bare lookups so the same list can
# serve Film querysets and FilmLocation querysets, where they sit behind a relation.
SEARCH_FIELDS = ("title__icontains", "director__icontains", "actors__icontains")


def _search_filter(term: str, prefix: str = "") -> Q:
    """
    Case-insensitive substring search across title, director, and cast.

    Substring rather than trigram similarity: at 352 films this is instant and needs
    no database extension (ADR-0004). `actors` is a JSON list, so `icontains` matches
    against its serialized text — adequate for name lookup at this scale.
    """
    query = Q()
    for lookup in SEARCH_FIELDS:
        query |= Q(**{f"{prefix}{lookup}": term})
    return query


def _apply_common_filters(queryset: QuerySet, params, film_prefix: str = "") -> QuerySet:
    """
    Apply the filters shared by the film and location endpoints.

    `film_prefix` lets the same logic serve both `Film` querysets and `FilmLocation`
    querysets, where the film fields sit behind a relation.
    """
    if search := params.get("search", "").strip():
        queryset = queryset.filter(_search_filter(search, film_prefix))

    if decade := params.get("decade", "").strip():
        try:
            start = int(decade)
        except ValueError:
            raise ValidationError({"decade": "Must be an integer, e.g. 1970."})
        queryset = queryset.filter(
            **{
                f"{film_prefix}release_year__gte": start,
                f"{film_prefix}release_year__lt": start + 10,
            }
        )

    return queryset


class FilmViewSet(viewsets.ReadOnlyModelViewSet):
    """Films, with search and filtering. Read-only — writes happen via sync."""

    lookup_field = "slug"

    def get_queryset(self) -> QuerySet:
        queryset = Film.objects.annotate(
            location_count=Count("locations", distinct=True),
            mappable_count=Count(
                "locations", filter=Q(locations__is_mappable=True), distinct=True
            ),
        )

        params = self.request.query_params
        queryset = _apply_common_filters(queryset, params)

        if neighborhood := params.get("neighborhood", "").strip():
            queryset = queryset.filter(locations__neighborhood=neighborhood).distinct()

        if person := params.get("person", "").strip():
            queryset = queryset.filter(
                Q(director__icontains=person)
                | Q(writer__icontains=person)
                | Q(actors__icontains=person)
            )

        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return FilmDetailSerializer
        if self.action == "autocomplete":
            return FilmAutocompleteSerializer
        return FilmListSerializer

    def retrieve(self, request, *args, **kwargs):
        # Detail nests every location, so prefetch to avoid an N+1.
        self.queryset = self.get_queryset().prefetch_related("locations")
        return super().retrieve(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """List films, with facet values attached to the paginated envelope."""
        response = super().list(request, *args, **kwargs)
        # Facets ship with the response rather than as a separate round trip
        # (ADR-0006). Cheap: two distinct queries over a small table.
        response.data["facets"] = {
            "decades": sorted(
                {
                    (year // 10) * 10
                    for year in Film.objects.exclude(release_year=None)
                    .values_list("release_year", flat=True)
                    .distinct()
                }
            ),
            "neighborhoods": sorted(
                FilmLocation.objects.exclude(neighborhood="")
                # `Meta.ordering` would otherwise join Film and add its columns to
                # the SELECT, defeating DISTINCT and returning one row per location.
                .order_by()
                .values_list("neighborhood", flat=True)
                .distinct()
            ),
        }
        return response

    @action(detail=False, methods=["get"])
    def autocomplete(self, request):
        """
        Search suggestions for the dropdown.

        Returns an empty list below the minimum query length rather than an error —
        the client calls this on every keystroke, and a 400 while the user is still
        typing is not an error condition.
        """
        term = request.query_params.get("q", "").strip()
        if len(term) < AUTOCOMPLETE_MIN_LENGTH:
            return Response([])

        films = (
            Film.objects.filter(_search_filter(term))
            .annotate(location_count=Count("locations"))
            .order_by("-location_count", "title")[:AUTOCOMPLETE_LIMIT]
        )
        return Response(FilmAutocompleteSerializer(films, many=True).data)


class MapMarkerListView(ListAPIView):
    """
    Every mappable location, for the map.

    Deliberately unpaginated: clustering needs the full set to compute clusters
    correctly, and 2,120 narrow markers is a small payload.
    """

    serializer_class = MapMarkerSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet:
        queryset = FilmLocation.objects.mappable().select_related("film")
        params = self.request.query_params

        queryset = _apply_common_filters(queryset, params, film_prefix="film__")

        if film_slug := params.get("film", "").strip():
            queryset = queryset.filter(film__slug=film_slug)

        if neighborhood := params.get("neighborhood", "").strip():
            queryset = queryset.filter(neighborhood=neighborhood)

        if bbox := params.get("bbox", "").strip():
            queryset = self._filter_bbox(queryset, bbox)

        return queryset

    @staticmethod
    def _filter_bbox(queryset: QuerySet, bbox: str) -> QuerySet:
        """Filter to a viewport given as `min_lng,min_lat,max_lng,max_lat`."""
        parts = bbox.split(",")
        if len(parts) != 4:
            raise ValidationError(
                {"bbox": "Expected four comma-separated values: "
                         "min_lng,min_lat,max_lng,max_lat."}
            )
        try:
            min_lng, min_lat, max_lng, max_lat = (float(p) for p in parts)
        except ValueError:
            raise ValidationError({"bbox": "All four values must be numbers."})

        return queryset.filter(
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lng,
            longitude__lte=max_lng,
        )


def _float_param(params, name: str, required: bool = True, default: float = 0.0):
    """Parse a float query parameter, raising a 400 with a useful message."""
    raw = params.get(name, "").strip()
    if not raw:
        if required:
            raise ValidationError({name: "This parameter is required."})
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValidationError({name: f"Must be a number, got {raw!r}."})


@api_view(["GET"])
def nearby_locations(request):
    """
    Mappable locations within a radius of a point, nearest first.

    A bounding box narrows candidates using the (latitude, longitude) index, then
    Haversine computes exact distances over what survives (ADR-0006).
    """
    params = request.query_params

    lat = _float_param(params, "lat")
    lng = _float_param(params, "lng")
    if not -90 <= lat <= 90:
        raise ValidationError({"lat": "Must be between -90 and 90."})
    if not -180 <= lng <= 180:
        raise ValidationError({"lng": "Must be between -180 and 180."})

    radius_km = _float_param(params, "radius_km", required=False, default=DEFAULT_RADIUS_KM)
    if radius_km <= 0:
        raise ValidationError({"radius_km": "Must be greater than zero."})
    radius_km = min(radius_km, MAX_RADIUS_KM)

    try:
        limit = min(int(params.get("limit", NEARBY_DEFAULT_LIMIT)), NEARBY_MAX_LIMIT)
    except ValueError:
        raise ValidationError({"limit": "Must be an integer."})

    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
    candidates = (
        FilmLocation.objects.mappable()
        .select_related("film")
        .filter(
            latitude__gte=min_lat,
            latitude__lte=max_lat,
            longitude__gte=min_lng,
            longitude__lte=max_lng,
        )
    )

    within = []
    for location in candidates:
        distance = haversine_km(lat, lng, location.latitude, location.longitude)
        # The box over-selects at its corners; this discards them.
        if distance <= radius_km:
            location.distance_km = round(distance, 3)
            within.append(location)

    within.sort(key=lambda loc: loc.distance_km)
    return Response(NearbyLocationSerializer(within[:limit], many=True).data)


@api_view(["GET"])
def health(request):
    """
    Liveness and data-freshness check.

    Reports degraded when the database is unreachable *or* empty — an API serving
    zero films is technically up but useless, and a deploy that skipped the sync
    should surface as a problem rather than as an empty map.
    """
    try:
        film_count = Film.objects.count()
        location_count = FilmLocation.objects.count()
        mappable_count = FilmLocation.objects.mappable().count()
        latest = (
            FilmLocation.objects.exclude(data_as_of=None)
            .order_by("-data_as_of")
            .values_list("data_as_of", flat=True)
            .first()
        )
    except Exception as exc:
        logger.exception("health check failed")
        return Response(
            {"status": "degraded", "database": "error", "detail": str(exc)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    payload = {
        "status": "ok" if film_count else "degraded",
        "database": "ok",
        "film_count": film_count,
        "location_count": location_count,
        "mappable_count": mappable_count,
        "last_sync": latest,
    }
    if not film_count:
        payload["detail"] = "Database is empty. Run: manage.py sync_film_locations"
        return Response(payload, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(payload)
