"use client";

import dynamic from "next/dynamic";
import { Component, useEffect, useId, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { GeocodeResult } from "@/lib/api/types";

import { formatPoint, isInIndia, parseCoordinate, type LatLng } from "./geo";

// Leaflet (and its CSS) load only in the browser, and only once the map is on screen.
const LeafletMap = dynamic(() => import("./LeafletMap"), {
  ssr: false,
  loading: () => <MapMessage>Loading the map…</MapMessage>,
});

type Mode = "map" | "text";
type Fallback = "tiles" | "script" | "chosen";

const FALLBACK_REASONS: Record<Fallback, string> = {
  tiles: "The map couldn't load. Enter the coordinates instead, or try the map again.",
  script: "The map couldn't load. Enter the coordinates instead, or try the map again.",
  chosen: "Enter the coordinates, for example from Google Maps or your phone's map app.",
};

function MapMessage({ children }: { children: React.ReactNode }) {
  return <div className="map__message">{children}</div>;
}

/** If the map's code fails to load (offline, blocked), fall back to text. */
class MapBoundary extends Component<{ onError: () => void; children: React.ReactNode }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch() {
    this.props.onError();
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}

/** True once the element has scrolled into view (or at once without IntersectionObserver). */
function useOnScreen(ref: React.RefObject<HTMLElement | null>): boolean {
  const [seen, setSeen] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (seen || !ref.current) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) setSeen(true);
      },
      { rootMargin: "200px" },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [ref, seen]);
  return seen;
}

function searchMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429)
      return "Too many searches in a row. Wait a few seconds and try again.";
    if (error.status === 503) return "Place search is down right now. Drag the pin instead.";
    if (error.isValidation) return "Type a place name, address or landmark.";
  }
  return "Search didn't work. Drag the pin instead, or try again.";
}

export type LocationPickerProps = {
  value: LatLng | null;
  onChange: (point: LatLng) => void;
  /** Called with the place a search found, e.g. to fill in the city. */
  onPlaceFound?: (place: GeocodeResult) => void;
  /** Starting text for the search box, e.g. the address typed so far. */
  suggestedQuery?: string;
  error?: string;
};

/**
 * Pick a point on an OpenStreetMap map: search for a place (the backend geocoder,
 * only when the person asks), then drag the pin to the exact spot. Typed coordinates
 * work too, and take over when the map can't load.
 */
export function LocationPicker({
  value,
  onChange,
  onPlaceFound,
  suggestedQuery = "",
  error,
}: LocationPickerProps) {
  const ids = useId();
  const wrapper = useRef<HTMLDivElement>(null);
  const onScreen = useOnScreen(wrapper);
  const [mode, setMode] = useState<Mode>("map");
  const [fallback, setFallback] = useState<Fallback>("chosen");
  const [mapAttempt, setMapAttempt] = useState(0);

  const [query, setQuery] = useState(suggestedQuery);
  const [searching, setSearching] = useState(false);
  const [status, setStatus] = useState("");

  const [latText, setLatText] = useState(value ? value.latitude.toFixed(6) : "");
  const [lngText, setLngText] = useState(value ? value.longitude.toFixed(6) : "");
  const [textError, setTextError] = useState("");

  function showText(reason: Fallback) {
    setFallback(reason);
    setMode("text");
    if (value) {
      setLatText(value.latitude.toFixed(6));
      setLngText(value.longitude.toFixed(6));
    }
  }

  function retryMap() {
    setMapAttempt((n) => n + 1);
    setMode("map");
  }

  function place(point: LatLng, announce: string) {
    onChange(point);
    setLatText(point.latitude.toFixed(6));
    setLngText(point.longitude.toFixed(6));
    setStatus(announce);
  }

  async function search() {
    const text = query.trim();
    if (!text || searching) return;
    setSearching(true);
    setStatus("Searching…");
    try {
      const result = await unwrap(api.POST("/api/v1/geo/geocode/", { body: { query: text } }));
      if (!result.found || result.latitude == null || result.longitude == null) {
        setStatus("We couldn't find that place. Try a nearby landmark, or drag the pin.");
        return;
      }
      place(
        { latitude: result.latitude, longitude: result.longitude },
        `Found ${result.display_name}. Drag the pin to the exact spot.`,
      );
      onPlaceFound?.(result);
    } catch (err) {
      setStatus(searchMessage(err));
    } finally {
      setSearching(false);
    }
  }

  function applyText() {
    const latitude = parseCoordinate(latText, "latitude");
    const longitude = parseCoordinate(lngText, "longitude");
    if (latitude == null || longitude == null) {
      setTextError("Enter a latitude and longitude as numbers, for example 15.5527 and 73.7517.");
      return;
    }
    if (!isInIndia({ latitude, longitude })) {
      setTextError("That point isn't in India. Check the numbers aren't swapped.");
      return;
    }
    setTextError("");
    place({ latitude, longitude }, `Pin set to ${formatPoint({ latitude, longitude })}.`);
  }

  return (
    <div className="map" ref={wrapper}>
      <div className="map__search">
        <label className="field__label" htmlFor={`${ids}-q`}>
          Search for the place
        </label>
        <div className="map__search-row">
          <input
            id={`${ids}-q`}
            className="field__control"
            type="search"
            value={query}
            placeholder="Property name, street or landmark"
            autoComplete="off"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void search();
              }
            }}
          />
          <Button
            variant="secondary"
            onClick={() => void search()}
            busy={searching}
            busyLabel="Searching…"
          >
            Search
          </Button>
        </div>
      </div>

      {mode === "map" ? (
        <div className="map__frame">
          {onScreen ? (
            <MapBoundary key={mapAttempt} onError={() => showText("script")}>
              <LeafletMap
                point={value}
                label="Map. Tap the map or drag the pin to the property's entrance."
                onMove={(point) => place(point, `Pin moved to ${formatPoint(point)}.`)}
                onTilesFailed={() => showText("tiles")}
              />
            </MapBoundary>
          ) : (
            <MapMessage>The map loads when you scroll to it.</MapMessage>
          )}
        </div>
      ) : (
        <fieldset className="map__fallback">
          <legend className="form-section__title">Coordinates</legend>
          <p className="field__hint">{FALLBACK_REASONS[fallback]}</p>
          <div className="form-grid">
            <div className="field">
              <label className="field__label" htmlFor={`${ids}-lat`}>
                Latitude
              </label>
              <input
                id={`${ids}-lat`}
                className="field__control"
                inputMode="decimal"
                value={latText}
                aria-invalid={textError ? true : undefined}
                aria-describedby={textError ? `${ids}-text-error` : undefined}
                onChange={(e) => setLatText(e.target.value)}
              />
            </div>
            <div className="field">
              <label className="field__label" htmlFor={`${ids}-lng`}>
                Longitude
              </label>
              <input
                id={`${ids}-lng`}
                className="field__control"
                inputMode="decimal"
                value={lngText}
                aria-invalid={textError ? true : undefined}
                aria-describedby={textError ? `${ids}-text-error` : undefined}
                onChange={(e) => setLngText(e.target.value)}
              />
            </div>
          </div>
          {textError ? (
            <p className="field__error" id={`${ids}-text-error`}>
              {textError}
            </p>
          ) : null}
          <div className="map__actions">
            <Button variant="secondary" onClick={applyText}>
              Use these coordinates
            </Button>
            <Button variant="ghost" onClick={retryMap}>
              {fallback === "chosen" ? "Back to the map" : "Try the map again"}
            </Button>
          </div>
        </fieldset>
      )}

      <div className="map__footer">
        <p className="map__point">
          {value ? (
            <>
              Pin: <span className="map__coords">{formatPoint(value)}</span>
            </>
          ) : (
            "No pin yet. Search for the place or tap the map."
          )}
        </p>
        {mode === "map" ? (
          <Button variant="ghost" onClick={() => showText("chosen")}>
            Enter coordinates instead
          </Button>
        ) : null}
      </div>
      <p className="map__status" role="status" aria-live="polite">
        {status}
      </p>
      {error ? <p className="field__error">{error}</p> : null}
    </div>
  );
}
