import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OfferThread } from "@/lib/api/types";

import { application, offer, offerThread, terms } from "../../../../../test/fixtures";
import { errorBody, jsonResponse } from "../../../../../test/http";

import { OfferPanel } from "./OfferPanel";

let thread: OfferThread;
let network: ReturnType<typeof vi.fn>;
const onChange = vi.fn();

function calls(method: string, suffix: string) {
  return network.mock.calls
    .map((c) => c[0] as Request)
    .filter((r) => r.method === method && new URL(r.url).pathname.endsWith(suffix));
}

beforeEach(() => {
  thread = offerThread();
  network = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname;
    if (path.endsWith("/offers/")) return jsonResponse(200, thread);
    if (path.endsWith("/offer-draft/")) return jsonResponse(200, terms);
    if (path.endsWith("/offer/") && request.method === "POST") {
      const body = (await request.clone().json()) as { terms: { hours_per_day: number } };
      if (body.terms.hours_per_day > 6) {
        return jsonResponse(
          400,
          errorBody("validation_error", "Check the highlighted fields.", {
            hours_per_day: ["Ensure this value is less than or equal to 6."],
          }),
        );
      }
      return jsonResponse(201, thread);
    }
    if (path.endsWith("/decline/") || path.endsWith("/accept/")) return jsonResponse(200, thread);
    return jsonResponse(404, errorBody("not_found"));
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
  onChange.mockReset();
});

describe("OfferPanel", () => {
  it("makes an offer from the gig's terms, edited", async () => {
    const user = userEvent.setup();
    render(
      <OfferPanel application={{ ...application, status: "shortlisted" }} onChange={onChange} />,
    );
    await user.click(await screen.findByRole("button", { name: "Make an offer" }));
    const hours = await screen.findByLabelText(/Hours a day/);
    expect(hours).toHaveValue(4);
    await user.clear(hours);
    await user.type(hours, "3");
    await user.type(screen.getByLabelText(/Message/), "See you in December");
    await user.click(screen.getByRole("button", { name: "Send offer" }));

    await vi.waitFor(() => expect(onChange).toHaveBeenCalled());
    const body = (await calls("POST", "/offer/")[0]!.json()) as {
      terms: typeof terms;
      message: string;
    };
    expect(body.terms.hours_per_day).toBe(3);
    expect(body.terms.usage_rights?.scope).toBe("organic");
    expect(body.message).toBe("See you in December");
  });

  it("shows the API's field errors", async () => {
    const user = userEvent.setup();
    render(<OfferPanel application={{ ...application, status: "applied" }} onChange={onChange} />);
    await user.click(await screen.findByRole("button", { name: "Make an offer" }));
    const hours = await screen.findByLabelText(/Hours a day/);
    await user.clear(hours);
    await user.type(hours, "8");
    await user.click(screen.getByRole("button", { name: "Send offer" }));
    expect(await screen.findByText("Ensure this value is less than or equal to 6.")).toBeVisible();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("highlights a counter and keeps the original offer", async () => {
    const user = userEvent.setup();
    const original = offer({ status: "countered" });
    const counter = offer({
      id: "of-2",
      revision: 2,
      proposed_by: "talent",
      mine: false,
      final: true,
      counter_of: original.id,
      changed_fields: ["stipend_amount"],
      message: "Could it be 7,000?",
      terms: { ...terms, stipend_amount: "7000.00" },
    });
    thread = offerThread({ offers: [original, counter], open_offer: "of-2", your_turn: true });
    render(<OfferPanel application={{ ...application, status: "offered" }} onChange={onChange} />);

    const card = (await screen.findByRole("heading", { name: "They asked for a change" })).closest(
      "li",
    )!;
    expect(within(card).getByText("“Could it be 7,000?”")).toBeVisible();
    expect(within(card).getByText("Changed")).toBeVisible();
    expect(within(card).getByText("₹7,000 per month")).toBeVisible();

    await user.type(within(card).getByLabelText(/Message if you decline/), "Budget is fixed");
    await user.click(within(card).getByRole("button", { name: "Keep my offer" }));
    await vi.waitFor(() => expect(onChange).toHaveBeenCalled());
    const declined = calls("POST", "/offers/of-2/decline/")[0]!;
    expect(await declined.json()).toEqual({ reason: "Budget is fixed" });
  });

  it("offers nothing once the application has ended", async () => {
    render(<OfferPanel application={{ ...application, status: "rejected" }} onChange={onChange} />);
    expect(await screen.findByText("No offer was made.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Make an offer" })).toBeNull();
  });
});
