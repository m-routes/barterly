import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { LibraryItem, TrackedDeliverable } from "@/lib/api/types";

import { jsonResponse } from "../../../../../test/http";

import { ContentPage } from "./ContentPage";

function deliverable(overrides: Partial<TrackedDeliverable> = {}): TrackedDeliverable {
  return {
    id: "d-1",
    booking_id: "b-1",
    gig_title: "Rooftop café reels",
    kind: "reel",
    platform: "instagram",
    spec_type: "instagram_reel",
    title: "Instagram reel 1 of 2",
    notes: "",
    due_date: "2026-12-20",
    status: "submitted",
    change_rounds: 0,
    change_rounds_left: 2,
    disclosure_required: true,
    submitted_at: "2026-12-10T10:00:00Z",
    approved_at: null,
    latest_submission: {
      version: 1,
      post_url: "https://www.instagram.com/reel/Cabc/",
      files: [],
      note: "Shot at sunset",
      disclosure_confirmed: true,
      disclosure_detected: false,
      submitted_at: "2026-12-10T10:00:00Z",
      review: "",
      review_note: "",
      reviewed_at: null,
    },
    stats: [
      {
        source: "manual",
        self_reported: true,
        views: 1200,
        likes: 90,
        comments: 4,
        captured_at: "2026-12-11T10:00:00Z",
        screenshot_url: "https://storage.test/read/shot.jpg",
      },
    ],
    usage_rights: null,
    usable_until: null,
    ...overrides,
  };
}

function libraryItem(): LibraryItem {
  return {
    ...deliverable({ status: "approved", approved_at: "2027-01-31T12:00:00Z" }),
    usage_rights: { scope: "organic", duration_months: 12, credit_required: true },
    usable_until: "2028-01-31",
    talent_name: "Aarav Mehta",
    downloads: [
      {
        id: "f-1",
        content_type: "video/mp4",
        size_bytes: 1,
        url: "https://storage.test/v?download=1",
      },
    ],
  };
}

const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

let network: ReturnType<typeof vi.fn>;
let toReview: TrackedDeliverable[];
let reviews: unknown[];

beforeEach(() => {
  toReview = [deliverable()];
  reviews = [];
  network = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname;
    if (path === "/api/v1/content/to-review/") return jsonResponse(200, page(toReview));
    if (path === "/api/v1/content/library/") return jsonResponse(200, page([libraryItem()]));
    if (path.endsWith("/review/")) {
      reviews.push(await request.json());
      toReview = [];
      return jsonResponse(200, deliverable({ status: "approved" }));
    }
    return jsonResponse(404, {});
  });
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ContentPage", () => {
  it("shows the label check and self-reported stats, and approves", async () => {
    const user = userEvent.setup();
    render(<ContentPage />);
    expect(await screen.findByText("Instagram reel 1 of 2")).toBeInTheDocument();
    const label = screen.getByLabelText("Collaboration label");
    expect(within(label).getByText("Talent confirms the #collab / #ad label")).toBeInTheDocument();
    expect(within(label).getByText("Label not found in the caption")).toBeInTheDocument();
    const stats = screen.getByLabelText("Post stats");
    expect(within(stats).getByText("Self-reported")).toBeInTheDocument();
    expect(within(stats).getByText(/1,200 views/)).toBeInTheDocument();
    expect(within(stats).getByRole("link", { name: "Screenshot" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Approve" }));
    expect(reviews).toEqual([{ approve: true, note: "" }]);
    expect(await screen.findByText("Nothing to review")).toBeInTheDocument();
  });

  it("asks for changes with a note, and stops after two rounds", async () => {
    const user = userEvent.setup();
    toReview = [
      deliverable(),
      deliverable({ id: "d-2", title: "Photo set", change_rounds: 2, change_rounds_left: 0 }),
    ];
    render(<ContentPage />);
    const buttons = await screen.findAllByRole("button", { name: "Ask for changes" });
    await user.click(buttons[1]!);
    let dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/used both rounds/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Ask for changes" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: /close/i }));

    await user.click(buttons[0]!);
    dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("What needs to change"), "Brighter colours");
    await user.click(within(dialog).getByRole("button", { name: "Ask for changes" }));
    expect(reviews).toEqual([{ approve: false, note: "Brighter colours" }]);
  });

  it("lists approved content with its usage rights and downloads", async () => {
    const user = userEvent.setup();
    render(<ContentPage />);
    await user.click(await screen.findByRole("tab", { name: "Library" }));
    const rights = await screen.findByLabelText("Usage rights");
    expect(rights).toHaveTextContent("Your own social channels and website");
    expect(rights).toHaveTextContent("12 months from approval");
    expect(rights).toHaveTextContent("Credit the talent when you use it");
    expect(screen.getByRole("link", { name: "Download video 1" })).toHaveAttribute(
      "href",
      "https://storage.test/v?download=1",
    );
  });
});
