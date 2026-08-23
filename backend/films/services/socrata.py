"""
HTTP client for the DataSF Socrata (SODA v2) API.

This is the only outbound network caller in the project. It deliberately knows nothing
about Django models — it returns plain dicts, and `mapper.py` translates them. Keeping
that boundary means the retry/timeout behavior below can be tested against mocked HTTP
without touching the database.

Resilience covers the failure modes this API actually exhibits:
  - connection failures and read timeouts   → retry with exponential backoff
  - 5xx server errors                       → retry
  - 429 rate limiting                       → retry, honoring Retry-After when sent
  - 4xx client errors                       → fail immediately, retrying cannot help
  - malformed JSON                          → fail with context
"""

import logging
import random
import time
from typing import Any, Iterator

import requests

logger = logging.getLogger("films.socrata")


class SocrataError(Exception):
    """Base class for every failure originating from the Socrata API."""


class SocrataUnavailable(SocrataError):
    """The API could not be reached, or kept failing after every retry."""


class SocrataBadRequest(SocrataError):
    """The API rejected the request (4xx). Retrying will not help."""


# Retried: transient server-side or throttling conditions.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

BACKOFF_BASE_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 8.0
# Upper bound on a server-supplied Retry-After, so a hostile or buggy header
# cannot stall ingestion indefinitely.
RETRY_AFTER_CAP_SECONDS = 30.0


class SocrataClient:
    """
    Paginating, retrying client for a single Socrata dataset.

    Configuration is injected rather than read from settings here, so tests can
    construct a client with a 0-second backoff and no real network.
    """

    def __init__(
        self,
        base_url: str,
        dataset_id: str,
        app_token: str = "",
        timeout: int = 15,
        max_retries: int = 3,
        page_size: int = 1000,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.dataset_id = dataset_id
        self.app_token = app_token
        self.timeout = timeout
        self.max_retries = max_retries
        self.page_size = page_size
        self._session = session or requests.Session()
        # Injectable so tests do not actually wait through backoff.
        self._sleep = sleep

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/resource/{self.dataset_id}.json"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        # Unauthenticated requests work but are throttled harder. The token is
        # optional precisely so a fresh clone runs without one.
        if self.app_token:
            headers["X-App-Token"] = self.app_token
        return headers

    def _backoff_seconds(self, attempt: int, retry_after: str | None = None) -> float:
        """
        Exponential backoff with full jitter.

        Jitter matters even for a single client: without it, a retry storm against a
        recovering server arrives in a synchronized burst.
        """
        if retry_after:
            try:
                return min(float(retry_after), RETRY_AFTER_CAP_SECONDS)
            except ValueError:
                pass  # Header may be an HTTP-date; fall through to computed backoff.
        capped = min(BACKOFF_BASE_SECONDS * (2**attempt), BACKOFF_MAX_SECONDS)
        return random.uniform(0, capped)

    def _get(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Perform one GET with retries. Returns the decoded JSON list."""
        last_error: Exception | None = None
        retry_after: str | None = None

        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            retry_after = None
            try:
                response = self._session.get(
                    self.endpoint,
                    params=params,
                    headers=self._headers(),
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                # Connection refused, DNS failure, read timeout.
                last_error = exc
                logger.warning(
                    "socrata request failed attempt=%d/%d error=%s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
            else:
                elapsed_ms = (time.monotonic() - started) * 1000
                status = response.status_code

                if status == 200:
                    logger.info(
                        "socrata ok status=200 offset=%s duration_ms=%.0f",
                        params.get("$offset", 0),
                        elapsed_ms,
                    )
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        # A 200 with unparseable content is not transient.
                        raise SocrataUnavailable(
                            f"Socrata returned malformed JSON: {exc}"
                        ) from exc
                    if not isinstance(payload, list):
                        raise SocrataUnavailable(
                            f"Expected a JSON list, got {type(payload).__name__}"
                        )
                    return payload

                if status not in RETRYABLE_STATUS:
                    # 400/403/404 — the request itself is wrong. Retrying wastes time.
                    raise SocrataBadRequest(
                        f"Socrata rejected the request: HTTP {status} "
                        f"{response.text[:200]}"
                    )

                last_error = SocrataUnavailable(f"HTTP {status}")
                # Honored on 429; harmless when absent on 5xx.
                retry_after = response.headers.get("Retry-After")
                logger.warning(
                    "socrata retryable status=%d attempt=%d/%d duration_ms=%.0f",
                    status,
                    attempt + 1,
                    self.max_retries + 1,
                    elapsed_ms,
                )

            # Sleep between attempts, but never after the final one.
            if attempt < self.max_retries:
                delay = self._backoff_seconds(attempt, retry_after)
                logger.info("socrata backoff seconds=%.2f", delay)
                self._sleep(delay)

        raise SocrataUnavailable(
            f"Socrata unreachable after {self.max_retries + 1} attempts: {last_error}"
        )

    def iter_rows(self, limit: int | None = None) -> Iterator[dict[str, Any]]:
        """
        Yield every row in the dataset, paginating via $limit/$offset.

        Streaming rather than accumulating keeps memory flat and lets the caller
        report progress. `limit` caps the total for --limit and for tests.
        """
        offset = 0
        yielded = 0

        while True:
            page_size = self.page_size
            if limit is not None:
                remaining = limit - yielded
                if remaining <= 0:
                    return
                page_size = min(page_size, remaining)

            rows = self._get(
                {
                    "$limit": page_size,
                    "$offset": offset,
                    # Without an explicit order, SODA pagination may repeat or skip
                    # rows across pages. :id is the internal stable ordering key.
                    "$order": ":id",
                }
            )

            if not rows:
                return

            for row in rows:
                yield row
                yielded += 1

            # A short page means the dataset is exhausted.
            if len(rows) < page_size:
                return

            offset += len(rows)
