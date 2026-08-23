/**
 * Browser geolocation for the "filmed near me" feature.
 *
 * Permission is requested only when the user asks for it, never on load — an
 * unprompted location prompt on first paint is hostile, and most visitors to a
 * San Francisco film map are not in San Francisco.
 */

import { useCallback, useState } from "react";

export interface Coordinates {
  lat: number;
  lng: number;
}

/** Downtown SF — the fallback when geolocation is denied or unavailable. */
export const SF_CENTER: Coordinates = { lat: 37.7793, lng: -122.4193 };

type Status = "idle" | "locating" | "granted" | "denied" | "unavailable";

export function useGeolocation() {
  const [status, setStatus] = useState<Status>("idle");
  const [position, setPosition] = useState<Coordinates | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const locate = useCallback(() => {
    if (!("geolocation" in navigator)) {
      setStatus("unavailable");
      setMessage("This browser cannot share your location.");
      return;
    }

    setStatus("locating");
    setMessage(null);

    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setPosition({ lat: coords.latitude, lng: coords.longitude });
        setStatus("granted");
      },
      (error) => {
        setStatus("denied");
        // Say what happened and what to do, in the interface's voice.
        setMessage(
          error.code === error.PERMISSION_DENIED
            ? "Location access is blocked. Allow it in your browser settings, or explore the map directly."
            : "Could not determine your location. Try again, or explore the map directly.",
        );
      },
      { timeout: 10_000, maximumAge: 60_000 },
    );
  }, []);

  const clear = useCallback(() => {
    setPosition(null);
    setStatus("idle");
    setMessage(null);
  }, []);

  return { status, position, message, locate, clear };
}
