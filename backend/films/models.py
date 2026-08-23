"""
Data model for the DataSF Film Locations dataset.

The source is flat — one row per (film, location) pair, with film details repeated
across every row for the same film. That denormalization is undone here: 2,214 source
rows become 350 `Film` records and 2,214 `FilmLocation` records.
"""

import hashlib

from django.db import models
from django.utils.text import slugify


class Film(models.Model):
    """A film, deduplicated from the repeated film columns in the source rows."""

    # Natural key: title alone collides (remakes, series seasons), so the slug
    # incorporates the release year.
    slug = models.SlugField(max_length=255, unique=True)

    title = models.CharField(max_length=255, db_index=True)
    release_year = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    director = models.CharField(max_length=255, blank=True)
    writer = models.CharField(max_length=255, blank=True)
    production_company = models.CharField(max_length=255, blank=True)
    distributor = models.CharField(max_length=255, blank=True)

    # Source spreads cast across actor_1..actor_3; normalized into one list so the
    # API and search do not have to know about the column-per-actor shape.
    actors = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["title", "release_year"]
        indexes = [models.Index(fields=["release_year", "title"])]

    def __str__(self) -> str:
        return f"{self.title} ({self.release_year or 'year unknown'})"

    @staticmethod
    def build_slug(title: str, release_year: int | None) -> str:
        """Deterministic slug. Same inputs always produce the same value."""
        base = slugify(title) or "untitled"
        return f"{base}-{release_year}" if release_year else base

    @property
    def decade(self) -> int | None:
        return (self.release_year // 10) * 10 if self.release_year else None


class FilmLocationQuerySet(models.QuerySet):
    def mappable(self) -> "FilmLocationQuerySet":
        """Only locations that can be plotted — excludes the 86 coordinate-less rows."""
        return self.filter(is_mappable=True)


class FilmLocation(models.Model):
    """
    One filming location for one film.

    Coordinates come straight from DataSF, which publishes them for 2,128 of 2,214
    rows (ADR-0001). The remaining 86 are kept with `is_mappable=False` rather than
    dropped: they stay searchable and visible in film detail, but never reach the map.
    """

    film = models.ForeignKey(Film, on_delete=models.CASCADE, related_name="locations")

    location_text = models.CharField(max_length=512, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    # Denormalized from (latitude, longitude) so map queries filter on one indexed
    # boolean instead of scattering null checks across every consumer.
    is_mappable = models.BooleanField(default=False, db_index=True)

    neighborhood = models.CharField(max_length=255, blank=True, db_index=True)
    supervisor_district = models.CharField(max_length=16, blank=True)
    fun_facts = models.TextField(blank=True)

    # Socrata exposes no stable row id, so identity is derived from content
    # (ADR-0001). This is what makes re-running the sync idempotent.
    content_hash = models.CharField(max_length=64, unique=True, editable=False)

    # Source freshness, passed through from DataSF and surfaced by /api/health/.
    data_as_of = models.DateTimeField(null=True, blank=True)

    objects = FilmLocationQuerySet.as_manager()

    class Meta:
        ordering = ["film__title", "location_text"]
        indexes = [
            # Bounding-box viewport queries and the nearby prefilter.
            models.Index(fields=["latitude", "longitude"]),
            models.Index(fields=["is_mappable", "neighborhood"]),
        ]

    def __str__(self) -> str:
        return f"{self.film.title} — {self.location_text or 'location unknown'}"

    @staticmethod
    def build_content_hash(
        title: str, release_year: int | None, location_text: str
    ) -> str:
        """
        Stable identity for a source row.

        These three fields are what distinguishes one row from another in the source
        data. Deliberately excludes mutable detail columns (director, actors, coordinates)
        so that a corrected value upstream updates the existing row instead of creating
        a duplicate.
        """
        raw = f"{title.strip().lower()}|{release_year or ''}|{location_text.strip().lower()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
