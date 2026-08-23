/**
 * Search box with an autocomplete listbox.
 *
 * Implements the ARIA combobox pattern: arrow keys move through options, Enter
 * selects, Escape closes. Keyboard operation is not optional — this is the primary
 * way into the dataset.
 */

import { useEffect, useId, useRef, useState } from "react";

import { useAutocomplete } from "../../lib/queries";
import { useDebounced } from "../../hooks/useDebounced";

import "./search.css";

interface SearchAutocompleteProps {
  value: string;
  onChange: (term: string) => void;
  onSelectFilm: (slug: string) => void;
}

export function SearchAutocomplete({
  value,
  onChange,
  onSelectFilm,
}: SearchAutocompleteProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  const debounced = useDebounced(value);
  const { data: suggestions = [], isFetching } = useAutocomplete(debounced);

  // Close when focus or a click leaves the combobox.
  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  // A changed result set invalidates the highlighted index.
  useEffect(() => setActiveIndex(-1), [suggestions]);

  const select = (slug: string, title: string) => {
    onChange(title);
    onSelectFilm(slug);
    setIsOpen(false);
    setActiveIndex(-1);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!isOpen || suggestions.length === 0) return;

    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActiveIndex((i) => (i + 1) % suggestions.length);
        break;
      case "ArrowUp":
        event.preventDefault();
        setActiveIndex((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
        break;
      case "Enter": {
        event.preventDefault();
        const choice = suggestions[activeIndex] ?? suggestions[0];
        if (choice) select(choice.slug, choice.title);
        break;
      }
      case "Escape":
        setIsOpen(false);
        setActiveIndex(-1);
        break;
    }
  };

  const showList = isOpen && debounced.trim().length >= 2;

  return (
    <div className="search" ref={containerRef}>
      <label className="search__label" htmlFor="film-search">
        Search
      </label>

      <div className="search__field">
        <input
          id="film-search"
          type="search"
          className="search__input"
          placeholder="Try Bullitt, Vertigo, or Eastwood"
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={onKeyDown}
          role="combobox"
          aria-expanded={showList}
          aria-controls={listboxId}
          aria-autocomplete="list"
          aria-activedescendant={
            activeIndex >= 0 ? `${listboxId}-option-${activeIndex}` : undefined
          }
          autoComplete="off"
        />
        {isFetching && <span className="search__spinner" aria-hidden="true" />}
      </div>

      {showList && (
        <ul className="search__listbox" id={listboxId} role="listbox">
          {suggestions.length === 0 && !isFetching && (
            // An empty result is a dead end; say so plainly rather than showing nothing.
            <li className="search__empty">No films match “{debounced}”.</li>
          )}

          {suggestions.map((film, index) => (
            <li
              key={film.slug}
              id={`${listboxId}-option-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              className={`search__option ${
                index === activeIndex ? "search__option--active" : ""
              }`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={(event) => {
                // mousedown, not click: the input's blur would close the list first.
                event.preventDefault();
                select(film.slug, film.title);
              }}
            >
              <span className="search__option-title">{film.title}</span>
              <span className="search__option-meta">
                {film.release_year ?? "—"}
                <span className="search__option-count">
                  {film.location_count} loc
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
