import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BillingOverview, BillingPlan, Invoice } from "@/lib/api/types";

import { page } from "../../../../../test/fixtures";
import { errorBody, jsonResponse } from "../../../../../test/http";
import { TalentSearchPage } from "../talent/TalentSearchPage";

import { BillingPage } from "./BillingPage";
import { rupees } from "./money";

const features = (on: string[]) =>
  Object.fromEntries(
    ["talent_search", "agreements", "ai_fit_scores", "team_roles"].map((f) => [f, on.includes(f)]),
  );

const plan = (code: string, name: string, price: number, gigs: number | null, on: string[]) =>
  ({
    code,
    name,
    description: `${name} plan`,
    price_paise: price,
    currency: "INR",
    gst_percent: 18,
    max_live_gigs: gigs,
    features: features(on),
  }) as BillingPlan;

const PLANS = [
  plan("starter", "Starter", 99900, 1, ["agreements"]),
  plan("growth", "Growth", 249900, 5, ["talent_search", "agreements", "ai_fit_scores"]),
  plan("pro", "Pro", 599900, null, ["talent_search", "agreements", "ai_fit_scores", "team_roles"]),
];

const freeOverview = (): BillingOverview => ({
  subscription: null,
  entitlements: {
    plan: "free",
    plan_name: "Free",
    max_live_gigs: 1,
    live_gigs: 1,
    can_post_gig: false,
    reason: "Your Free plan allows 1 live gig. Pause one, or upgrade, to go live.",
    features: features(["agreements"]),
  },
});

const subscription = (status: string, extra: object = {}) => ({
  id: "s1",
  plan: PLANS[1]!,
  pending_plan: null,
  status,
  checkout_url: "https://rzp.test/checkout/sub_1",
  trial_ends_at: null,
  current_period_start: "2026-11-01T00:00:00Z",
  current_period_end: "2026-12-01T00:00:00Z",
  payment_failed_at: null,
  grace_until: null,
  cancel_at_period_end: false,
  created_at: "2026-11-01T00:00:00Z",
  ...extra,
});

const growthOverview = (status = "active", extra: object = {}): BillingOverview =>
  ({
    subscription: subscription(status, extra),
    entitlements: {
      plan: "growth",
      plan_name: "Growth",
      max_live_gigs: 5,
      live_gigs: 2,
      can_post_gig: true,
      reason: "",
      features: features(["talent_search", "agreements", "ai_fit_scores"]),
    },
  }) as BillingOverview;

const invoice: Invoice = {
  id: "i1",
  number: "BRT/2026-27/000001",
  plan_name: "Growth",
  period_start: "2026-11-01T00:00:00Z",
  period_end: "2026-12-01T00:00:00Z",
  taxable_paise: 249900,
  cgst_paise: 22491,
  sgst_paise: 22491,
  igst_paise: 0,
  tax_paise: 44982,
  total_paise: 294882,
  gst_rate_percent: "18.00",
  place_of_supply: "Karnataka",
  buyer_gstin: "29ABCDE1234F1Z5",
  issued_at: "2026-11-01T00:00:00Z",
  emailed_at: "2026-11-01T00:00:00Z",
  pdf_ready: true,
};

let overview: BillingOverview;
let invoices: Invoice[];
let network: ReturnType<typeof vi.fn>;
const assign = vi.fn();

function sent(method: string, suffix: string) {
  return network.mock.calls
    .map((c) => c[0] as Request)
    .filter((r) => r.method === method && new URL(r.url).pathname.endsWith(suffix));
}

beforeEach(() => {
  overview = freeOverview();
  invoices = [];
  assign.mockReset();
  vi.stubGlobal("location", { ...window.location, assign });
  network = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/billing/") return jsonResponse(200, overview);
    if (path === "/api/v1/billing/plans/") return jsonResponse(200, PLANS);
    if (path === "/api/v1/billing/invoices/") return jsonResponse(200, page(invoices));
    if (path === "/api/v1/billing/subscribe/") {
      return jsonResponse(201, subscription("created"));
    }
    if (path === "/api/v1/billing/change-plan/") return jsonResponse(200, subscription("active"));
    if (path === "/api/v1/billing/cancel/") {
      return jsonResponse(200, subscription("active", { cancel_at_period_end: true }));
    }
    if (path.endsWith("/pdf/")) {
      return jsonResponse(200, { url: "https://storage.test/i1.pdf", expires_in: 600 });
    }
    return jsonResponse(404, errorBody("not_found"));
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("money", () => {
  it("shows paise as rupees", () => {
    expect(rupees(249900)).toBe("₹2,499");
    expect(rupees(294882)).toBe("₹2,948.82");
  });
});

describe("BillingPage", () => {
  it("shows the free plan's limit and sends a new subscriber to checkout with their code", async () => {
    const user = userEvent.setup();
    render(<BillingPage />);
    expect(await screen.findByRole("heading", { name: "Your plan: Free" })).toBeVisible();
    expect(screen.getByText("1 of 1")).toBeVisible();
    expect(screen.getByText(/Free plan allows 1 live gig/)).toBeVisible();
    const growth = screen.getByRole("listitem", { name: "Growth" });
    expect(within(growth).getByText("₹2,499")).toBeVisible();
    expect(within(growth).getByText("5 live gigs")).toBeVisible();
    await user.type(screen.getByLabelText(/Have a code/), "FIRST100");
    await user.click(within(growth).getByRole("button", { name: "Choose Growth" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("https://rzp.test/checkout/sub_1"));
    expect(await sent("POST", "/subscribe/")[0]!.json()).toEqual({
      plan: "growth",
      coupon: "FIRST100",
    });
  });

  it("upgrades and downgrades a paid plan", async () => {
    const user = userEvent.setup();
    overview = growthOverview();
    render(<BillingPage />);
    const pro = await screen.findByRole("listitem", { name: "Pro" });
    expect(
      within(screen.getByRole("listitem", { name: "Growth" })).getByText("Your plan"),
    ).toBeVisible();
    await user.click(within(pro).getByRole("button", { name: "Upgrade now" }));
    await user.click(
      within(screen.getByRole("listitem", { name: "Starter" })).getByRole("button", {
        name: "Downgrade",
      }),
    );
    await vi.waitFor(() => expect(sent("POST", "/change-plan/")).toHaveLength(2));
    expect(await sent("POST", "/change-plan/")[0]!.json()).toEqual({ plan: "pro" });
    expect(await sent("POST", "/change-plan/")[1]!.json()).toEqual({ plan: "starter" });
    expect(screen.queryByLabelText(/Have a code/)).toBeNull();
  });

  it("warns about a failed payment and links to update the card", async () => {
    const user = userEvent.setup();
    overview = growthOverview("past_due", { grace_until: "2026-11-25T00:00:00Z" });
    render(<BillingPage />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/couldn't take your last payment/);
    expect(alert).toHaveTextContent(/stay on until/);
    await user.click(within(alert).getByRole("button", { name: "Update payment method" }));
    expect(assign).toHaveBeenCalledWith("https://rzp.test/checkout/sub_1");
  });

  it("cancels at the period end after confirming", async () => {
    const user = userEvent.setup();
    overview = growthOverview();
    render(<BillingPage />);
    await user.click(await screen.findByRole("button", { name: "Cancel plan" }));
    const dialog = screen.getByRole("dialog", { name: "Cancel your plan?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel at period end" }));
    expect(await sent("POST", "/cancel/")[0]!.json()).toEqual({ at_period_end: true });
    expect(await screen.findByText("Ends")).toBeVisible();
  });

  it("lists GST invoices and downloads one", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    overview = growthOverview();
    invoices = [invoice];
    render(<BillingPage />);
    const row = (await screen.findByRole("rowheader", { name: "BRT/2026-27/000001" })).closest(
      "tr",
    )!;
    expect(within(row).getByText("₹2,948.82")).toBeVisible();
    expect(within(row).getByText(/CGST \+ SGST/)).toBeVisible();
    await user.click(within(row).getByRole("button", { name: /Download PDF/ }));
    await vi.waitFor(() =>
      expect(open).toHaveBeenCalledWith("https://storage.test/i1.pdf", "_blank", "noopener"),
    );
    open.mockRestore();
  });
});

describe("TalentSearchPage", () => {
  it("points plans without talent search to Billing", async () => {
    render(<TalentSearchPage />);
    expect(await screen.findByText("Talent search is on Growth and Pro")).toBeVisible();
    expect(screen.getByRole("link", { name: "See plans" })).toHaveAttribute(
      "href",
      "/console/billing",
    );
  });
});
