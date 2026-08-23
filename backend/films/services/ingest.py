"""
Ingestion: fetch rows, map them, upsert into the database.

Idempotency is the property that matters here. Running the sync twice against
unchanged upstream data must report zero creates and zero updates — that is what
makes the command safe to schedule and safe to re-run after a partial failure.

Identity comes from `FilmLocation.content_hash` rather than a source row id, because
Socrata does not expose a stable one (ADR-0001).
"""

import logging
from dataclasses import dataclass, field
from typing import Iterable

from django.db import transaction

from films.models import Film, FilmLocation
from films.services.mapper import MalformedRecord, MappedRow, map_row

logger = logging.getLogger("films.ingest")


@dataclass
class SyncReport:
    """Outcome of a sync run. Logged as a summary and returned for tests."""

    fetched: int = 0
    films_created: int = 0
    films_updated: int = 0
    locations_created: int = 0
    locations_updated: int = 0
    locations_unchanged: int = 0
    skipped: int = 0
    # Source rows that collapse to an identity already seen this run — upstream
    # duplicates, not errors. Reported so the count stays visible rather than silent.
    duplicate_rows: int = 0
    skip_reasons: list[str] = field(default_factory=list)

    @property
    def is_idempotent_run(self) -> bool:
        """True when nothing changed — the expected result of an immediate re-run."""
        return (
            self.films_created == 0
            and self.locations_created == 0
            and self.locations_updated == 0
        )

    def summary(self) -> str:
        return (
            f"fetched={self.fetched} "
            f"films(created={self.films_created} updated={self.films_updated}) "
            f"locations(created={self.locations_created} "
            f"updated={self.locations_updated} unchanged={self.locations_unchanged}) "
            f"duplicates={self.duplicate_rows} skipped={self.skipped}"
        )


# Film fields that a later row may fill in or correct.
_FILM_FIELDS = ("director", "writer", "production_company", "distributor")

# Location fields compared to decide whether an update is needed.
_LOCATION_FIELDS = (
    "latitude",
    "longitude",
    "is_mappable",
    "neighborhood",
    "supervisor_district",
    "fun_facts",
    "data_as_of",
)


def _upsert_film(mapped: MappedRow, report: SyncReport, seen: set[str]) -> Film:
    """
    Get or create the film for this row.

    Source rows repeat film detail for every location, and those repetitions are not
    always complete — one row may carry a director while another leaves it blank. Only
    non-empty incoming values overwrite, so a blank never erases known data.

    The source also contradicts itself: `summertime-2015` reports five different
    distributors across its rows ("4 Distribution", "7 Distribution", …), and
    `golden-gate-1994` is two distinct films sharing a title and year. Left unguarded,
    whichever row came last would win, and the winner would change between runs —
    making the sync report permanent phantom updates.

    `seen` holds the slugs already written during *this* run, so the first row for a
    film establishes its detail and later contradicting rows are ignored. First-write-
    wins is arbitrary but deterministic, which is what idempotency requires.
    """
    slug = Film.build_slug(mapped.title, mapped.release_year)
    film, created = Film.objects.get_or_create(
        slug=slug,
        defaults={
            "title": mapped.title,
            "release_year": mapped.release_year,
            "director": mapped.director,
            "writer": mapped.writer,
            "production_company": mapped.production_company,
            "distributor": mapped.distributor,
            "actors": mapped.actors,
        },
    )

    if created:
        report.films_created += 1
        seen.add(slug)
        return film

    # A later row for a film already handled this run is a self-contradiction in the
    # source, not new information. Ignore it.
    if slug in seen:
        return film
    seen.add(slug)

    changed = [
        f
        for f in _FILM_FIELDS
        if (incoming := getattr(mapped, f)) and getattr(film, f) != incoming
    ]
    # Cast lists can also be partial across rows; keep the fullest seen.
    if mapped.actors and len(mapped.actors) > len(film.actors):
        changed.append("actors")

    if changed:
        for f in changed:
            setattr(film, f, getattr(mapped, f))
        film.save(update_fields=changed)
        report.films_updated += 1

    return film


def _upsert_location(
    film: Film, mapped: MappedRow, report: SyncReport, seen: set[str]
) -> None:
    """
    Create or update one location, keyed on its content hash.

    As with films, the source contains rows that collapse to the same identity while
    disagreeing on detail — 7 of 2,214 rows, differing in `fun_facts`. `seen` applies
    the same first-write-wins rule so repeat runs stay stable.
    """
    content_hash = FilmLocation.build_content_hash(
        mapped.title, mapped.release_year, mapped.location_text
    )

    location, created = FilmLocation.objects.get_or_create(
        content_hash=content_hash,
        defaults={
            "film": film,
            "location_text": mapped.location_text,
            "latitude": mapped.latitude,
            "longitude": mapped.longitude,
            "is_mappable": mapped.is_mappable,
            "neighborhood": mapped.neighborhood,
            "supervisor_district": mapped.supervisor_district,
            "fun_facts": mapped.fun_facts,
            "data_as_of": mapped.data_as_of,
        },
    )

    if created:
        report.locations_created += 1
        seen.add(content_hash)
        return

    if content_hash in seen:
        # Duplicate row within this run; already handled above.
        report.duplicate_rows += 1
        return
    seen.add(content_hash)

    changed = [f for f in _LOCATION_FIELDS if getattr(location, f) != getattr(mapped, f)]
    if changed:
        for f in changed:
            setattr(location, f, getattr(mapped, f))
        location.save(update_fields=changed)
        report.locations_updated += 1
    else:
        report.locations_unchanged += 1


def ingest_rows(rows: Iterable[dict], dry_run: bool = False) -> SyncReport:
    """
    Ingest an iterable of raw Socrata rows.

    A malformed row is logged and skipped — one bad record must never abort a run that
    would otherwise import 2,213 good ones. The whole run is wrapped in a transaction so
    an unexpected failure leaves no partial state, and `dry_run` reuses that transaction
    by rolling it back, which means a dry run exercises the real write path rather than
    a simulated one.
    """
    report = SyncReport()
    # Identities already written during this run, enforcing first-write-wins over
    # the source's self-contradictions. See `_upsert_film`.
    seen_films: set[str] = set()
    seen_locations: set[str] = set()

    with transaction.atomic():
        for raw in rows:
            report.fetched += 1
            try:
                mapped = map_row(raw)
            except MalformedRecord as exc:
                report.skipped += 1
                # Bounded, so a systematically broken feed cannot exhaust memory.
                if len(report.skip_reasons) < 20:
                    report.skip_reasons.append(str(exc))
                logger.warning("skipping row: %s", exc)
                continue

            film = _upsert_film(mapped, report, seen_films)
            _upsert_location(film, mapped, report, seen_locations)

        if dry_run:
            logger.info("dry run — rolling back")
            transaction.set_rollback(True)

    logger.info("sync complete %s", report.summary())
    return report
