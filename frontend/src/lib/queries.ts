/**
 * TanStack Query hooks.
 *
 * The dataset changes only when the sync command runs (ADR-0003), so cached data
 * is treated as fresh for a long time rather than refetched on every focus change.
 */

import { useQuery } from "@tanstack/react-query";

import { api, type FilmFilters } from "./api";

/** The data is a batch snapshot; an hour of staleness is well inside its lifetime. */
const STALE_TIME = 60 * 60 * 1000;

export const queryKeys = {
  markers: (filters: FilmFilters & { film?: string }) =>
    ["markers", filters] as const,
  autocomplete: (q: string) => ["autocomplete", q] as const,
  film: (slug: string) => ["film", slug] as const,
  films: (filters: FilmFilters) => ["films", filters] as const,
  health: () => ["health"] as const,
};

export function useMarkers(filters: FilmFilters & { film?: string }) {
  return useQuery({
    queryKey: queryKeys.markers(filters),
    queryFn: ({ signal }) => api.markers(filters, signal),
    staleTime: STALE_TIME,
    // Markers are the map's backdrop; keeping the previous set visible while a
    // filter change loads avoids the whole map blanking on every keystroke.
    placeholderData: (previous) => previous,
  });
}

export function useAutocomplete(term: string) {
  return useQuery({
    queryKey: queryKeys.autocomplete(term),
    queryFn: ({ signal }) => api.autocomplete(term, signal),
    // Mirrors the backend's minimum; below it the endpoint returns [] anyway.
    enabled: term.trim().length >= 2,
    staleTime: STALE_TIME,
  });
}

export function useFilm(slug: string | null) {
  return useQuery({
    queryKey: queryKeys.film(slug ?? ""),
    queryFn: ({ signal }) => api.film(slug!, signal),
    enabled: Boolean(slug),
    staleTime: STALE_TIME,
  });
}

export function useFilms(filters: FilmFilters) {
  return useQuery({
    queryKey: queryKeys.films(filters),
    queryFn: ({ signal }) => api.films(filters, signal),
    staleTime: STALE_TIME,
    placeholderData: (previous) => previous,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: ({ signal }) => api.health(signal),
    staleTime: STALE_TIME,
    retry: 1,
  });
}
