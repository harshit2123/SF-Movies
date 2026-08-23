"""
Endpoint tests.

Data comes from the same trimmed real fixture the ingestion tests use, so these
exercise genuine field shapes rather than hand-built ideal records.
"""

import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from films.models import Film, FilmLocation
from films.services.ingest import ingest_rows

FIXTURE = Path(__file__).parent / "fixtures_socrata.json"

@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def seeded(db) -> None:
    ingest_rows(json.loads(FIXTURE.read_text()))


# ---------------------------------------------------------------- films


@pytest.mark.django_db
def test_film_list_returns_paginated_envelope(client, seeded):
    response = client.get("/api/films/")

    assert response.status_code == 200
    assert response.data["count"] == Film.objects.count()
    assert "results" in response.data


@pytest.mark.django_db
def test_facet_neighborhoods_are_deduplicated(client, db):
    """
    Regression: `Meta.ordering` on FilmLocation joins Film and adds its columns to
    the SELECT, which defeats DISTINCT — the endpoint returned one entry per location
    (2,063) instead of one per neighborhood (40). Needs several locations sharing a
    neighborhood to reproduce, which the small fixture alone does not provide.
    """
    film = Film.objects.create(slug="f-2000", title="F", release_year=2000)
    for i in range(5):
        FilmLocation.objects.create(
            film=film,
            location_text=f"Place {i}",
            latitude=37.8,
            longitude=-122.4,
            is_mappable=True,
            neighborhood="Chinatown",
            content_hash=f"hash-{i}",
        )

    facets = client.get("/api/films/").data["facets"]

    assert facets["neighborhoods"] == ["Chinatown"]


@pytest.mark.django_db
def test_film_list_includes_facets(client, seeded):
    response = client.get("/api/films/")

    facets = response.data["facets"]
    # Facets ship inline so the client needs no second request.
    assert all(decade % 10 == 0 for decade in facets["decades"])
    assert facets["neighborhoods"] == sorted(facets["neighborhoods"])
    # Regression: the model's default ordering joined Film into the query and added
    # its columns to the SELECT, which defeated DISTINCT and returned one entry per
    # location (2,063 "neighborhoods" instead of 40).
    assert len(facets["neighborhoods"]) == len(set(facets["neighborhoods"]))
    assert len(facets["decades"]) == len(set(facets["decades"]))
    assert len(facets["neighborhoods"]) < FilmLocation.objects.count()


@pytest.mark.django_db
def test_film_list_annotates_location_counts(client, seeded):
    response = client.get("/api/films/?search=Milk")

    milk = response.data["results"][0]
    assert milk["location_count"] == 4
    assert milk["mappable_count"] <= milk["location_count"]


@pytest.mark.django_db
def test_film_search_matches_title_case_insensitively(client, seeded):
    response = client.get("/api/films/?search=milk")

    assert any(f["title"] == "Milk" for f in response.data["results"])


@pytest.mark.django_db
def test_film_search_matches_director(client, seeded):
    response = client.get("/api/films/?search=Van Sant")

    assert response.data["count"] >= 1
    assert all("Milk" == f["title"] for f in response.data["results"])


@pytest.mark.django_db
def test_film_filter_by_decade(client, seeded):
    response = client.get("/api/films/?decade=2000")

    for film in response.data["results"]:
        assert 2000 <= film["release_year"] < 2010


@pytest.mark.django_db
def test_film_filter_by_invalid_decade_returns_400(client, seeded):
    response = client.get("/api/films/?decade=not-a-year")

    assert response.status_code == 400
    assert "decade" in response.data


@pytest.mark.django_db
def test_film_detail_includes_all_locations(client, seeded):
    response = client.get("/api/films/milk-2008/")

    assert response.status_code == 200
    assert len(response.data["locations"]) == 4
    assert "fun_facts" in response.data["locations"][0]


@pytest.mark.django_db
def test_film_detail_unknown_slug_returns_404(client, seeded):
    assert client.get("/api/films/does-not-exist/").status_code == 404


@pytest.mark.django_db
def test_film_detail_includes_unmappable_locations(client, seeded):
    """Coordinate-less rows stay visible in detail even though the map omits them."""
    unmappable = FilmLocation.objects.filter(is_mappable=False).first()

    response = client.get(f"/api/films/{unmappable.film.slug}/")

    ids = [loc["id"] for loc in response.data["locations"]]
    assert unmappable.id in ids


# ---------------------------------------------------------------- autocomplete


@pytest.mark.django_db
def test_autocomplete_returns_matches(client, seeded):
    response = client.get("/api/films/autocomplete/?q=mil")

    assert response.status_code == 200
    assert any(item["title"] == "Milk" for item in response.data)


@pytest.mark.django_db
@pytest.mark.parametrize("term", ["", "m"])
def test_autocomplete_below_min_length_returns_empty_not_error(client, seeded, term):
    # The client fires on every keystroke; a 400 mid-typing is not an error.
    response = client.get(f"/api/films/autocomplete/?q={term}")

    assert response.status_code == 200
    assert response.data == []


@pytest.mark.django_db
def test_autocomplete_is_capped(client, seeded):
    response = client.get("/api/films/autocomplete/?q=e")

    assert len(response.data) <= 10


@pytest.mark.django_db
def test_autocomplete_payload_is_minimal(client, seeded):
    response = client.get("/api/films/autocomplete/?q=milk")

    assert set(response.data[0]) == {
        "slug",
        "title",
        "release_year",
        "location_count",
    }


# ---------------------------------------------------------------- map markers


@pytest.mark.django_db
def test_locations_excludes_unmappable_rows(client, seeded):
    response = client.get("/api/locations/")

    assert response.status_code == 200
    assert len(response.data) == FilmLocation.objects.mappable().count()
    assert all(marker["latitude"] is not None for marker in response.data)


@pytest.mark.django_db
def test_locations_is_not_paginated(client, seeded):
    """Clustering needs the whole set, so this endpoint returns a bare list."""
    response = client.get("/api/locations/")

    assert isinstance(response.data, list)


@pytest.mark.django_db
def test_locations_filtered_by_film_slug(client, seeded):
    response = client.get("/api/locations/?film=milk-2008")

    assert len(response.data) == 4
    assert all(m["film_slug"] == "milk-2008" for m in response.data)


@pytest.mark.django_db
def test_locations_bbox_filter(client, seeded):
    # A tight box around Coit Tower should exclude markers elsewhere in the city.
    response = client.get("/api/locations/?bbox=-122.41,37.80,-122.40,37.81")

    for marker in response.data:
        assert -122.41 <= marker["longitude"] <= -122.40
        assert 37.80 <= marker["latitude"] <= 37.81


@pytest.mark.django_db
@pytest.mark.parametrize("bbox", ["1,2,3", "a,b,c,d"])
def test_locations_malformed_bbox_returns_400(client, seeded, bbox):
    response = client.get(f"/api/locations/?bbox={bbox}")

    assert response.status_code == 400
    assert "bbox" in response.data


# ---------------------------------------------------------------- health


@pytest.mark.django_db
def test_health_reports_ok_when_seeded(client, seeded):
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert response.data["film_count"] > 0
    assert response.data["mappable_count"] <= response.data["location_count"]


@pytest.mark.django_db
def test_health_reports_degraded_when_empty(client):
    """An API serving zero films is up but useless — a skipped sync must show."""
    response = client.get("/api/health/")

    assert response.status_code == 503
    assert response.data["status"] == "degraded"
    assert "sync_film_locations" in response.data["detail"]

