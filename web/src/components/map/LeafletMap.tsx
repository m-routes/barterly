"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useRef } from "react";

import {
  ATTRIBUTION,
  INDIA_CENTER,
  INDIA_ZOOM,
  MAX_ZOOM,
  PIN_ZOOM,
  TILE_URL,
  type LatLng,
} from "./geo";

/** Tiles that may fail before any loads, and how long to wait for the first one. */
const FAILED_TILES_BEFORE_GIVING_UP = 4;
const FIRST_TILE_TIMEOUT_MS = 12_000;

// A CSS pin instead of Leaflet's default marker images (no image paths to bundle).
const PIN_ICON = L.divIcon({
  className: "map-pin",
  html: '<span class="map-pin__head"></span>',
  iconSize: [32, 40],
  iconAnchor: [16, 40],
});

export type LeafletMapProps = {
  point: LatLng | null;
  /** The person dragged the pin or tapped the map. */
  onMove: (point: LatLng) => void;
  /** No tiles could be loaded (offline, blocked, or the tile server is down). */
  onTilesFailed: () => void;
  label: string;
};

/**
 * Leaflet map with one draggable pin. Loaded only on the client and only when needed
 * (see LocationPicker), so Leaflet stays out of every other page's bundle.
 */
export default function LeafletMap({ point, onMove, onTilesFailed, label }: LeafletMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const marker = useRef<L.Marker | null>(null);
  // Keep the latest callbacks without re-creating the map.
  const callbacks = useRef({ onMove, onTilesFailed });
  useEffect(() => {
    callbacks.current = { onMove, onTilesFailed };
  });

  // Create the map once.
  useEffect(() => {
    if (!container.current) return;
    const start = point ?? INDIA_CENTER;
    const instance = L.map(container.current, {
      center: [start.latitude, start.longitude],
      zoom: point ? PIN_ZOOM : INDIA_ZOOM,
      scrollWheelZoom: false, // the page scrolls; zoom with the buttons or pinch
    });
    instance.attributionControl.setPrefix(false);

    let loaded = 0;
    let failed = 0;
    let gaveUp = false;
    const giveUp = () => {
      if (gaveUp || loaded > 0) return;
      gaveUp = true;
      callbacks.current.onTilesFailed();
    };
    const timer = window.setTimeout(giveUp, FIRST_TILE_TIMEOUT_MS);
    L.tileLayer(TILE_URL, { attribution: ATTRIBUTION, maxZoom: MAX_ZOOM })
      .on("tileload", () => {
        loaded += 1;
        window.clearTimeout(timer);
      })
      .on("tileerror", () => {
        failed += 1;
        if (failed >= FAILED_TILES_BEFORE_GIVING_UP) giveUp();
      })
      .addTo(instance);

    instance.on("click", (event: L.LeafletMouseEvent) => {
      callbacks.current.onMove({ latitude: event.latlng.lat, longitude: event.latlng.lng });
    });
    map.current = instance;
    return () => {
      window.clearTimeout(timer);
      instance.remove();
      map.current = null;
      marker.current = null;
    };
    // The map is created once; later points are applied by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Show the pin where the form says it is.
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    if (!point) {
      marker.current?.remove();
      marker.current = null;
      return;
    }
    const at = L.latLng(point.latitude, point.longitude);
    if (!marker.current) {
      marker.current = L.marker(at, {
        draggable: true,
        icon: PIN_ICON,
        title: "Property location: drag to adjust",
        alt: "Property location",
        autoPan: true,
      })
        .on("dragend", () => {
          const moved = marker.current!.getLatLng();
          callbacks.current.onMove({ latitude: moved.lat, longitude: moved.lng });
        })
        .addTo(instance);
      instance.setView(at, Math.max(instance.getZoom(), PIN_ZOOM));
      return;
    }
    if (!marker.current.getLatLng().equals(at)) {
      marker.current.setLatLng(at);
      if (!instance.getBounds().contains(at)) {
        instance.setView(at, Math.max(instance.getZoom(), PIN_ZOOM));
      }
    }
  }, [point]);

  return <div ref={container} className="map__canvas" role="region" aria-label={label} />;
}
