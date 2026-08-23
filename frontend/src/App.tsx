/**
 * Application shell.
 *
 * Owns the composition — URL state in, queries out, panels arranged around the map.
 * Feature components stay presentational; data fetching lives in the query hooks.
 */

import { useMemo, useState } from "react";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { FilmPanel } from "./features/film-detail/FilmPanel";
import { FilterPanel } from "./features/filters/FilterPanel";
import { MapLegend } from "./features/map/MapLegend";
import { MapView } from "./features/map/MapView";
import { SearchAutocomplete } from "./features/search/SearchAutocomplete";
import { useGeolocation } from "./hooks/useGeolocation";
import { useUrlState } from "./hooks/useUrlState";
import { useFilm, useFilms, useHealth, useMarkers, useNearby } from "./lib/queries";

import "./styles/app.css";

/** Radius for the "filmed near me" view. Walking distance, roughly. */
const NEARBY_RADIUS_KM = 1.5;

export default function App() {
  const { state, update, reset } = useUrlState();
  const geo = useGeolocation();

  const filters = useMemo(
    () => ({
      search: state.search,
      decade: state.decade,
      neighborhood: state.neighborhood,
    }),
    [state.search, state.decade, state.neighborhood],
  );

  const health = useHealth();
  const films = useFilms(filters);
  const markers = useMarkers(filters);
  const selectedFilm = useFilm(state.film);
  const nearby = useNearby(
    state.nearby ? geo.position : null,
    NEARBY_RADIUS_KM,
  );

  // In nearby mode the map shows only what is within walking distance.
  const visibleMarkers = state.nearby && nearby.data ? nearby.data : markers.data ?? [];

  const toggleNearby = () => {
    if (state.nearby) {
      update({ nearby: false });
      geo.clear();
      return;
    }
    geo.locate();
    update({ nearby: true });
  };

  // Clicking a frame in the filmstrip pans the map to that location.
  const [focusedLocationId, setFocusedLocationId] = useState<number | null>(null);

  const focusedPoint = useMemo(() => {
    const location = selectedFilm.data?.locations.find(
      (candidate) => candidate.id === focusedLocationId,
    );
    return location?.is_mappable
      ? { lat: location.latitude!, lng: location.longitude! }
      : null;
  }, [selectedFilm.data, focusedLocationId]);

  const apiUnreachable = health.isError;

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__brand">
          <span className="app__mark" aria-hidden="true" />
          <h1 className="app__title">SF on Film</h1>
        </div>
        <p className="app__tagline">
          A century of filming locations across San Francisco, 1915&ndash;2025
        </p>
        {health.data && (
          <p className="app__stats">
            <span>{health.data.film_count} films</span>
            <span>{health.data.mappable_count} locations</span>
          </p>
        )}
      </header>

      <aside className="app__sidebar">
        <SearchAutocomplete
          value={state.search}
          onChange={(search) => update({ search })}
          onSelectFilm={(film) => {
            update({ film });
            setFocusedLocationId(null);
          }}
        />

        <FilterPanel
          facets={films.data?.facets}
          decade={state.decade}
          neighborhood={state.neighborhood}
          nearbyActive={state.nearby}
          locating={geo.status === "locating"}
          onDecadeChange={(decade) => update({ decade })}
          onNeighborhoodChange={(neighborhood) => update({ neighborhood })}
          onToggleNearby={toggleNearby}
        />

        {geo.message && <p className="app__notice">{geo.message}</p>}

        <p className="app__result-count">
          {markers.isFetching && !markers.data
            ? "Loading locations…"
            : `${visibleMarkers.length} locations shown`}
          {(state.search || state.decade || state.neighborhood || state.nearby) && (
            <button className="app__clear" onClick={reset}>
              Clear
            </button>
          )}
        </p>

        <MapLegend hasSelection={Boolean(selectedFilm.data)} />
      </aside>

      <main className="app__map">
        {apiUnreachable ? (
          <div className="app__offline" role="alert">
            <p className="app__offline-title">The API is not responding.</p>
            <p className="app__offline-detail">
              Start the backend with <code>python manage.py runserver</code>, then
              reload.
            </p>
          </div>
        ) : (
          <ErrorBoundary region="map">
            <MapView
              markers={visibleMarkers}
              selectedFilm={selectedFilm.data ?? null}
              userPosition={state.nearby ? geo.position : null}
              focusedPoint={focusedPoint}
              isFiltered={Boolean(
                state.neighborhood || state.decade || state.search,
              )}
              onSelectFilm={(film) => update({ film })}
            />
          </ErrorBoundary>
        )}
      </main>

      {selectedFilm.data && (
        <div className="app__panel">
          <ErrorBoundary region="details panel">
            <FilmPanel
              film={selectedFilm.data}
              onClose={() => {
                update({ film: null });
                setFocusedLocationId(null);
              }}
              onFocusLocation={setFocusedLocationId}
            />
          </ErrorBoundary>
        </div>
      )}
    </div>
  );
}
