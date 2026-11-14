import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { gig, page } from "../../../../../test/fixtures";
import { jsonResponse } from "../../../../../test/http";

import { GigList } from "./GigList";

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const lastQuery = () => new URL((network.mock.lastCall![0] as Request).url).searchParams;

describe("GigList", () => {
  it("lists gigs with status chips and the right actions", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(200, page([gig, { ...gig, id: "g2", title: "Yoga teacher", status: "live" }])),
    );
    render(<GigList />);

    const rows = await screen.findAllByRole("row");
    const draft = within(rows[1]!);
    expect(draft.getByText("Draft")).toBeVisible();
    expect(draft.getByRole("link", { name: /Continue/ })).toHaveAttribute(
      "href",
      `/console/gigs/${gig.id}/edit`,
    );
    expect(draft.queryByRole("link", { name: /Applicants/ })).toBeNull();
    const live = within(rows[2]!);
    expect(live.getByText("Live")).toBeVisible();
    expect(live.getByRole("link", { name: /Applicants/ })).toHaveAttribute(
      "href",
      "/console/gigs/g2/applicants",
    );
    expect(lastQuery().get("status")).toBeNull();
  });

  it("filters by status", async () => {
    network
      .mockResolvedValueOnce(jsonResponse(200, page([gig])))
      .mockResolvedValueOnce(jsonResponse(200, page([])));
    const user = userEvent.setup();
    render(<GigList />);
    await screen.findAllByRole("row");
    const live = screen.getByRole("button", { name: "Live" });
    await user.click(live);

    expect(live).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByRole("heading", { name: "No live gigs" })).toBeVisible();
    expect(lastQuery().get("status")).toBe("live");
  });

  it("invites a first gig when there are none", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, page([])));
    render(<GigList />);
    expect(await screen.findByRole("heading", { name: "No gigs yet" })).toBeVisible();
  });
});
