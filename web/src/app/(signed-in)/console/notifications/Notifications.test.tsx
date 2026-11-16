import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AppNotification, NotificationPreferences } from "@/lib/api/types";

import { page } from "../../../../../test/fixtures";
import { errorBody, jsonResponse } from "../../../../../test/http";

import { consolePath } from "./links";
import { NotificationInbox } from "./NotificationInbox";
import { NotificationSettings } from "./NotificationSettings";
import { NotificationsLink } from "./NotificationsLink";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const note = (overrides: Partial<AppNotification> = {}): AppNotification => ({
  id: "n1",
  kind: "application.applied",
  title: "New applicant for Front desk",
  body: "Riya applied. Have a look.",
  urgent: false,
  app_path: "/trips",
  web_url: "https://web.test/console/applicants/a1",
  read: false,
  read_at: null,
  created_at: "2026-11-16T10:00:00Z",
  ...overrides,
});

const prefs = (): NotificationPreferences => ({
  locale: "en",
  quiet_hours_enabled: true,
  quiet_start: "22:00",
  quiet_end: "08:00",
  channels_available: ["in_app", "push", "email"],
  event_types: [
    {
      key: "application.applied",
      label: "New applicant",
      urgent: false,
      channels: {
        in_app: { enabled: true, locked: true },
        push: { enabled: true, locked: false },
        email: { enabled: true, locked: false },
      },
    },
    {
      key: "offer.expiring",
      label: "Offer about to expire",
      urgent: true,
      channels: {
        in_app: { enabled: true, locked: true },
        push: { enabled: true, locked: false },
        email: { enabled: true, locked: false },
      },
    },
  ],
});

let network: ReturnType<typeof vi.fn>;
let items: AppNotification[];
let saved: NotificationPreferences;

function requests(method: string, suffix: string) {
  return network.mock.calls
    .map((c) => c[0] as Request)
    .filter((r) => r.method === method && new URL(r.url).pathname.endsWith(suffix));
}

beforeEach(() => {
  push.mockReset();
  items = [note(), note({ id: "n2", title: "Booking confirmed", read: true, urgent: true })];
  saved = prefs();
  network = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/notifications/") return jsonResponse(200, page(items));
    if (path === "/api/v1/notifications/unread-count/") return jsonResponse(200, { unread: 3 });
    if (path.endsWith("/read/")) return jsonResponse(200, { ...items[0], read: true });
    if (path.endsWith("/read-all/")) return jsonResponse(200, { marked: 1 });
    if (path === "/api/v1/notifications/preferences/") {
      if (request.method === "PUT") {
        const body = (await request.clone().json()) as { locale: "en" | "hi" };
        saved = { ...saved, locale: body.locale };
      }
      return jsonResponse(200, saved);
    }
    return jsonResponse(404, errorBody("not_found"));
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("consolePath", () => {
  it("keeps only links into the console", () => {
    expect(consolePath("https://web.test/console/agreements/ag1")).toBe("/console/agreements/ag1");
    expect(consolePath("https://web.test/talent")).toBeNull();
    expect(consolePath("not a url")).toBeNull();
  });
});

describe("NotificationsLink", () => {
  it("shows the unread count", async () => {
    render(<NotificationsLink />);
    expect(await screen.findByLabelText("3 unread")).toHaveTextContent("3");
    expect(screen.getByRole("link", { name: /Notifications/ })).toHaveAttribute(
      "href",
      "/console/notifications",
    );
  });
});

describe("NotificationInbox", () => {
  it("lists notifications and opens one where it points", async () => {
    const user = userEvent.setup();
    render(<NotificationInbox />);
    const first = await screen.findByRole("button", { name: /New applicant for Front desk/ });
    expect(within(first).getByText("(unread)")).toBeInTheDocument();
    expect(screen.getByText("Urgent")).toBeVisible();
    await user.click(first);
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/console/applicants/a1"));
    expect(await requests("POST", "/n1/read/")[0]!.json()).toEqual({ from_push: false });
  });

  it("marks everything read", async () => {
    const user = userEvent.setup();
    render(<NotificationInbox />);
    await user.click(await screen.findByRole("button", { name: "Mark all 1 read" }));
    await vi.waitFor(() => expect(requests("POST", "/read-all/")).toHaveLength(1));
    expect(screen.queryByText("(unread)")).toBeNull();
  });

  it("says when there's nothing yet", async () => {
    items = [];
    render(<NotificationInbox />);
    expect(await screen.findByText("Nothing yet")).toBeVisible();
  });
});

describe("NotificationSettings", () => {
  it("switches a channel off and saves the language and quiet hours", async () => {
    const user = userEvent.setup();
    render(<NotificationSettings />);
    const email = await screen.findByRole("checkbox", { name: "New applicant by Email" });
    expect(screen.getByRole("checkbox", { name: "New applicant by In app" })).toBeDisabled();
    expect(screen.getByText("(urgent)")).toBeVisible();
    await user.click(email);
    await user.selectOptions(screen.getByLabelText("Language"), "hi");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
    expect(await requests("PUT", "/preferences/")[0]!.json()).toEqual({
      locale: "hi",
      quiet_hours_enabled: true,
      quiet_start: "22:00",
      quiet_end: "08:00",
      changes: [{ event_type: "application.applied", channel: "email", enabled: false }],
    });
  });
});
