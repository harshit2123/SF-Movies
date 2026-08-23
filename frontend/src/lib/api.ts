/**
 * Typed client for the films API.
 *
 * Types are hand-written against docs/API.md rather than generated from an OpenAPI
 * schema — the SPA is the only consumer, so a build-time generation step would add
 * tooling without adding safety (ADR-0006).
 */

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// --- Response shapes -------------------------------------------------------

export interface FilmSummary {
  slug: string;
  title: string;
  release_year: number | null;
  director: string;
  actors: string[];
  location_count: number;
  mappable_count: number;
}

export interface AutocompleteItem {
  slug: string;
  title: string;
  release_year: number | null;
  location_count: number;
}

export interface FilmLocation {
  id: number;
  location_text: string;
  latitude: number | null;
  longitude: number | null;
  is_mappable: boolean;
  neighborhood: string;
  supervisor_district: string;
  fun_facts: string;
}

export interface FilmDetail {
  slug: string;
  title: string;
  release_year: number | null;
  director: string;
  writer: string;
  production_company: string;
  distributor: string;
  actors: string[];
  locations: FilmLocation[];
}

export interface MapMarker {
  id: number;
  film_slug: string;
  film_title: string;
  release_year: number | null;
  location_text: string;
  latitude: number;
  longitude: number;
  neighborhood: string;
}

export interface NearbyMarker extends MapMarker {
  distance_km: number;
}

export interface Facets {
  decades: number[];
  neighborhoods: string[];
}

export interface FilmListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  facets: Facets;
  results: FilmSummary[];
}

export interface Health {
  status: "ok" | "degraded";
  film_count: number;
  location_count: number;
  mappable_count: number;
  last_sync: string | null;
}

// --- Fetch layer -----------------------------------------------------------

/** Surfaces the HTTP status so callers can distinguish a 404 from an outage. */
export class ApiError extends Error {
  // Declared explicitly rather than as a constructor parameter property, which
  // `erasableSyntaxOnly` disallows.
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type QueryValue = string | number | boolean | null | undefined;

function buildUrl(path: string, params: Record<string, QueryValue> = {}): string {
  const url = new URL(path, BASE_URL);
  for (const [key, value] of Object.entries(params)) {
    // Empty filters are omitted rather than sent as blanks, so the backend's
    // "unset" branch and the frontend's agree.
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

async function request<T>(
  path: string,
  params: Record<string, QueryValue> = {},
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(path, params), { signal });
  } catch (cause) {
    // Distinguish a genuine network failure from an HTTP error response, so the
    // UI can tell "the API is unreachable" from "that film does not exist".
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError("Cannot reach the API. Is the backend running?", 0);
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // Non-JSON error body; the status-based message above stands.
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}

// --- Endpoints -------------------------------------------------------------

export interface FilmFilters {
  search?: string;
  decade?: number | null;
  neighborhood?: string | null;
  person?: string;
}

export const api = {
  films: (filters: FilmFilters = {}, signal?: AbortSignal) =>
    request<FilmListResponse>("/api/films/", { ...filters }, signal),

  autocomplete: (q: string, signal?: AbortSignal) =>
    request<AutocompleteItem[]>("/api/films/autocomplete/", { q }, signal),

  film: (slug: string, signal?: AbortSignal) =>
    request<FilmDetail>(`/api/films/${slug}/`, {}, signal),

  markers: (filters: FilmFilters & { film?: string } = {}, signal?: AbortSignal) =>
    request<MapMarker[]>("/api/locations/", { ...filters }, signal),

  nearby: (
    lat: number,
    lng: number,
    radiusKm: number,
    signal?: AbortSignal,
  ) =>
    request<NearbyMarker[]>(
      "/api/locations/nearby/",
      { lat, lng, radius_km: radiusKm },
      signal,
    ),

  health: (signal?: AbortSignal) => request<Health>("/api/health/", {}, signal),
};
