"""URL routing. Every application route is namespaced under /api/."""

from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from films import views

router = DefaultRouter()
router.register(r"films", views.FilmViewSet, basename="film")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/locations/", views.MapMarkerListView.as_view(), name="locations"),
    path("api/locations/nearby/", views.nearby_locations, name="locations-nearby"),
    path("api/health/", views.health, name="health"),
]
