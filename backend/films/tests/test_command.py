"""
Tests for the sync management command.

The command is the operational entry point — it runs unattended from cron, so its
failure behavior matters as much as its success path. HTTP is mocked throughout.
"""

import json
from io import StringIO
from pathlib import Path

import pytest
import responses
from django.core.management import call_command
from django.core.management.base import CommandError

from films.models import Film, FilmLocation

FIXTURE = Path(__file__).parent / "fixtures_socrata.json"
ENDPOINT = "https://data.sfgov.org/resource/yitu-d5am.json"


@pytest.fixture
def rows() -> list[dict]:
    return json.loads(FIXTURE.read_text())


def run_command(*args) -> str:
    out = StringIO()
    call_command("sync_film_locations", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


@pytest.mark.django_db
@responses.activate
def test_command_ingests_and_reports(rows):
    responses.add(responses.GET, ENDPOINT, json=rows, status=200)

    output = run_command()

    assert Film.objects.exists()
    assert FilmLocation.objects.count() == len(rows)
    assert f"rows fetched        {len(rows)}" in output
    assert "Sync complete" in output


@pytest.mark.django_db
@responses.activate
def test_command_dry_run_persists_nothing(rows):
    responses.add(responses.GET, ENDPOINT, json=rows, status=200)

    output = run_command("--dry-run")

    assert Film.objects.count() == 0
    assert "DRY RUN" in output
    assert "rolled back" in output


@pytest.mark.django_db
@responses.activate
def test_command_limit_caps_rows(rows):
    responses.add(responses.GET, ENDPOINT, json=rows[:2], status=200)

    run_command("--limit", "2")

    assert FilmLocation.objects.count() == 2


@pytest.mark.django_db
@responses.activate
def test_command_reports_idempotent_rerun(rows):
    responses.add(responses.GET, ENDPOINT, json=rows, status=200)
    responses.add(responses.GET, ENDPOINT, json=rows, status=200)

    run_command()
    output = run_command()

    assert "Already up to date" in output


@pytest.mark.django_db
@responses.activate
def test_command_raises_command_error_on_api_failure():
    """Unattended runs need a clean error, not a traceback."""
    for _ in range(5):
        responses.add(responses.GET, ENDPOINT, json={}, status=503)

    with pytest.raises(CommandError, match="Sync failed"):
        run_command()


@pytest.mark.django_db
@responses.activate
def test_command_failure_leaves_no_partial_state(rows):
    responses.add(responses.GET, ENDPOINT, json=rows, status=200)
    run_command()
    before = FilmLocation.objects.count()

    responses.reset()
    for _ in range(5):
        responses.add(responses.GET, ENDPOINT, json={}, status=500)
    with pytest.raises(CommandError):
        run_command()

    assert FilmLocation.objects.count() == before
