/**
 * The map.
 *
 * Two layers with different jobs: the clustered backdrop of every matching location,
 * and — when a film is selected — that film's own locations drawn as a connected,
 * numbered route. The route is the signature element, so it gets the accent color and
 * everything else recedes.
 */

import { useEffect, useMemo } from "react";
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";
import L from "leaflet";

import type { FilmDetail, MapMarker } from "../../lib/api";
import { SF_CENTER } from "../../hooks/useGeolocation";

import "leaflet/dist/leaflet.css";
import "./map.css";

/*
 * Leaflet writes fill/stroke as inline SVG attributes, which beat a stylesheet
 * class. Marker colors therefore have to be passed as pathOptions; the token
 * values are mirrored here as the single source for map geometry.
 */
const COLOR_META = "#6b8f71";
const COLOR_ACCENT = "#d94f2a";
const COLOR_BASE = "#0e0e10";
const COLOR_TEXT = "#e8e4dc";

const BACKDROP_STYLE = {
  color: COLOR_BASE,
  weight: 1,
  fillColor: COLOR_META,
  fillOpacity: 0.55,
};

const ROUTE_STYLE = {
  color: COLOR_BASE,
  weight: 2,
  fillColor: COLOR_ACCENT,
  fillOpacity: 0.95,
};

const USER_STYLE = {
  color: COLOR_ACCENT,
  weight: 3,
  fillColor: COLOR_TEXT,
  fillOpacity: 0.9,
};

const ROUTE_LINE_STYLE = { color: COLOR_ACCENT, opacity: 0.75 };

interface MapViewProps {
  markers: MapMarker[];
  selectedFilm: FilmDetail | null;
  userPosition: { lat: number; lng: number } | null;
  /** Set when a filmstrip frame is clicked, so the map pans to that location. */
  focusedPoint: { lat: number; lng: number } | null;
  onSelectFilm: (slug: string) => void;
}

/** Pans to the selected film's locations so the route is always in view. */
function RouteFocus({ film }: { film: FilmDetail | null }) {
  const map = useMap();

  useEffect(() => {
    if (!film) return;
    const points = film.locations
      .filter((location) => location.is_mappable)
      .map((location) => [location.latitude!, location.longitude!] as [number, number]);

    if (points.length === 0) return;
    // The detail panel overlays the map — on the right at desktop widths, as a
    // bottom sheet below 900px. Pad on whichever edge it occupies so the route
    // is never hidden underneath it.
    // The panel overlaps the map — on the right at desktop widths, as a bottom
    // sheet below 900px. Measure the actual overlap rather than assuming a fixed
    // inset, so the route lands in pixels the user can actually see.
    const mapRect = map.getContainer().getBoundingClientRect();
    const panelRect = document
      .querySelector(".app__panel")
      ?.getBoundingClientRect();

    let padRight = 40;
    let padBottom = 40;
    if (panelRect) {
      const isSheet = window.matchMedia("(max-width: 900px)").matches;
      if (isSheet) {
        padBottom = Math.max(40, mapRect.bottom - panelRect.top + 20);
      } else {
        padRight = Math.max(40, mapRect.right - panelRect.left + 20);
      }
    }

    map.flyToBounds(L.latLngBounds(points), {
      paddingTopLeft: [40, 40],
      paddingBottomRight: [padRight, padBottom],
      maxZoom: 14,
      duration: 0.6,
    });
  }, [film, map]);

  return null;
}

/** Centers on the user once, when their position first arrives. */
function UserFocus({ position }: { position: { lat: number; lng: number } | null }) {
  const map = useMap();

  useEffect(() => {
    if (position) map.flyTo([position.lat, position.lng], 15, { duration: 0.6 });
  }, [position, map]);

  return null;
}

/** Pans to a single location when a filmstrip frame is clicked. */
function PointFocus({ point }: { point: { lat: number; lng: number } | null }) {
  const map = useMap();

  useEffect(() => {
    if (point) map.flyTo([point.lat, point.lng], 16, { duration: 0.5 });
  }, [point, map]);

  return null;
}

export function MapView({
  markers,
  selectedFilm,
  userPosition,
  focusedPoint,
  onSelectFilm,
}: MapViewProps) {
  // The route connects a film's locations in the order the source lists them.
  const routePoints = useMemo(() => {
    if (!selectedFilm) return [];
    return selectedFilm.locations
      .filter((location) => location.is_mappable)
      .map((location) => [location.latitude!, location.longitude!] as [number, number]);
  }, [selectedFilm]);

  // Hide the backdrop's copies of the selected film's markers, so the route's own
  // numbered markers are the only ones drawn for it.
  const backdropMarkers = useMemo(
    () =>
      selectedFilm
        ? markers.filter((marker) => marker.film_slug !== selectedFilm.slug)
        : markers,
    [markers, selectedFilm],
  );

  return (
    <MapContainer
      center={[SF_CENTER.lat, SF_CENTER.lng]}
      zoom={13}
      className="map"
      zoomControl={false}
      preferCanvas
    >
      {/* Muted basemap: the data is the subject, the streets are context. */}
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />

      <RouteFocus film={selectedFilm} />
      <UserFocus position={userPosition} />
      <PointFocus point={focusedPoint} />

      {/* Clustering is essential, not decorative: downtown holds hundreds of
          overlapping points that are unreadable and slow when drawn individually. */}
      <MarkerClusterGroup
        chunkedLoading
        maxClusterRadius={55}
        showCoverageOnHover={false}
        // react-leaflet-cluster ships no type for the cluster argument, and
        // @types/leaflet does not declare MarkerCluster; only getChildCount() is used.
        iconCreateFunction={(cluster: { getChildCount: () => number }) => {
          const count = cluster.getChildCount();
          const size = count > 100 ? "lg" : count > 20 ? "md" : "sm";
          return L.divIcon({
            html: `<span>${count}</span>`,
            className: `cluster cluster--${size}`,
            iconSize: L.point(36, 36),
          });
        }}
      >
        {backdropMarkers.map((marker) => (
          <CircleMarker
            key={marker.id}
            center={[marker.latitude, marker.longitude]}
            radius={5}
            className="marker"
            pathOptions={BACKDROP_STYLE}
            eventHandlers={{ click: () => onSelectFilm(marker.film_slug) }}
          >
            <Popup>
              <span className="popup__title">{marker.film_title}</span>
              <span className="popup__year">{marker.release_year ?? "—"}</span>
              <span className="popup__place">{marker.location_text}</span>
            </Popup>
          </CircleMarker>
        ))}
      </MarkerClusterGroup>

      {/* The signature: a film's locations as a connected, numbered route. */}
      {routePoints.length > 1 && (
        <Polyline
          positions={routePoints}
          className="route-line"
          pathOptions={{ ...ROUTE_LINE_STYLE, weight: 2, dashArray: "1 6", lineCap: "round" }}
        />
      )}

      {selectedFilm?.locations
        .filter((location) => location.is_mappable)
        .map((location, index) => (
          <CircleMarker
            key={location.id}
            center={[location.latitude!, location.longitude!]}
            radius={11}
            className="marker marker--route"
            pathOptions={ROUTE_STYLE}
          >
            <Popup>
              <span className="popup__index">Frame {index + 1}</span>
              <span className="popup__place">{location.location_text}</span>
              {location.neighborhood && (
                <span className="popup__meta">{location.neighborhood}</span>
              )}
            </Popup>
          </CircleMarker>
        ))}

      {userPosition && (
        <CircleMarker
          center={[userPosition.lat, userPosition.lng]}
          radius={8}
          className="marker--user"
          pathOptions={USER_STYLE}
        >
          <Popup>You are here</Popup>
        </CircleMarker>
      )}
    </MapContainer>
  );
}
