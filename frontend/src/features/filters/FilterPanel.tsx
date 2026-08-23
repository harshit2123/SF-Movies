/**
 * Decade and neighborhood filters.
 *
 * Facet values come from the films response rather than a separate request
 * (ADR-0006), so this component renders whatever the dataset currently contains.
 */

import type { Facets } from "../../lib/api";

import "./filters.css";

interface FilterPanelProps {
  facets: Facets | undefined;
  decade: number | null;
  neighborhood: string | null;
  onDecadeChange: (decade: number | null) => void;
  onNeighborhoodChange: (neighborhood: string | null) => void;
}

export function FilterPanel({
  facets,
  decade,
  neighborhood,
  onDecadeChange,
  onNeighborhoodChange,
}: FilterPanelProps) {
  return (
    <div className="filters">
      <fieldset className="filters__group">
        <legend className="filters__legend">Decade</legend>
        <div className="filters__decades">
          {facets?.decades.map((value) => (
            <button
              key={value}
              className={`chip ${decade === value ? "chip--active" : ""}`}
              aria-pressed={decade === value}
              // Clicking the active decade clears it — no separate reset needed.
              onClick={() => onDecadeChange(decade === value ? null : value)}
            >
              {/* Full year, not a two-digit abbreviation: the dataset spans two
                  centuries, so "10s" would name both the 1910s and the 2010s. */}
              {value}s
            </button>
          ))}
        </div>
      </fieldset>

      <div className="filters__group">
        <label className="filters__legend" htmlFor="neighborhood">
          Neighborhood
        </label>
        <select
          id="neighborhood"
          className="filters__select"
          value={neighborhood ?? ""}
          onChange={(event) => onNeighborhoodChange(event.target.value || null)}
        >
          <option value="">All neighborhoods</option>
          {facets?.neighborhoods.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

    </div>
  );
}
