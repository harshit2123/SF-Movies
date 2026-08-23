"""
Sync film locations from DataSF.

    python manage.py sync_film_locations
    python manage.py sync_film_locations --dry-run
    python manage.py sync_film_locations --limit 50

Safe to re-run: identity is derived from row content, so an immediate second run
reports zero creates and zero updates (ADR-0001).

Scheduling is left to the host rather than a task queue (ADR-0006). A nightly crontab
entry would read:

    0 3 * * * cd /app && python manage.py sync_film_locations >> /var/log/sync.log 2>&1
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from films.services.ingest import ingest_rows
from films.services.socrata import SocrataClient, SocrataError


class Command(BaseCommand):
    help = "Fetch film locations from the DataSF Socrata API and upsert them."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Exercise the full write path, then roll back. Changes nothing.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Stop after N rows. Useful for a quick smoke test.",
        )

    def handle(self, *args, **options) -> None:
        dry_run: bool = options["dry_run"]
        limit: int | None = options["limit"]

        config = settings.SOCRATA
        client = SocrataClient(
            base_url=config["BASE_URL"],
            dataset_id=config["DATASET_ID"],
            app_token=config["APP_TOKEN"],
            timeout=config["TIMEOUT_SECONDS"],
            max_retries=config["MAX_RETRIES"],
            page_size=config["PAGE_SIZE"],
        )

        self.stdout.write(f"Fetching from {client.endpoint}")
        if not config["APP_TOKEN"]:
            self.stdout.write(
                self.style.WARNING(
                    "No SOCRATA_APP_TOKEN set — requests are throttled harder. "
                    "Fine at this volume."
                )
            )
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no changes will persist"))

        started = time.monotonic()
        try:
            report = ingest_rows(client.iter_rows(limit=limit), dry_run=dry_run)
        except SocrataError as exc:
            # Surface upstream failures as a clean command error rather than a
            # traceback: this runs unattended from cron.
            raise CommandError(f"Sync failed: {exc}") from exc

        elapsed = time.monotonic() - started

        self.stdout.write("")
        self.stdout.write(f"  rows fetched        {report.fetched}")
        self.stdout.write(
            f"  films               +{report.films_created} created, "
            f"{report.films_updated} updated"
        )
        self.stdout.write(
            f"  locations           +{report.locations_created} created, "
            f"{report.locations_updated} updated, "
            f"{report.locations_unchanged} unchanged"
        )
        if report.duplicate_rows:
            self.stdout.write(
                f"  duplicate rows      {report.duplicate_rows} "
                f"(same identity, conflicting detail upstream)"
            )
        if report.skipped:
            self.stdout.write(
                self.style.WARNING(f"  skipped             {report.skipped}")
            )
            for reason in report.skip_reasons[:5]:
                self.stdout.write(f"      - {reason}")
        self.stdout.write(f"  duration            {elapsed:.1f}s")
        self.stdout.write("")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete — rolled back."))
        elif report.is_idempotent_run and report.fetched:
            self.stdout.write(
                self.style.SUCCESS("Already up to date — nothing changed.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Sync complete."))
