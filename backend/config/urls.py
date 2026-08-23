"""
URL routing. Every application route is namespaced under /api/.

The Django admin is deliberately not routed. It is genuinely useful for
inspecting ingested data locally — `admin.py` keeps its registrations, and
adding the path back is a one-line change — but the deployed site is public,
and shipping a login form for an account nobody holds is surface with no
purpose. Data is written by the sync command, never through the admin.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from films import views

router = DefaultRouter()
router.register(r"films", views.FilmViewSet, basename="film")

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/locations/", views.MapMarkerListView.as_view(), name="locations"),
    path("api/locations/nearby/", views.nearby_locations, name="locations-nearby"),
    path("api/health/", views.health, name="health"),
]
