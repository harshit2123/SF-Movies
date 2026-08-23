/**
 * Debounce a rapidly-changing value.
 *
 * Autocomplete fires on every keystroke; without this, typing "bullitt" would
 * issue seven requests and race their responses. 250ms is below the threshold
 * where suggestions feel laggy, and above typical inter-keystroke timing.
 */

import { useEffect, useState } from "react";

export function useDebounced<T>(value: T, delayMs = 250): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
