/**
 * Legend and orientation hints.
 *
 * The map's symbols are not self-explanatory: a badge reading "483" is
 * meaningless until you know it counts shoots, and nothing signals that zooming
 * turns dots into named pins. This says both, in the sidebar, without requiring
 * a click.
 */

import "./legend.css";

interface MapLegendProps {
  /** Hints change once a film is selected — the route needs explaining then. */
  hasSelection: boolean;
}

export function MapLegend({ hasSelection }: MapLegendProps) {
  return (
    <section className="legend" aria-label="Map key">
      <h2 className="legend__title">Map key</h2>

      <ul className="legend__items">
        <li className="legend__item">
          <span className="legend__swatch legend__swatch--cluster">24</span>
          <span className="legend__text">
            Shoots in this area. Zoom in to split it apart.
          </span>
        </li>

        <li className="legend__item">
          <span className="legend__swatch legend__swatch--dot" />
          <span className="legend__text">
            One filming location. Zoom past street level to see film names.
          </span>
        </li>

        {hasSelection && (
          <li className="legend__item">
            <span className="legend__swatch legend__swatch--frame">1</span>
            <span className="legend__text">
              A stop on the selected film&rsquo;s route, numbered in order.
            </span>
          </li>
        )}
      </ul>

      <p className="legend__hint">
        {hasSelection
          ? "Click a frame in the list to fly to it."
          : "Click any marker, or search above, to trace a film’s locations."}
      </p>
    </section>
  );
}
