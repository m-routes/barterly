import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { gig, property } from "../../../../../../test/fixtures";
import { errorBody, jsonResponse } from "../../../../../../test/http";

import { GigBuilder } from "./GigBuilder";

vi.mock(
  "next/navigation",
  async () => (await import("../../../../../../test/navigation")).navigationMock,
);

const TODAY = "2026-11-14";
let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function requests() {
  return network.mock.calls.map((call) => call[0] as Request);
}

function renderBuilder(initialGig: typeof gig | null = null) {
  return render(
    <GigBuilder initialGig={initialGig} properties={[property]} skills={[]} today={TODAY} />,
  );
}

describe("GigBuilder", () => {
  it("saves a new draft once it has the basics, then updates it", async () => {
    network
      .mockResolvedValueOnce(jsonResponse(201, { ...gig, title: "Morning yoga teacher" }))
      .mockResolvedValueOnce(jsonResponse(200, { ...gig, title: "Morning yoga teacher" }));
    const replace = vi.spyOn(window.history, "replaceState");
    const user = userEvent.setup();
    renderBuilder();

    await user.click(screen.getByLabelText(/Specialist/));
    await user.type(screen.getByLabelText("Gig title"), "Morning yoga teacher");
    expect(screen.getByRole("status")).toHaveTextContent(/saves once it has a role, title/);
    // The preview follows the form.
    expect(screen.getByRole("article", { name: "Preview of your gig" })).toHaveTextContent(
      "Morning yoga teacher",
    );

    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByLabelText(/Stay plus stipend/));
    await waitFor(() => expect(network).toHaveBeenCalledTimes(1), { timeout: 3000 });
    const created = requests()[0]!;
    expect(created.method).toBe("POST");
    expect(new URL(created.url).pathname).toBe("/api/v1/gigs/");
    expect(await created.json()).toMatchObject({
      property: property.id,
      title: "Morning yoga teacher",
      role_template: "specialist",
      compensation_model: "hybrid",
      required_verification: "id_verified",
    });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/Draft saved at/));
    expect(replace).toHaveBeenCalledWith(null, "", `/console/gigs/${gig.id}/edit`);

    await user.type(screen.getByLabelText("Amount (₹)"), "6000");
    await waitFor(() => expect(network).toHaveBeenCalledTimes(2), { timeout: 3000 });
    const updated = requests()[1]!;
    expect(updated.method).toBe("PATCH");
    expect(new URL(updated.url).pathname).toBe(`/api/v1/gigs/${gig.id}/`);
    expect(await updated.json()).toMatchObject({ stipend_amount: "6000.00" });
  });

  it("explains rule breaks inline and doesn't save them", async () => {
    const user = userEvent.setup();
    renderBuilder(gig);
    const hours = screen.getByLabelText(/Hours per day/);
    await user.clear(hours);
    await user.type(hours, "8");

    expect(screen.getByText("At most 6 hours a day.")).toBeVisible();
    expect(hours).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("status")).toHaveTextContent("Fix the highlighted fields to save.");
    await new Promise((r) => setTimeout(r, 1500));
    expect(network).not.toHaveBeenCalled();
  });

  it("lists what's missing on review and jumps back to fix it", async () => {
    const user = userEvent.setup();
    renderBuilder({ ...gig, description: "" });
    await user.click(screen.getByRole("button", { name: /5 Review/ }));

    expect(screen.getByRole("heading", { name: "1 thing to fix before review" })).toBeVisible();
    expect(screen.getByText(/Description:/).parentElement).toHaveTextContent(
      "Required before the gig can be reviewed.",
    );
    await user.click(screen.getByRole("button", { name: "Fix in Basics" }));
    expect(screen.getByRole("heading", { level: 2, name: "Basics" })).toBeVisible();
    expect(screen.getByLabelText(/Description/)).toHaveAttribute("aria-invalid", "true");
  });

  it("submits a complete draft for review", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, { ...gig, status: "in_review" }));
    const user = userEvent.setup();
    renderBuilder(gig);
    await user.click(screen.getByRole("button", { name: /5 Review/ }));
    expect(screen.getByText(/Everything's filled in/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByRole("heading", { name: "Sent for review" })).toBeVisible();
    // Nothing changed, so no save first: just the status change.
    expect(network).toHaveBeenCalledTimes(1);
    const request = requests()[0]!;
    expect(new URL(request.url).pathname).toBe(`/api/v1/gigs/${gig.id}/status/`);
    expect(await request.json()).toEqual({ status: "in_review" });
  });

  it("shows the API's reasons when review is refused", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(
        400,
        errorBody("validation_error", "Invalid input.", {
          apply_by: ["The apply-by date has passed."],
        }),
      ),
    );
    const user = userEvent.setup();
    renderBuilder(gig);
    await user.click(screen.getByRole("button", { name: /5 Review/ }));
    await user.click(screen.getByRole("button", { name: "Submit for review" }));

    expect(await screen.findByText("The apply-by date has passed.")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent("Fix the items listed above first.");
  });

  it("saves a live gig only on request, and warns when that sends it back to review", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(200, { ...gig, status: "in_review", hours_per_day: 5 }),
    );
    const user = userEvent.setup();
    renderBuilder({ ...gig, status: "live" });
    const hours = screen.getByLabelText(/Hours per day/);
    await user.clear(hours);
    await user.type(hours, "5");

    expect(screen.getByText(/Saving sends this gig back to review/)).toBeVisible();
    await new Promise((r) => setTimeout(r, 1500));
    expect(network).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(network).toHaveBeenCalledTimes(1));
    expect(requests()[0]!.method).toBe("PATCH");
  });

  it("won't edit a closed gig", () => {
    renderBuilder({ ...gig, status: "closed" });
    expect(screen.getByText(/can't be edited/)).toBeVisible();
    expect(screen.getByRole("link", { name: "See its applicants" })).toHaveAttribute(
      "href",
      `/console/gigs/${gig.id}/applicants`,
    );
  });
});
