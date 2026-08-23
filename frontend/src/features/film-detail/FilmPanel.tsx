/**
 * Film detail, rendered as a filmstrip.
 *
 * This is the signature element. A film's locations are a sequence — the route the
 * production actually moved through — so they are numbered frames on a perforated
 * strip rather than a plain list. The numbering encodes something true about the
 * content; it is not decoration.
 */

import type { FilmDetail } from "../../lib/api";

import "./film-panel.css";

interface FilmPanelProps {
  film: FilmDetail;
  onClose: () => void;
  onFocusLocation: (locationId: number) => void;
}

export function FilmPanel({ film, onClose, onFocusLocation }: FilmPanelProps) {
  const mappable = film.locations.filter((location) => location.is_mappable);
  const unmappable = film.locations.length - mappable.length;
  const funFacts = film.locations.filter((location) => location.fun_facts);

  return (
    <aside className="panel" aria-label={`${film.title} details`}>
      <header className="panel__header">
        <div className="panel__titles">
          <h2 className="panel__title">{film.title}</h2>
          <span className="panel__year">{film.release_year ?? "Year unknown"}</span>
        </div>
        <button className="panel__close" onClick={onClose} aria-label="Close details">
          ✕
        </button>
      </header>

      <dl className="panel__credits">
        {film.director && (
          <>
            <dt>Director</dt>
            <dd>{film.director}</dd>
          </>
        )}
        {film.writer && (
          <>
            <dt>Writer</dt>
            <dd>{film.writer}</dd>
          </>
        )}
        {film.production_company && (
          <>
            <dt>Production</dt>
            <dd>{film.production_company}</dd>
          </>
        )}
        {film.actors.length > 0 && (
          <>
            <dt>Cast</dt>
            <dd>{film.actors.join(", ")}</dd>
          </>
        )}
      </dl>

      {funFacts.length > 0 && (
        <section className="panel__facts">
          <h3 className="panel__section-title">Fun facts</h3>
          {funFacts.map((location) => (
            <p key={location.id} className="panel__fact">
              {location.fun_facts}
            </p>
          ))}
        </section>
      )}

      <section className="strip">
        <h3 className="panel__section-title">
          Locations
          <span className="panel__count">
            {mappable.length} mapped
            {unmappable > 0 && ` · ${unmappable} without coordinates`}
          </span>
        </h3>

        {/* The strip itself: perforations run down both edges, frames between. */}
        <ol className="strip__reel">
          {mappable.map((location, index) => (
            <li key={location.id} className="strip__frame">
              <button
                className="strip__button"
                onClick={() => onFocusLocation(location.id)}
              >
                <span className="strip__number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="strip__body">
                  <span className="strip__place">{location.location_text}</span>
                  {location.neighborhood && (
                    <span className="strip__neighborhood">
                      {location.neighborhood}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ol>

        {unmappable > 0 && (
          <p className="strip__note">
            {unmappable} {unmappable === 1 ? "location is" : "locations are"} listed
            without coordinates in the source data and cannot be mapped.
          </p>
        )}
      </section>
    </aside>
  );
}
