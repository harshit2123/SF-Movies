"""
Tests for the Socrata HTTP client.

All HTTP is mocked — the suite never touches the network, so it runs offline and in CI
without depending on DataSF being up.
"""

import pytest
import requests
import responses

from films.services.socrata import (
    SocrataBadRequest,
    SocrataClient,
    SocrataUnavailable,
)

ENDPOINT = "https://data.sfgov.org/resource/yitu-d5am.json"


def build_client(**overrides) -> SocrataClient:
    """Client with backoff disabled so retry tests do not actually sleep."""
    defaults = dict(
        base_url="https://data.sfgov.org",
        dataset_id="yitu-d5am",
        max_retries=2,
        page_size=2,
        sleep=lambda _seconds: None,
    )
    return SocrataClient(**{**defaults, **overrides})


@responses.activate
def test_returns_rows_on_success():
    responses.add(responses.GET, ENDPOINT, json=[{"title": "Milk"}], status=200)

    rows = list(build_client().iter_rows())

    assert rows == [{"title": "Milk"}]


@responses.activate
def test_paginates_until_short_page():
    # Page size is 2: a full page means "keep going", a short page means "stop".
    responses.add(
        responses.GET, ENDPOINT, json=[{"title": "A"}, {"title": "B"}], status=200
    )
    responses.add(responses.GET, ENDPOINT, json=[{"title": "C"}], status=200)

    rows = list(build_client().iter_rows())

    assert [r["title"] for r in rows] == ["A", "B", "C"]
    assert len(responses.calls) == 2
    # Second request must advance the offset, or pagination would loop forever.
    assert "%24offset=2" in responses.calls[1].request.url


@responses.activate
def test_stops_on_empty_page():
    responses.add(responses.GET, ENDPOINT, json=[], status=200)

    assert list(build_client().iter_rows()) == []


@responses.activate
def test_limit_caps_total_rows_and_page_size():
    responses.add(responses.GET, ENDPOINT, json=[{"title": "A"}], status=200)

    rows = list(build_client().iter_rows(limit=1))

    assert len(rows) == 1
    # The limit must shrink the requested page, not just truncate the result.
    assert "%24limit=1" in responses.calls[0].request.url


@responses.activate
@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_retries_retryable_statuses_then_succeeds(status):
    responses.add(responses.GET, ENDPOINT, json={"error": "boom"}, status=status)
    responses.add(responses.GET, ENDPOINT, json=[{"title": "Milk"}], status=200)

    rows = list(build_client().iter_rows())

    assert rows == [{"title": "Milk"}]
    assert len(responses.calls) == 2


@responses.activate
def test_gives_up_after_max_retries():
    for _ in range(3):  # max_retries=2 means 3 total attempts
        responses.add(responses.GET, ENDPOINT, json={}, status=503)

    with pytest.raises(SocrataUnavailable, match="after 3 attempts"):
        list(build_client().iter_rows())

    assert len(responses.calls) == 3


@responses.activate
@pytest.mark.parametrize("status", [400, 403, 404])
def test_does_not_retry_client_errors(status):
    responses.add(responses.GET, ENDPOINT, body="bad request", status=status)

    with pytest.raises(SocrataBadRequest):
        list(build_client().iter_rows())

    # Retrying a 4xx cannot help, so exactly one attempt should be made.
    assert len(responses.calls) == 1


@responses.activate
def test_retries_connection_errors():
    responses.add(responses.GET, ENDPOINT, body=requests.ConnectionError("refused"))
    responses.add(responses.GET, ENDPOINT, json=[{"title": "Milk"}], status=200)

    assert list(build_client().iter_rows()) == [{"title": "Milk"}]


@responses.activate
def test_retries_read_timeout():
    responses.add(responses.GET, ENDPOINT, body=requests.Timeout("too slow"))
    responses.add(responses.GET, ENDPOINT, json=[{"title": "Milk"}], status=200)

    assert list(build_client().iter_rows()) == [{"title": "Milk"}]


@responses.activate
def test_malformed_json_is_not_retried():
    # A 200 carrying unparseable content is a real error, not a transient one.
    responses.add(responses.GET, ENDPOINT, body="<html>not json</html>", status=200)

    with pytest.raises(SocrataUnavailable, match="malformed JSON"):
        list(build_client().iter_rows())

    assert len(responses.calls) == 1


@responses.activate
def test_unexpected_json_shape_is_rejected():
    responses.add(responses.GET, ENDPOINT, json={"unexpected": "object"}, status=200)

    with pytest.raises(SocrataUnavailable, match="Expected a JSON list"):
        list(build_client().iter_rows())


@responses.activate
def test_app_token_header_sent_only_when_configured():
    responses.add(responses.GET, ENDPOINT, json=[], status=200)
    list(build_client(app_token="secret-token").iter_rows())
    assert responses.calls[0].request.headers["X-App-Token"] == "secret-token"

    responses.reset()
    responses.add(responses.GET, ENDPOINT, json=[], status=200)
    list(build_client().iter_rows())
    assert "X-App-Token" not in responses.calls[0].request.headers


@responses.activate
def test_requests_stable_ordering():
    # Without an explicit $order, SODA pagination can repeat or skip rows.
    responses.add(responses.GET, ENDPOINT, json=[], status=200)

    list(build_client().iter_rows())

    assert "%24order=%3Aid" in responses.calls[0].request.url


def test_backoff_honors_retry_after_header():
    client = build_client()
    assert client._backoff_seconds(0, retry_after="5") == 5.0


def test_backoff_caps_hostile_retry_after():
    # A server sending a huge Retry-After must not stall ingestion indefinitely.
    client = build_client()
    assert client._backoff_seconds(0, retry_after="99999") == 30.0


def test_backoff_ignores_non_numeric_retry_after():
    # Retry-After may be an HTTP-date; fall back to computed backoff rather than crash.
    client = build_client()
    delay = client._backoff_seconds(0, retry_after="Wed, 21 Oct 2026 07:28:00 GMT")
    assert 0 <= delay <= 0.5


def test_backoff_grows_exponentially_and_stays_capped():
    client = build_client()
    # Full jitter means each delay is bounded by an exponentially growing cap.
    assert client._backoff_seconds(0) <= 0.5
    assert client._backoff_seconds(3) <= 4.0
    assert client._backoff_seconds(99) <= 8.0
