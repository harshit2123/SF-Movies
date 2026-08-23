/**
 * The map.
 *
 * Two layers with different jobs: the clustered backdrop of every matching location,
 * and — when a film is selected — that film's own locations drawn as a connected,
 * numbered route. The route is the signature element, so it gets the accent color and
 * everything else recedes.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Marker,
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

const USER_STYLE = {
  color: COLOR_ACCENT,
  weight: 3,
  fillColor: COLOR_TEXT,
  fillOpacity: 0.9,
};

const ROUTE_LINE_STYLE = { color: COLOR_ACCENT, opacity: 0.75 };

/** Opening view, and the view returned to when nearby mode is switched off. */
const DEFAULT_ZOOM = 13;

interface MapViewProps {
  markers: MapMarker[];
  selectedFilm: FilmDetail | null;
  userPosition: { lat: number; lng: number } | null;
  /** Set when a filmstrip frame is clicked, so the map pans to that location. */
  focusedPoint: { lat: number; lng: number } | null;
  /** True while a filter narrows the map, so the view refits to the results. */
  isFiltered: boolean;
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

/**
 * Centers on the user when their position arrives, and returns to the city when
 * they leave nearby mode.
 *
 * The return leg matters: without it, turning nearby off left the map wherever
 * the user happened to be — often nowhere near San Francisco — showing an empty
 * view of the correct data.
 */
function UserFocus({ position }: { position: { lat: number; lng: number } | null }) {
  const map = useMap();
  const wasLocated = useRef(false);

  useEffect(() => {
    if (position) {
      wasLocated.current = true;
      map.flyTo([position.lat, position.lng], 15, { duration: 0.6 });
      return;
    }
    // Only fly back if we had actually moved away, so this does not fight the
    // initial view or a film route on first load.
    if (wasLocated.current) {
      wasLocated.current = false;
      map.flyTo([SF_CENTER.lat, SF_CENTER.lng], DEFAULT_ZOOM, { duration: 0.6 });
    }
  }, [position, map]);

  return null;
}

/**
 * Frames the visible markers when a filter changes.
 *
 * Selecting a neighborhood previously filtered the data without moving the map,
 * so choosing somewhere off-screen looked like it had done nothing. This fits the
 * view to whatever the current filters actually matched.
 */
function FilterFocus({
  markers,
  enabled,
}: {
  markers: MapMarker[];
  enabled: boolean;
}) {
  const map = useMap();

  useEffect(() => {
    if (!enabled || markers.length === 0) return;

    const bounds = L.latLngBounds(
      markers.map((m) => [m.latitude, m.longitude] as [number, number]),
    );
    map.flyToBounds(bounds, {
      paddingTopLeft: [40, 40],
      paddingBottomRight: [40, 40],
      maxZoom: 15,
      duration: 0.6,
    });
    // Keyed on the marker set, so it refits whenever the filters change what
    // is shown — but not on every render.
  }, [markers, enabled, map]);

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

/**
 * Zoom at which markers stop being anonymous dots and start carrying film names.
 * Below this the labels would collide into an unreadable mat; at or above it there
 * is enough room between points for a name to be worth more than a dot.
 */
const LABEL_ZOOM = 16;

/** Tracks zoom so the marker layer can switch between dots and named labels. */
function useZoomLevel(): number {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());

  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom());
    map.on("zoomend", onZoom);
    return () => {
      map.off("zoomend", onZoom);
    };
  }, [map]);

  return zoom;
}

/**
 * The backdrop layer.
 *
 * Below LABEL_ZOOM these are quiet dots — texture that shows where the city was
 * filmed. At street level they become named labels, because a dot you have to
 * click to identify is not telling you anything.
 */
function BackdropMarkers({
  markers,
  onSelectFilm,
}: {
  markers: MapMarker[];
  onSelectFilm: (slug: string) => void;
}) {
  const zoom = useZoomLevel();
  const labelled = zoom >= LABEL_ZOOM;

  if (labelled) {
    return (
      <>
        {markers.map((marker) => (
          <Marker
            key={marker.id}
            position={[marker.latitude, marker.longitude]}
            icon={L.divIcon({
              className: "pin",
              // The name is the point; the year disambiguates remakes and seasons.
              html: `<span class="pin__dot"></span><span class="pin__label">${escapeHtml(
                marker.film_title,
              )}<em>${marker.release_year ?? ""}</em></span>`,
              iconSize: [10, 10],
              iconAnchor: [5, 5],
            })}
            eventHandlers={{ click: () => onSelectFilm(marker.film_slug) }}
          >
            <Popup>
              <span className="popup__title">{marker.film_title}</span>
              <span className="popup__year">{marker.release_year ?? "—"}</span>
              <span className="popup__place">{marker.location_text}</span>
            </Popup>
          </Marker>
        ))}
      </>
    );
  }

  return (
    <>
      {markers.map((marker) => (
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
    </>
  );
}

/** Film titles come from an external dataset and go into an HTML string. */
function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[char]!,
  );
}

export function MapView({
  markers,
  selectedFilm,
  userPosition,
  focusedPoint,
  isFiltered,
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
      zoom={DEFAULT_ZOOM}
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
      <FilterFocus
        markers={markers}
        enabled={isFiltered && !selectedFilm && !userPosition}
      />
      <PointFocus point={focusedPoint} />

      {/* Clustering is essential, not decorative: downtown holds hundreds of
          overlapping points that are unreadable and slow when drawn individually. */}
      <MarkerClusterGroup
        chunkedLoading
        // Stop clustering at street level: a badge reading "2" tells the user
        // nothing a pair of named pins would not tell them better.
        disableClusteringAtZoom={LABEL_ZOOM}
        spiderfyOnMaxZoom={false}
        maxClusterRadius={55}
        showCoverageOnHover={false}
        // react-leaflet-cluster ships no type for the cluster argument, and
        // @types/leaflet does not declare MarkerCluster; only getChildCount() is used.
        iconCreateFunction={(cluster: { getChildCount: () => number }) => {
          const count = cluster.getChildCount();
          const size = count > 100 ? "lg" : count > 20 ? "md" : "sm";
          return L.divIcon({
            // "shoots" names the unit, so the badge reads as a quantity of
            // something rather than an unexplained number.
            html: `<span class="cluster__count">${count}</span><span class="cluster__unit">shoots</span>`,
            className: `cluster cluster--${size}`,
            iconSize: L.point(36, 36),
          });
        }}
      >
        <BackdropMarkers
          markers={backdropMarkers}
          onSelectFilm={onSelectFilm}
        />
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
          <Marker
            key={location.id}
            position={[location.latitude!, location.longitude!]}
            icon={L.divIcon({
              className: "frame",
              // The frame number is the sequence; the place name identifies it
              // without a click, matching the filmstrip in the panel.
              html:
                `<span class="frame__badge">${index + 1}</span>` +
                `<span class="frame__label">${escapeHtml(
                  location.location_text,
                )}</span>`,
              iconSize: [24, 24],
              iconAnchor: [12, 12],
            })}
          >
            <Popup>
              <span className="popup__index">Frame {index + 1}</span>
              <span className="popup__place">{location.location_text}</span>
              {location.neighborhood && (
                <span className="popup__meta">{location.neighborhood}</span>
              )}
            </Popup>
          </Marker>
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
