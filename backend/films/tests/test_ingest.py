"""
Tests for mapping and ingestion.

The fixture is trimmed from a real Socrata response and deliberately includes the
awkward cases: a multi-location film, rows with and without coordinates, a row with no
location text at all, and a row carrying fun_facts.
"""

import json
from pathlib import Path

import pytest

from films.models import Film, FilmLocation
from films.services.ingest import ingest_rows
from films.services.mapper import MalformedRecord, map_row

FIXTURE = Path(__file__).parent / "fixtures_socrata.json"


@pytest.fixture
def rows() -> list[dict]:
    return json.loads(FIXTURE.read_text())


# ---------------------------------------------------------------- mapping


def test_maps_a_complete_row(rows):
    row = next(r for r in rows if r["title"] == "Milk")

    mapped = map_row(row)

    assert mapped.title == "Milk"
    assert mapped.release_year == 2008
    assert mapped.director == "Gus Van Sant"
    assert mapped.is_mappable is True
    assert 37.6 < mapped.latitude < 37.9


def test_collapses_actor_columns_into_a_list(rows):
    row = next(r for r in rows if r.get("actor_3"))

    actors = map_row(row).actors

    assert len(actors) == 3
    assert all(isinstance(name, str) and name for name in actors)


def test_actor_list_drops_duplicates_and_blanks():
    mapped = map_row(
        {"title": "T", "actor_1": "Ann", "actor_2": "Ann", "actor_3": "  "}
    )

    assert mapped.actors == ["Ann"]


def test_row_without_coordinates_is_not_mappable(rows):
    row = next(r for r in rows if not r.get("latitude"))

    mapped = map_row(row)

    assert mapped.is_mappable is False
    assert mapped.latitude is None


def test_row_without_title_is_malformed():
    with pytest.raises(MalformedRecord, match="no title"):
        map_row({"locations": "Coit Tower"})


def test_missing_optional_fields_degrade_to_empty():
    mapped = map_row({"title": "Minimal"})

    assert mapped.director == ""
    assert mapped.actors == []
    assert mapped.release_year is None
    assert mapped.is_mappable is False


@pytest.mark.parametrize("year", ["not-a-year", "", "1799", "3000", None])
def test_implausible_years_become_none(year):
    assert map_row({"title": "T", "release_year": year}).release_year is None


def test_coordinates_outside_san_francisco_are_rejected():
    # Guards against transposed lat/lng and null-island rows.
    mapped = map_row({"title": "T", "latitude": "51.5", "longitude": "-0.12"})

    assert mapped.is_mappable is False


def test_zero_zero_coordinates_are_rejected():
    mapped = map_row({"title": "T", "latitude": "0", "longitude": "0"})

    assert mapped.is_mappable is False


def test_unparseable_coordinates_are_rejected():
    mapped = map_row({"title": "T", "latitude": "north", "longitude": "west"})

    assert mapped.is_mappable is False


def test_source_timestamp_is_timezone_aware(rows):
    """
    Regression: Socrata sends `data_as_of` without an offset. Left naive, it never
    compares equal to the aware value Django stores, so every re-run reported every
    row as updated and idempotency was silently broken.
    """
    row = next(r for r in rows if r.get("data_as_of"))

    mapped = map_row(row)

    assert mapped.data_as_of is not None
    assert mapped.data_as_of.tzinfo is not None


def test_missing_timestamp_is_none():
    assert map_row({"title": "T"}).data_as_of is None


# ---------------------------------------------------------------- ingestion


@pytest.mark.django_db
def test_ingest_creates_films_and_locations(rows):
    report = ingest_rows(rows)

    assert report.fetched == len(rows)
    assert report.locations_created == len(rows)
    assert Film.objects.count() < len(rows)  # rows collapse into fewer films
    assert FilmLocation.objects.count() == len(rows)


@pytest.mark.django_db
def test_multi_location_film_is_deduplicated(rows):
    ingest_rows(rows)

    milk = Film.objects.get(slug="milk-2008")

    # Four Milk rows in the fixture, one film, four locations.
    assert milk.locations.count() == 4


@pytest.mark.django_db
def test_rerun_is_idempotent(rows):
    ingest_rows(rows)
    films_before = Film.objects.count()
    locations_before = FilmLocation.objects.count()

    report = ingest_rows(rows)

    # The property that makes the command safe to schedule.
    assert report.films_created == 0
    assert report.locations_created == 0
    assert report.locations_updated == 0
    assert report.locations_unchanged == len(rows)
    assert report.is_idempotent_run
    assert Film.objects.count() == films_before
    assert FilmLocation.objects.count() == locations_before


@pytest.mark.django_db
def test_changed_upstream_value_updates_in_place(rows):
    ingest_rows(rows)
    target = next(r for r in rows if r.get("analysis_neighborhood"))
    edited = {**target, "analysis_neighborhood": "Corrected Neighborhood"}

    report = ingest_rows([edited])

    assert report.locations_updated == 1
    assert report.locations_created == 0
    location = FilmLocation.objects.get(
        content_hash=FilmLocation.build_content_hash(
            target["title"], int(target["release_year"]), target["locations"]
        )
    )
    assert location.neighborhood == "Corrected Neighborhood"


@pytest.mark.django_db
def test_blank_incoming_film_field_does_not_erase_known_value(rows):
    """Film detail is repeated per row and is sometimes partial — never regress it."""
    row = next(r for r in rows if r.get("director"))
    ingest_rows([row])

    ingest_rows([{**row, "director": ""}])

    film = Film.objects.get(slug=Film.build_slug(row["title"], int(row["release_year"])))
    assert film.director == row["director"]


@pytest.mark.django_db
def test_contradicting_film_rows_settle_deterministically(rows):
    """
    Regression: the source disagrees with itself. `summertime-2015` reports five
    different distributors across its rows, and two distinct films share the slug
    `golden-gate-1994`. Without first-write-wins, whichever row came last won, the
    winner changed between runs, and every sync reported phantom updates forever.
    """
    row = next(r for r in rows if r.get("distributor"))
    contradicting = {**row, "locations": "Somewhere Else", "distributor": "Rival Corp"}

    ingest_rows([row, contradicting])
    film = Film.objects.get(slug=Film.build_slug(row["title"], int(row["release_year"])))
    first_pass = film.distributor

    # Re-running must not flip the value back and forth.
    report = ingest_rows([row, contradicting])
    film.refresh_from_db()

    assert film.distributor == first_pass == row["distributor"]
    assert report.films_updated == 0
    assert report.is_idempotent_run


@pytest.mark.django_db
def test_duplicate_source_rows_are_counted_not_double_written(rows):
    row = next(r for r in rows if r.get("locations"))

    # Same identity twice in one run, differing only in detail.
    report = ingest_rows([row, {**row, "fun_facts": "A conflicting fact"}])

    assert report.locations_created == 1
    assert report.duplicate_rows == 1
    assert FilmLocation.objects.count() == 1


@pytest.mark.django_db
def test_malformed_row_is_skipped_not_fatal(rows):
    report = ingest_rows([*rows, {"locations": "No title here"}])

    assert report.skipped == 1
    assert report.locations_created == len(rows)  # good rows still imported
    assert report.skip_reasons


@pytest.mark.django_db
def test_dry_run_persists_nothing(rows):
    report = ingest_rows(rows, dry_run=True)

    # Report reflects the work that would happen...
    assert report.locations_created == len(rows)
    # ...but the transaction rolled back.
    assert Film.objects.count() == 0
    assert FilmLocation.objects.count() == 0


@pytest.mark.django_db
def test_mappable_queryset_excludes_coordinateless_rows(rows):
    ingest_rows(rows)

    total = FilmLocation.objects.count()
    mappable = FilmLocation.objects.mappable().count()

    assert 0 < mappable < total
    assert all(
        loc.latitude is not None for loc in FilmLocation.objects.mappable()
    )


# ---------------------------------------------------------------- identity


def test_content_hash_is_stable_across_calls():
    a = FilmLocation.build_content_hash("Milk", 2008, "Coit Tower")
    b = FilmLocation.build_content_hash("Milk", 2008, "Coit Tower")

    assert a == b


def test_content_hash_ignores_case_and_surrounding_whitespace():
    a = FilmLocation.build_content_hash("Milk", 2008, "Coit Tower")
    b = FilmLocation.build_content_hash("  milk ", 2008, "  COIT TOWER  ")

    # Upstream whitespace or casing changes must not duplicate a row.
    assert a == b


def test_content_hash_distinguishes_different_locations():
    a = FilmLocation.build_content_hash("Milk", 2008, "Coit Tower")
    b = FilmLocation.build_content_hash("Milk", 2008, "City Hall")

    assert a != b


def test_slug_disambiguates_same_title_different_years():
    assert Film.build_slug("Milk", 2008) != Film.build_slug("Milk", 1998)


def test_slug_handles_missing_year_and_punctuation():
    assert Film.build_slug("Milk", None) == "milk"
    assert Film.build_slug("Ant-Man & The Wasp", 2018) == "ant-man-the-wasp-2018"
