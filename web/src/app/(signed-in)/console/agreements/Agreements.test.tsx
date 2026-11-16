import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Agreement, AgreementListItem } from "@/lib/api/types";
import type { PhoneSignIn } from "@/lib/firebase/phoneAuth";

import {
  agreement,
  agreementListItem,
  agreementVersion,
  page,
  terms,
} from "../../../../../test/fixtures";
import { errorBody, jsonResponse, vendorUser } from "../../../../../test/http";

import { AgreementDetail } from "./AgreementDetail";
import { AgreementsIndex } from "./AgreementsIndex";

vi.mock("next/navigation", () => ({ useParams: () => ({ agreementId: "ag-1" }) }));
vi.mock("@/lib/session/session", () => ({
  useSession: () => ({ state: { status: "signed-in", user: vendorUser } }),
}));

let current: Agreement;
let list: AgreementListItem[];
let network: ReturnType<typeof vi.fn>;

function posted(suffix: string) {
  return network.mock.calls
    .map((c) => c[0] as Request)
    .filter((r) => r.method === "POST" && new URL(r.url).pathname.endsWith(suffix));
}

beforeEach(() => {
  current = agreement();
  list = [agreementListItem()];
  network = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/agreements/") return jsonResponse(200, page(list));
    if (path === "/api/v1/agreements/ag-1/") return jsonResponse(200, current);
    if (path.endsWith("/sign/") && request.method === "GET") {
      return jsonResponse(200, {
        method: "otp",
        consent_text: "I have read version 1 of this agreement and I agree to its terms.",
        phone_hint: "+91 ••••• 3210",
        max_age_seconds: 300,
        document_sha256: "c".repeat(64),
      });
    }
    if (path.endsWith("/sign/")) {
      current = agreement({
        versions: [agreementVersion({ signed_by_me: true, can_sign: false })],
      });
      return jsonResponse(200, current);
    }
    if (path.endsWith("/pdf/")) {
      return jsonResponse(200, {
        url: "https://storage.test/v1.pdf",
        expires_in: 600,
        sha256: "c".repeat(64),
        size: 1,
      });
    }
    if (path.endsWith("/details/")) {
      return jsonResponse(200, {
        booking_id: current.booking,
        status: current.booking_status,
        host: { name: "Asha", phone: "+919876543210" },
        talent: { name: "Aarav Mehta", phone: "+919812345678" },
        place: null,
      });
    }
    if (path.endsWith("/cancel/") && request.method === "GET") {
      return jsonResponse(200, {
        reasons: [
          { code: "staffing", label: "Staffing needs changed" },
          { code: "other", label: "Something else" },
        ],
        effect: "late",
        effect_label: "Late",
        policy: "moderate",
        notice_days: 7,
        days_before_start: 4,
      });
    }
    if (path.endsWith("/cancel/")) {
      current = agreement({ booking_status: "cancelled" });
      return jsonResponse(200, {});
    }
    if (path.endsWith("/changes/")) return jsonResponse(201, current);
    if (path.endsWith("/decline/")) return jsonResponse(200, current);
    return jsonResponse(404, errorBody("not_found"));
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function fakePhone() {
  const confirm = vi.fn(async (code: string) => `fresh-id-token-${code}`);
  const signIn: PhoneSignIn = {
    sendCode: vi.fn(async () => ({ confirm })),
    reset: vi.fn(async () => {}),
  };
  return { signIn, confirm };
}

describe("AgreementsIndex", () => {
  it("lists agreements and what needs your signature", async () => {
    render(<AgreementsIndex />);
    const item = (await screen.findByRole("link", { name: current.gig_title })).closest("li")!;
    expect(within(item).getByText("Sign version 1")).toBeVisible();
    expect(within(item).getByText("Not in force yet")).toBeVisible();
    expect(within(item).getByText(/Aarav Mehta/)).toBeVisible();
  });
});

describe("AgreementDetail", () => {
  it("signs with consent and a fresh OTP", async () => {
    const user = userEvent.setup();
    const { signIn } = fakePhone();
    render(<AgreementDetail phoneSignIn={signIn} />);

    expect(
      await screen.findByText(/legal text is a placeholder that a lawyer must review/),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Sign version 1" }));
    const consent = await screen.findByRole("checkbox", { name: /I agree to its terms/ });
    expect(screen.getByRole("button", { name: "Sign" })).toBeDisabled();
    await user.click(consent);
    await user.click(screen.getByRole("button", { name: "Send code" }));
    expect(signIn.sendCode).toHaveBeenCalledWith(vendorUser.phone, expect.anything());
    await user.type(await screen.findByLabelText(/Code sent to \+91/), "123456");
    await user.click(screen.getByRole("button", { name: "Sign" }));

    await vi.waitFor(() => expect(posted("/sign/")).toHaveLength(1));
    expect(await posted("/sign/")[0]!.json()).toEqual({
      consent: true,
      document_sha256: "c".repeat(64),
      otp_token: "fresh-id-token-123456",
    });
    await vi.waitFor(() => expect(signIn.reset).toHaveBeenCalled());
    await vi.waitFor(() =>
      expect(screen.queryByRole("button", { name: "Sign version 1" })).toBeNull(),
    );
  });

  it("proposes a change with only the changed terms", async () => {
    const user = userEvent.setup();
    current = agreement({
      in_force: true,
      current_version: 1,
      versions: [agreementVersion({ status: "active", can_sign: false, signed_by_me: true })],
    });
    render(<AgreementDetail phoneSignIn={fakePhone().signIn} />);
    await user.click(await screen.findByRole("button", { name: "Change the terms" }));
    const hours = screen.getByLabelText(/Hours a day/);
    await user.clear(hours);
    await user.type(hours, "3");
    await user.type(screen.getByLabelText(/Why the change/), "Quieter season");
    await user.click(screen.getByRole("button", { name: "Propose the change" }));
    await vi.waitFor(() => expect(posted("/changes/")).toHaveLength(1));
    expect(await posted("/changes/")[0]!.json()).toEqual({
      changes: { hours_per_day: 3 },
      reason: "Quieter season",
    });
  });

  it("declines a change the other side asked for", async () => {
    const user = userEvent.setup();
    current = agreement({
      in_force: true,
      current_version: 1,
      versions: [
        agreementVersion({
          id: "v-2",
          number: 2,
          proposed_by: "talent",
          change_reason: "I'd like Sundays free",
          changed_fields: ["days_per_week"],
          terms: { ...terms, days_per_week: 4 },
        }),
        agreementVersion({ status: "active", can_sign: false }),
      ],
    });
    render(<AgreementDetail phoneSignIn={fakePhone().signIn} />);
    expect(await screen.findByText(/I'd like Sundays free/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Decline this change" }));
    await vi.waitFor(() => expect(posted("/agreement-versions/v-2/decline/")).toHaveLength(1));
  });
});

describe("BookingPanel", () => {
  it("waits for signatures before sharing contact details", async () => {
    render(<AgreementDetail />);
    expect(await screen.findByText("Awaiting signatures")).toBeVisible();
    expect(screen.getByText(/contact details shared, once both of you have signed/)).toBeVisible();
    expect(network.mock.calls.some((c) => (c[0] as Request).url.endsWith("/details/"))).toBe(false);
  });

  it("shows the talent's verified phone once confirmed", async () => {
    current = agreement({ booking_status: "confirmed", in_force: true, current_version: 1 });
    render(<AgreementDetail />);
    const phone = await screen.findByRole("link", { name: "+919812345678" });
    expect(phone).toHaveAttribute("href", "tel:+919812345678");
    expect(screen.getByText("Confirmed")).toBeVisible();
  });

  it("cancels with a reason after showing the policy's effect", async () => {
    const user = userEvent.setup();
    current = agreement({ booking_status: "confirmed", in_force: true, current_version: 1 });
    render(<AgreementDetail />);
    await user.click(await screen.findByRole("button", { name: "Cancel this booking" }));
    expect(await screen.findByText(/counts as a late cancellation/)).toBeVisible();
    expect(screen.getByText(/7 days' notice; the stay starts in 4 days/)).toBeVisible();
    const submit = screen.getByRole("button", { name: "Cancel the booking" });
    expect(submit).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Reason"), "other");
    expect(submit).toBeDisabled(); // "other" needs a note
    await user.type(screen.getByLabelText(/More about why/), "Roof repairs");
    await user.click(submit);
    await vi.waitFor(() => expect(posted("/cancel/")).toHaveLength(1));
    expect(await posted("/cancel/")[0]!.json()).toEqual({ reason: "other", note: "Roof repairs" });
    expect(await screen.findByText("Cancelled")).toBeVisible();
  });
});

describe("Agreement viewer", () => {
  it("shows the PDF in the page, or opens it in a new tab", async () => {
    const user = userEvent.setup();
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    render(<AgreementDetail />);
    await user.click(await screen.findByRole("button", { name: "Read it here" }));
    const frame = await screen.findByTitle("Version 1 of the agreement (PDF)");
    expect(frame).toHaveAttribute("src", "https://storage.test/v1.pdf");
    await user.click(screen.getByRole("button", { name: "Hide the document" }));
    expect(screen.queryByTitle("Version 1 of the agreement (PDF)")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Open PDF in a new tab" }));
    await vi.waitFor(() =>
      expect(open).toHaveBeenCalledWith("https://storage.test/v1.pdf", "_blank", "noopener"),
    );
    open.mockRestore();
  });
});
