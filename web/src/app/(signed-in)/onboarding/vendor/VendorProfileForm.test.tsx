import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse } from "../../../../../test/http";

import type { VendorProfile } from "@/lib/api/types";

import { VendorProfileForm } from "./VendorProfileForm";

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const saved = {
  id: "p1",
  business_name: "Zostel Manali",
  business_type: "hostel",
  contact_name: "Asha",
  city: "Manali",
  state: "Himachal Pradesh",
  about: "A hostel in the hills.",
  address: "",
  gstin: "",
  website: "",
  profile_complete: true,
  missing_fields: [] as string[],
  created_at: "2026-11-13T10:00:00Z",
  updated_at: "2026-11-13T10:00:00Z",
} satisfies VendorProfile;

async function fillRequired() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Business name"), "Zostel Manali");
  await user.selectOptions(screen.getByLabelText("Business type"), "hostel");
  await user.type(screen.getByLabelText(/About your place/), "A hostel in the hills.");
  await user.type(screen.getByLabelText(/Contact name/), "Asha");
  await user.type(screen.getByLabelText("City or town"), "Manali");
  await user.selectOptions(screen.getByLabelText("State or union territory"), "Himachal Pradesh");
  return user;
}

describe("VendorProfileForm", () => {
  it("shows every missing required field and doesn't call the API", async () => {
    const user = userEvent.setup();
    render(<VendorProfileForm initial={null} onSaved={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(await screen.findByText("Enter your business name.")).toBeVisible();
    expect(screen.getByText("Choose your business type.")).toBeVisible();
    expect(screen.getByText("Choose your state or union territory.")).toBeVisible();
    expect(screen.getByLabelText("Business name")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Business name")).toHaveFocus();
    expect(network).not.toHaveBeenCalled();
  });

  it("PATCHes the cleaned values and reports the saved profile", async () => {
    network.mockResolvedValueOnce(jsonResponse(201, saved));
    const onSaved = vi.fn();
    render(<VendorProfileForm initial={null} onSaved={onSaved} />);
    const user = await fillRequired();
    await user.type(screen.getByLabelText(/GSTIN/), "29abcde1234f1z5");
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    await vi.waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    const request = network.mock.calls[0]![0] as Request;
    expect(request.method).toBe("PATCH");
    expect(new URL(request.url).pathname).toBe("/api/v1/profiles/vendor/me/");
    expect(await request.json()).toMatchObject({
      business_name: "Zostel Manali",
      business_type: "hostel",
      state: "Himachal Pradesh",
      gstin: "29ABCDE1234F1Z5",
    });
  });

  it("puts the API's field errors on the matching fields", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(
        400,
        errorBody("validation_error", "Invalid input.", { city: ["Not a city we know."] }),
      ),
    );
    render(<VendorProfileForm initial={null} onSaved={vi.fn()} />);
    const user = await fillRequired();
    await user.click(screen.getByRole("button", { name: "Create profile" }));

    expect(await screen.findByText("Not a city we know.")).toBeVisible();
    expect(screen.getByLabelText("City or town")).toHaveAttribute("aria-invalid", "true");
  });

  it("shows other failures above the button", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(409, errorBody("profile_removed", "This profile was removed. Contact support.")),
    );
    render(<VendorProfileForm initial={null} onSaved={vi.fn()} />);
    const user = await fillRequired();
    await user.click(screen.getByRole("button", { name: "Create profile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This profile was removed.");
  });

  it("starts from the saved profile when editing", () => {
    render(<VendorProfileForm initial={saved} onSaved={vi.fn()} />);
    expect(screen.getByLabelText("Business name")).toHaveValue("Zostel Manali");
    expect(screen.getByLabelText("State or union territory")).toHaveValue("Himachal Pradesh");
    expect(screen.getByRole("button", { name: "Save profile" })).toBeVisible();
  });
});
