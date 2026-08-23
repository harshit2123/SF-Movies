"""
Serializers for the read-only API.

Three shapes for three uses, rather than one serializer with conditional fields:
autocomplete needs to be tiny, list needs counts, detail needs everything. Keeping
them separate means each endpoint's payload is obvious from its serializer.
"""

from rest_framework import serializers

from films.models import Film, FilmLocation


class FilmAutocompleteSerializer(serializers.ModelSerializer):
    """Minimal payload for the search dropdown — fires on every keystroke."""

    location_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Film
        fields = ["slug", "title", "release_year", "location_count"]


class FilmListSerializer(serializers.ModelSerializer):
    """List row. Counts are annotated by the view to avoid a query per film."""

    location_count = serializers.IntegerField(read_only=True)
    mappable_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Film
        fields = [
            "slug",
            "title",
            "release_year",
            "director",
            "actors",
            "location_count",
            "mappable_count",
        ]


class FilmLocationSerializer(serializers.ModelSerializer):
    """A location nested inside its film's detail response."""

    class Meta:
        model = FilmLocation
        fields = [
            "id",
            "location_text",
            "latitude",
            "longitude",
            "is_mappable",
            "neighborhood",
            "supervisor_district",
            "fun_facts",
        ]


class FilmDetailSerializer(serializers.ModelSerializer):
    """Full film detail, including unmappable locations (ADR-0001)."""

    locations = FilmLocationSerializer(many=True, read_only=True)

    class Meta:
        model = Film
        fields = [
            "slug",
            "title",
            "release_year",
            "director",
            "writer",
            "production_company",
            "distributor",
            "actors",
            "locations",
        ]


class MapMarkerSerializer(serializers.ModelSerializer):
    """
    Flat marker for the map.

    Film fields are denormalized onto each marker so the frontend can render a popup
    without a second request. The whole mappable set ships at once, so the payload is
    kept deliberately narrow.
    """

    film_slug = serializers.CharField(source="film.slug", read_only=True)
    film_title = serializers.CharField(source="film.title", read_only=True)
    release_year = serializers.IntegerField(source="film.release_year", read_only=True)

    class Meta:
        model = FilmLocation
        fields = [
            "id",
            "film_slug",
            "film_title",
            "release_year",
            "location_text",
            "latitude",
            "longitude",
            "neighborhood",
        ]


class NearbyLocationSerializer(MapMarkerSerializer):
    """A marker plus its distance from the query point, annotated by the view."""

    distance_km = serializers.FloatField(read_only=True)

    class Meta(MapMarkerSerializer.Meta):
        fields = MapMarkerSerializer.Meta.fields + ["distance_km"]
