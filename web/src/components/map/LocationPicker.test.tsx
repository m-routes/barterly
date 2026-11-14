import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse } from "../../../test/http";

import type { LatLng } from "./geo";
import { LocationPicker } from "./LocationPicker";

// The real map needs a browser with layout; stand in a fake that exposes its callbacks.
vi.mock("./LeafletMap", () => ({
  default: (props: {
    point: LatLng | null;
    onMove: (p: LatLng) => void;
    onTilesFailed: () => void;
  }) => (
    <div data-testid="map">
      <span>{props.point ? `map pin ${props.point.latitude}` : "map without pin"}</span>
      <button type="button" onClick={() => props.onMove({ latitude: 15.5, longitude: 73.8 })}>
        drag pin
      </button>
      <button type="button" onClick={props.onTilesFailed}>
        fail tiles
      </button>
    </div>
  ),
}));

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function Harness({ onPlaceFound }: { onPlaceFound?: () => void }) {
  const [point, setPoint] = useState<LatLng | null>(null);
  return <LocationPicker value={point} onChange={setPoint} onPlaceFound={onPlaceFound} />;
}

describe("LocationPicker", () => {
  it("searches only when asked, then drops the pin there", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(200, {
        found: true,
        latitude: 15.0099,
        longitude: 74.0232,
        display_name: "Palolem Beach, Goa",
        city: "Canacona",
        state: "Goa",
        postcode: "403702",
      }),
    );
    const onPlaceFound = vi.fn();
    const user = userEvent.setup();
    render(<Harness onPlaceFound={onPlaceFound} />);

    await user.type(screen.getByLabelText("Search for the place"), "Palolem beach");
    expect(network).not.toHaveBeenCalled(); // never per keystroke
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText(/Found Palolem Beach, Goa/)).toBeVisible();
    expect(screen.getByText("15.009900, 74.023200")).toBeVisible();
    const request = network.mock.calls[0]![0] as Request;
    expect(new URL(request.url).pathname).toBe("/api/v1/geo/geocode/");
    expect(await request.json()).toEqual({ query: "Palolem beach" });
    expect(onPlaceFound).toHaveBeenCalledWith(expect.objectContaining({ city: "Canacona" }));
  });

  it("says when nothing was found, and when the search is rate limited", async () => {
    network
      .mockResolvedValueOnce(
        jsonResponse(200, {
          found: false,
          latitude: null,
          longitude: null,
          display_name: "",
          city: "",
          state: "",
          postcode: "",
        }),
      )
      .mockResolvedValueOnce(jsonResponse(429, errorBody("throttled", "Too many requests.")));
    const user = userEvent.setup();
    render(<Harness />);
    const box = screen.getByLabelText("Search for the place");
    await user.type(box, "nowhere{Enter}");
    expect(await screen.findByText(/couldn't find that place/)).toBeVisible();
    await user.type(box, " again{Enter}");
    expect(await screen.findByText(/Too many searches/)).toBeVisible();
  });

  it("moves the pin when the map reports a drag", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(await screen.findByRole("button", { name: "drag pin" }));
    expect(screen.getByText("15.500000, 73.800000")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Pin moved to 15.500000, 73.800000.");
  });

  it("falls back to typed coordinates when the tiles fail, and checks them", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(await screen.findByRole("button", { name: "fail tiles" }));

    expect(screen.queryByTestId("map")).toBeNull();
    expect(screen.getByText(/The map couldn't load/)).toBeVisible();
    await user.type(screen.getByLabelText("Latitude"), "73.75");
    await user.type(screen.getByLabelText("Longitude"), "15.55");
    await user.click(screen.getByRole("button", { name: "Use these coordinates" }));
    expect(screen.getByText(/isn't in India/)).toBeVisible();
    expect(screen.getByLabelText("Latitude")).toHaveAttribute("aria-invalid", "true");

    await user.clear(screen.getByLabelText("Latitude"));
    await user.clear(screen.getByLabelText("Longitude"));
    await user.type(screen.getByLabelText("Latitude"), "15.55");
    await user.type(screen.getByLabelText("Longitude"), "73.75");
    await user.click(screen.getByRole("button", { name: "Use these coordinates" }));
    expect(screen.getByText("15.550000, 73.750000")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Try the map again" }));
    expect(await screen.findByText("map pin 15.55")).toBeVisible();
  });

  it("offers coordinates instead of the map at any time", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Enter coordinates instead" }));
    expect(screen.getByText(/for example from Google Maps/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Back to the map" })).toBeVisible();
  });
});
