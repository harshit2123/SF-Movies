/**
 * Filter state lives in the URL.
 *
 * Search, filters, and the selected film are all shareable and survive a reload,
 * and the back button steps through them. This is one hook rather than a router
 * dependency — the app is a single view, so a router would only be managing query
 * parameters, which URLSearchParams already does.
 */

import { useCallback, useEffect, useState } from "react";

export interface AppState {
  search: string;
  decade: number | null;
  neighborhood: string | null;
  film: string | null;
}

const EMPTY: AppState = {
  search: "",
  decade: null,
  neighborhood: null,
  film: null,
};

function parse(searchParams: URLSearchParams): AppState {
  const decade = searchParams.get("decade");
  return {
    search: searchParams.get("search") ?? "",
    // A malformed ?decade=abc reads as "no filter" rather than NaN.
    decade: decade && !Number.isNaN(Number(decade)) ? Number(decade) : null,
    neighborhood: searchParams.get("neighborhood"),
    film: searchParams.get("film"),
  };
}

function serialize(state: AppState): string {
  const params = new URLSearchParams();
  if (state.search) params.set("search", state.search);
  if (state.decade !== null) params.set("decade", String(state.decade));
  if (state.neighborhood) params.set("neighborhood", state.neighborhood);
  if (state.film) params.set("film", state.film);
  return params.toString();
}

export function useUrlState() {
  const [state, setState] = useState<AppState>(() =>
    parse(new URLSearchParams(window.location.search)),
  );

  // Keep the app in step with browser navigation.
  useEffect(() => {
    const onPopState = () =>
      setState(parse(new URLSearchParams(window.location.search)));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const update = useCallback((patch: Partial<AppState>) => {
    setState((current) => {
      const next = { ...current, ...patch };
      const query = serialize(next);
      const url = query ? `?${query}` : window.location.pathname;
      // pushState, so each filter change is a back-button step.
      window.history.pushState(null, "", url);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    window.history.pushState(null, "", window.location.pathname);
    setState(EMPTY);
  }, []);

  return { state, update, reset };
}
