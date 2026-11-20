import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Arrivals } from "@/lib/api/types";
import { memoryStore, type AttendanceStore } from "@/lib/attendance/store";

import { jsonResponse } from "../../../../../test/http";

import { ArrivalsPage } from "./ArrivalsPage";

// The server's code for this secret at NOW (see crypto.test.ts).
const SECRET = "JBSWY3DPEHPK3PXP";
const CODE = "832515";
const NOW = new Date("2026-12-01T10:00:00Z");

function day(overrides: Partial<Arrivals> = {}): Arrivals {
  return {
    date: "2026-12-01",
    generated_at: "2026-12-01T09:00:00Z",
    public_keys: [{ kid: "k1", alg: "Ed25519", public_key: "AAAA" }],
    code_period_seconds: 300,
    clock_skew_seconds: 120,
    arrivals: [
      {
        booking_id: "b-1",
        talent_id: "t-1",
        talent_name: "Aarav Mehta",
        gig_title: "Mural for the café",
        property_name: "Sea Breeze",
        start_date: "2026-12-01",
        end_date: "2026-12-20",
        status: "confirmed",
        problem: "",
        pass_id: "p-1",
        code_secret: SECRET,
        pass_valid_from: "2026-11-30T00:00:00Z",
        pass_valid_until: "2026-12-02T00:00:00Z",
        no_show_from: "2026-12-01T12:30:00Z",
      },
    ],
    in_house: [],
    ...overrides,
  };
}

let network: ReturnType<typeof vi.fn>;
let synced: unknown[];
let online: boolean;
let store: AttendanceStore;

function setOnline(value: boolean) {
  online = value;
  act(() => {
    window.dispatchEvent(new Event(value ? "online" : "offline"));
  });
}

beforeEach(() => {
  synced = [];
  online = true;
  store = memoryStore();
  vi.spyOn(navigator, "onLine", "get").mockImplementation(() => online);
  network = vi.fn(async (request: Request) => {
    if (!online) throw new TypeError("Failed to fetch");
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/attendance/arrivals/") return jsonResponse(200, day());
    if (path === "/api/v1/attendance/hours/pending/") {
      return jsonResponse(200, { count: 0, next: null, previous: null, results: [] });
    }
    if (path === "/api/v1/attendance/sync/") {
      const body = (await request.json()) as { events: Array<{ client_id: string }> };
      synced.push(...body.events);
      return jsonResponse(200, {
        results: body.events.map((e) => ({
          client_id: e.client_id,
          status: "applied",
          message: "",
          booking_id: "b-1",
        })),
      });
    }
    return jsonResponse(404, {});
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ArrivalsPage", () => {
  it("checks a talent in by code offline, then syncs once back online", async () => {
    const user = userEvent.setup();
    render(<ArrivalsPage store={store} clock={() => NOW} />);
    expect(await screen.findByText("Aarav Mehta")).toBeInTheDocument();
    expect(await store.getDay()).not.toBeNull(); // kept for offline use

    setOnline(false);
    expect(screen.getByText("Offline")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enter code" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Six-digit code"), "000000");
    await user.click(within(dialog).getByRole("button", { name: "Check in" }));
    expect(within(dialog).getByText(/isn't right/)).toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("Six-digit code"));
    await user.type(within(dialog).getByLabelText("Six-digit code"), CODE);
    await user.click(within(dialog).getByRole("button", { name: "Check in" }));

    expect(await screen.findByText("Checked in · waiting to sync")).toBeInTheDocument();
    expect(await store.queued()).toHaveLength(1);
    expect(synced).toHaveLength(0);

    setOnline(true);
    await waitFor(() => expect(synced).toHaveLength(1));
    expect(synced[0]).toMatchObject({ booking_id: "b-1", method: "code", code: CODE });
    await waitFor(async () => expect(await store.queued()).toHaveLength(0));
  });

  it("works from the cached day when it opens offline", async () => {
    await store.setDay(day());
    online = false;
    render(<ArrivalsPage store={store} clock={() => NOW} />);
    expect(await screen.findByText("Aarav Mehta")).toBeInTheDocument();
    expect(screen.getByText("Offline")).toBeInTheDocument();
    expect(network).not.toHaveBeenCalled();
  });

  it("confirms by hand with a reason", async () => {
    const user = userEvent.setup();
    online = false;
    await store.setDay(day());
    render(<ArrivalsPage store={store} clock={() => NOW} />);
    await user.click(await screen.findByRole("button", { name: "Confirm by hand" }));
    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Confirm arrival" });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Why"), "Phone battery dead");
    await user.click(confirm);
    const [queued] = await store.queued();
    expect(queued).toMatchObject({ method: "manual", reason: "Phone battery dead" });
  });

  it("shows why a synced check-in was refused", async () => {
    await store.addOutcomes([
      {
        client_id: "c-1",
        status: "refused",
        message: "The host needs to fund the stipend before check-in.",
        booking_id: "b-1",
        talent_name: "Aarav Mehta",
        at: NOW.toISOString(),
      },
    ]);
    online = false;
    await store.setDay(day());
    render(<ArrivalsPage store={store} clock={() => NOW} />);
    expect(
      await screen.findByText("The host needs to fund the stipend before check-in."),
    ).toBeInTheDocument();
  });

  it("keeps no-show closed until the grace period ends", async () => {
    online = false;
    await store.setDay(day());
    render(<ArrivalsPage store={store} clock={() => NOW} />);
    expect(await screen.findByRole("button", { name: "No-show" })).toBeDisabled();
  });
});
