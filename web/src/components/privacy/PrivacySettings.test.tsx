import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LEGAL_VERSION } from "@/lib/legal/documents";

import { errorBody, jsonResponse } from "../../../test/http";

import { PrivacySettings } from "./PrivacySettings";

const consent = (purpose: string, label: string, granted: boolean, required = false) => ({
  purpose,
  label,
  required,
  granted,
  version: granted ? LEGAL_VERSION : "",
  current_version: LEGAL_VERSION,
  needs_renewal: false,
  recorded_at: granted ? "2026-11-20T10:00:00Z" : null,
});

const CONSENTS = [
  consent("terms", "Terms of service", true, true),
  consent("privacy", "Privacy policy", true, true),
  consent("location", "Location use", true),
  consent("social", "Social account access", false),
  consent("marketing", "Marketing messages", false),
];
const NO_DELETION = { request: null, blockers: [], grace_days: 7 };
const page = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

type Handler = (request: Request) => Response | Promise<Response>;
let routes: Record<string, Handler>;
let calls: { method: string; path: string; body: unknown }[];

beforeEach(() => {
  calls = [];
  routes = {
    "GET /api/v1/privacy/consents/": () => jsonResponse(200, CONSENTS),
    "GET /api/v1/privacy/exports/": () => jsonResponse(200, page([])),
    "GET /api/v1/privacy/deletion/": () => jsonResponse(200, NO_DELETION),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      const key = `${request.method} ${path}`;
      const text = request.method === "GET" ? "" : await request.clone().text();
      calls.push({ method: request.method, path, body: text ? JSON.parse(text) : null });
      const handler = routes[key];
      if (!handler) throw new Error(`Unexpected ${key}`);
      return handler(request);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function row(label: string) {
  return within((await screen.findByText(label)).closest("li")!);
}

describe("PrivacySettings", () => {
  it("withdraws a consent with one click, the same way it is given", async () => {
    routes["POST /api/v1/privacy/consents/"] = () =>
      jsonResponse(
        200,
        CONSENTS.map((c) => (c.purpose === "location" ? { ...c, granted: false } : c)),
      );
    const user = userEvent.setup();
    render(<PrivacySettings />);

    await user.click(await (await row("Location use")).findByRole("button", { name: "Withdraw" }));
    expect(calls.at(-1)).toEqual({
      method: "POST",
      path: "/api/v1/privacy/consents/",
      body: { purpose: "location", granted: false, source: "web" },
    });
    expect(await (await row("Location use")).findByRole("button", { name: "Allow" })).toBeVisible();
  });

  it("gives a consent with the version shown", async () => {
    routes["POST /api/v1/privacy/consents/"] = () => jsonResponse(200, CONSENTS);
    const user = userEvent.setup();
    render(<PrivacySettings />);
    await user.click(
      await (await row("Marketing messages")).findByRole("button", { name: "Allow" }),
    );
    expect(calls.at(-1)!.body).toEqual({
      purpose: "marketing",
      granted: true,
      version: LEGAL_VERSION,
      source: "web",
    });
  });

  it("has no withdraw button for the required consents", async () => {
    render(<PrivacySettings />);
    await screen.findByText("Terms of service");
    expect((await row("Terms of service")).queryByRole("button")).toBeNull();
  });

  it("makes an export and downloads it through a short-lived link", async () => {
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    const ready = {
      id: "e1",
      status: "ready",
      size_bytes: 10,
      created_at: "2026-11-21T10:00:00Z",
      expires_at: "2026-11-22T10:00:00Z",
    };
    routes["POST /api/v1/privacy/exports/"] = () => {
      routes["GET /api/v1/privacy/exports/"] = () => jsonResponse(200, page([ready]));
      return jsonResponse(201, ready);
    };
    routes["POST /api/v1/privacy/exports/e1/link/"] = () =>
      jsonResponse(200, { url: "https://storage.test/e1.json", expires_in_seconds: 300 });
    const user = userEvent.setup();
    render(<PrivacySettings />);

    await user.click(await screen.findByRole("button", { name: "Export my data" }));
    await user.click(await screen.findByRole("button", { name: "Download" }));
    await vi.waitFor(() => expect(assign).toHaveBeenCalledWith("https://storage.test/e1.json"));
  });

  it("asks for a correction", async () => {
    routes["POST /api/v1/privacy/corrections/"] = () => jsonResponse(201, {});
    const user = userEvent.setup();
    render(<PrivacySettings />);
    await user.click(await screen.findByRole("button", { name: "Ask for a correction" }));
    expect(await screen.findByText("Say what is wrong and what it should be.")).toBeVisible();
    await user.type(screen.getByLabelText("What is wrong"), "phone number");
    await user.type(screen.getByLabelText("What it should be"), "+919876500001");
    await user.click(screen.getByRole("button", { name: "Ask for a correction" }));
    expect(await screen.findByText(/Sent\./)).toBeVisible();
    expect(calls.at(-1)!.body).toEqual({
      field: "phone number",
      correct_value: "+919876500001",
      note: "",
    });
  });

  it("schedules deletion after a confirmation, and can cancel it", async () => {
    const scheduled = {
      ...NO_DELETION,
      request: {
        id: "d1",
        status: "scheduled",
        requested_at: "2026-11-21T10:00:00Z",
        scheduled_for: "2026-11-28T10:00:00Z",
        cancelled_at: null,
        completed_at: null,
      },
    };
    routes["POST /api/v1/privacy/deletion/"] = () => jsonResponse(202, scheduled);
    routes["DELETE /api/v1/privacy/deletion/"] = () => {
      routes["GET /api/v1/privacy/deletion/"] = () => jsonResponse(200, NO_DELETION);
      return jsonResponse(200, { ...scheduled.request, status: "cancelled" });
    };
    const user = userEvent.setup();
    render(<PrivacySettings />);

    await user.click(await screen.findByRole("button", { name: "Delete my account" }));
    await user.click(screen.getByRole("button", { name: "Yes, delete my account" }));
    expect(calls.at(-1)!.body).toEqual({ confirm: true });
    expect(await screen.findByText(/will be deleted on/)).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Keep my account" }));
    expect(await screen.findByRole("button", { name: "Delete my account" })).toBeVisible();
  });

  it("explains what blocks deletion", async () => {
    routes["GET /api/v1/privacy/deletion/"] = () =>
      jsonResponse(200, {
        ...NO_DELETION,
        blockers: [
          { code: "active_bookings", count: 1, message: "Finish or cancel your bookings first." },
        ],
      });
    render(<PrivacySettings />);
    expect(await screen.findByText("Finish or cancel your bookings first.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Delete my account" })).toBeNull();
  });

  it("shows the API's error when a consent change fails", async () => {
    routes["POST /api/v1/privacy/consents/"] = () =>
      jsonResponse(409, errorBody("document_changed", "This document has changed."));
    const user = userEvent.setup();
    render(<PrivacySettings />);
    await user.click(
      await (await row("Social account access")).findByRole("button", { name: "Allow" }),
    );
    expect(await screen.findByText(/This document has changed/)).toBeVisible();
  });
});
