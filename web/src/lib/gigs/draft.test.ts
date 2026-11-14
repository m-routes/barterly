import { describe, expect, it } from "vitest";

import { gigTerms, gigWhen } from "@/components/gigs/GigPreviewCard";

import { canCreate, draftFromGig, emptyDraft, rupees, toPayload, wholeNumber } from "./draft";
import { gig } from "../../../test/fixtures";

describe("toPayload", () => {
  it("turns empty inputs into nulls and numbers into numbers", () => {
    const payload = toPayload({ ...emptyDraft("p1"), hours_per_day: "4", slots: "" });
    expect(payload).toMatchObject({
      property: "p1",
      start_date: null,
      end_date: null,
      duration_days: null,
      hours_per_day: 4,
      slots: 1,
      stipend_amount: null,
      required_verification: "id_verified",
    });
  });

  it("sends an end date or a duration, never both", () => {
    const draft = { ...emptyDraft(), end_date: "2027-01-01", duration_days: "10" };
    expect(toPayload(draft)).toMatchObject({ end_date: "2027-01-01", duration_days: null });
    expect(toPayload({ ...draft, length_mode: "duration" })).toMatchObject({
      end_date: null,
      duration_days: 10,
    });
  });

  it("drops what the pay model doesn't use", () => {
    const draft = {
      ...emptyDraft(),
      stipend_amount: "6,000",
      stipend_period: "per_month" as const,
      deliverables: [{ type: "instagram_reel" as const, quantity: "3", notes: " Reels " }],
    };
    expect(toPayload({ ...draft, compensation_model: "volunteer" })).toMatchObject({
      stipend_amount: null,
      stipend_period: "",
      deliverables: [],
    });
    expect(toPayload({ ...draft, compensation_model: "hybrid" })).toMatchObject({
      stipend_amount: "6000.00",
      stipend_period: "per_month",
      deliverables: [{ type: "instagram_reel", quantity: 3, notes: "Reels" }],
    });
  });

  it("drops blank screening questions", () => {
    expect(
      toPayload({ ...emptyDraft(), screening_questions: [" Why us? ", "  "] }).screening_questions,
    ).toEqual(["Why us?"]);
  });
});

describe("draftFromGig", () => {
  it("round-trips a saved gig", () => {
    const draft = draftFromGig(gig);
    expect(draft).toMatchObject({ title: gig.title, slots: "2", hours_per_day: "4" });
    expect(toPayload(draft)).toMatchObject({
      start_date: gig.start_date,
      end_date: gig.end_date,
      stay_type: gig.stay_type,
    });
  });

  it("picks duration mode when the gig has a duration and no end date", () => {
    expect(draftFromGig({ ...gig, end_date: null, duration_days: 14 }).length_mode).toBe(
      "duration",
    );
  });
});

describe("number inputs", () => {
  it("parses whole numbers and rupees strictly", () => {
    expect(wholeNumber("")).toBeNull();
    expect(wholeNumber("12")).toBe(12);
    expect(wholeNumber("1.5")).toBeNaN();
    expect(rupees("₹ 6,000.50")).toBe(6000.5);
    expect(rupees("6.555")).toBeNaN();
  });
});

describe("canCreate", () => {
  it("needs property, title, role and pay model", () => {
    const ready = {
      ...emptyDraft("p1"),
      title: "Chef",
      role_template: "specialist" as const,
      compensation_model: "paid" as const,
    };
    expect(canCreate(ready)).toBe(true);
    expect(canCreate({ ...ready, title: "  " })).toBe(false);
    expect(canCreate({ ...ready, property: "" })).toBe(false);
  });
});

describe("preview text", () => {
  it("summarises the terms and dates like the design's card", () => {
    const draft = {
      ...draftFromGig(gig),
      compensation_model: "hybrid" as const,
      stipend_amount: "6000",
      stipend_period: "per_month" as const,
    };
    expect(gigTerms(draft)).toBe(
      "4 hrs/day · 5 days/week · dorm bed + all meals · ₹6,000/month stipend",
    );
    expect(gigWhen(draft)).toBe("From 12 Dec · 2 slots");
  });
});
