"""
Admin registration.

Kept minimal — the admin exists here as a free inspection tool for ingested data
(useful when checking what a sync actually wrote), not as a management interface.
The data is read-only in practice; the sync command is the writer.
"""

from django.contrib import admin

from films.models import Film, FilmLocation


class FilmLocationInline(admin.TabularInline):
    model = FilmLocation
    extra = 0
    fields = ("location_text", "neighborhood", "is_mappable")
    readonly_fields = fields
    can_delete = False


@admin.register(Film)
class FilmAdmin(admin.ModelAdmin):
    list_display = ("title", "release_year", "director", "location_count")
    list_filter = ("release_year",)
    search_fields = ("title", "director", "writer")
    inlines = [FilmLocationInline]

    @admin.display(description="Locations")
    def location_count(self, obj: Film) -> int:
        return obj.locations.count()


@admin.register(FilmLocation)
class FilmLocationAdmin(admin.ModelAdmin):
    list_display = ("film", "location_text", "neighborhood", "is_mappable")
    list_filter = ("is_mappable", "neighborhood")
    search_fields = ("location_text", "film__title")
    # Identity is derived from content, never edited by hand.
    readonly_fields = ("content_hash",)
