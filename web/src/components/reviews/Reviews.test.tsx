import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BookingReviews as Data, StayReview } from "@/lib/api/types";

import { jsonResponse } from "../../../test/http";

import { BookingReviews } from "./BookingReviews";
import { ReputationSummary } from "./ReputationSummary";

const LABELS = {
  communication: "Communication",
  accuracy: "Quality of the work",
  safety: "Safety",
  reliability: "Punctuality",
};

function review(overrides: Partial<StayReview> = {}): StayReview {
  return {
    id: "r-1",
    booking_id: "b-1",
    subject_side: "host",
    rating: 4,
    categories: [
      { key: "communication", label: "Communication", score: 5 },
      { key: "accuracy", label: "Accuracy of the listing", score: 4 },
      { key: "safety", label: "Safety", score: 5 },
      { key: "reliability", label: "Payment as agreed", score: 4 },
    ],
    text: "Kind hosts and a calm room by the sea.",
    status: "published",
    author_name: "Aarav Mehta",
    submitted_at: "2026-12-21T10:00:00Z",
    published_at: "2026-12-22T10:00:00Z",
    reply: null,
    ...overrides,
  };
}

function data(overrides: Partial<Data> = {}): Data {
  return {
    reviewing: "talent",
    can_review: true,
    window_closes_at: "2027-01-03T10:00:00Z",
    category_labels: LABELS,
    mine: null,
    theirs: null,
    they_have_reviewed: false,
    ...overrides,
  };
}

let current: Data;
let posted: Array<{ path: string; body: unknown }>;

beforeEach(() => {
  current = data();
  posted = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      if (request.method === "POST") {
        posted.push({ path, body: await request.json() });
        if (path.endsWith("/reviews/")) {
          current = data({
            can_review: false,
            mine: review({ status: "submitted", published_at: null }),
          });
          return jsonResponse(201, current.mine);
        }
        return jsonResponse(201, {});
      }
      return jsonResponse(200, current);
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BookingReviews", () => {
  it("writes a review that stays hidden until both are in", async () => {
    const user = userEvent.setup();
    current = data({ they_have_reviewed: true });
    render(<BookingReviews bookingId="b-1" />);
    expect(await screen.findByText(/They've reviewed you/)).toBeInTheDocument();
    const submit = screen.getByRole("button", { name: "Submit review" });
    expect(submit).toBeDisabled();

    for (const group of ["Overall", ...Object.values(LABELS)]) {
      const set = screen.getByRole("group", { name: group });
      await user.click(within(set).getByRole("radio", { name: "5 out of 5" }));
    }
    await user.type(screen.getByLabelText(/Your review/), "Hard-working, kind to guests, on time.");
    await user.click(submit);
    expect(posted[0]).toEqual({
      path: "/api/v1/bookings/b-1/reviews/",
      body: {
        rating: 5,
        communication: 5,
        accuracy: 5,
        safety: 5,
        reliability: 5,
        text: "Hard-working, kind to guests, on time.",
      },
    });
    expect(await screen.findByText(/Hidden until they review too/)).toBeInTheDocument();
  });

  it("shows their published review, and replies once", async () => {
    const user = userEvent.setup();
    current = data({ can_review: false, mine: review({ id: "r-0" }), theirs: review() });
    render(<BookingReviews bookingId="b-1" />);
    const theirs = await screen.findByRole("article", { name: "Their review of you" });
    expect(within(theirs).getByText("Accuracy of the listing")).toBeInTheDocument();
    expect(within(theirs).getByLabelText("Payment as agreed: 4 out of 5")).toBeInTheDocument();
    await user.click(within(theirs).getByRole("button", { name: "Reply" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Your reply"), "Thanks for staying!");
    await user.click(within(dialog).getByRole("button", { name: "Post reply" }));
    expect(posted[0]).toEqual({
      path: "/api/v1/reviews/r-1/reply/",
      body: { text: "Thanks for staying!" },
    });
  });

  it("has no reply button once they've replied", async () => {
    current = data({
      can_review: false,
      theirs: review({ reply: { text: "Thank you!", created_at: "2026-12-23T10:00:00Z" } }),
    });
    render(<BookingReviews bookingId="b-1" />);
    const theirs = await screen.findByRole("article", { name: "Their review of you" });
    expect(within(theirs).getByText("Thank you!")).toBeInTheDocument();
    expect(within(theirs).queryByRole("button", { name: "Reply" })).toBeNull();
  });
});

describe("ReputationSummary", () => {
  it("shows the rating, completion, response time and badges", () => {
    render(
      <ReputationSummary
        reputation={{
          rating_average: "4.75",
          review_count: 8,
          completion_rate: 96,
          response_minutes: 90,
          badges: [{ key: "trusted_member", label: "Trusted member" }],
        }}
      />,
    );
    const summary = screen.getByLabelText("Reputation");
    expect(summary).toHaveTextContent("★ 4.8 from 8 reviews");
    expect(summary).toHaveTextContent("96% of stays completed");
    expect(summary).toHaveTextContent("replies in about 2 h");
    expect(within(summary).getByText("Trusted member")).toBeInTheDocument();
  });

  it("says when there are no reviews yet", () => {
    render(
      <ReputationSummary
        reputation={{
          rating_average: null,
          review_count: 0,
          completion_rate: null,
          response_minutes: null,
          badges: [],
        }}
      />,
    );
    expect(screen.getByLabelText("Reputation")).toHaveTextContent("No reviews yet");
  });
});
