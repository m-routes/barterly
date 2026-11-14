import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { photo, property } from "../../../../../test/fixtures";
import { errorBody, jsonResponse } from "../../../../../test/http";

import { PropertyVerification } from "./PropertyVerification";

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PropertyVerification", () => {
  it("lists what's missing and keeps the button disabled", () => {
    render(
      <PropertyVerification
        property={{ ...property, location_confirmed: false, photos: [photo({ latitude: null })] }}
        onStatus={vi.fn()}
      />,
    );
    expect(screen.getByText("Place the map pin and confirm it.")).toBeVisible();
    expect(screen.getByText(/Add at least 3 photos \(you have 1\)/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Request verification" })).toBeDisabled();
  });

  it("sends a ready property and reports the new status", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, { status: "submitted" }));
    const onStatus = vi.fn();
    render(
      <PropertyVerification
        property={{ ...property, photos: [photo(), photo(), photo()] }}
        onStatus={onStatus}
      />,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Request verification" }));
    await vi.waitFor(() => expect(onStatus).toHaveBeenCalledWith("submitted"));
    const request = network.mock.calls[0]![0] as Request;
    expect(new URL(request.url).pathname).toBe(`/api/v1/properties/${property.id}/verification/`);
  });

  it("shows the API's reasons", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(
        400,
        errorBody("validation_error", "Invalid input.", {
          photos: ["These photos weren't taken within 200 m of the pin: ph-1."],
        }),
      ),
    );
    render(
      <PropertyVerification
        property={{ ...property, photos: [photo(), photo(), photo()] }}
        onStatus={vi.fn()}
      />,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "Request verification" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("within 200 m of the pin");
  });

  it("just shows the status while it's being checked", () => {
    render(
      <PropertyVerification
        property={{ ...property, verification_status: "in_review" }}
        onStatus={vi.fn()}
      />,
    );
    expect(screen.getByText("In review")).toBeVisible();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
