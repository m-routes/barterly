import { describe, expect, it } from "vitest";

import { emptyDraft, type GigDraft } from "@/lib/gigs/draft";

import { checkComplete, checkShape, gigLengthDays, stepOf, todayIso } from "./gig";

const TODAY = "2026-11-14";

/** A gig that passes every rule (volunteer, dated in the future). */
function complete(overrides: Partial<GigDraft> = {}): GigDraft {
  return {
    ...emptyDraft("p1"),
    title: "Reception and social media volunteer",
    description: "Front desk mornings and two stories a week.",
    role_template: "volunteer",
    compensation_model: "volunteer",
    slots: "2",
    start_date: "2026-12-12",
    end_date: "2027-01-12",
    apply_by: "2026-12-05",
    hours_per_day: "4",
    days_per_week: "5",
    stay_type: "dorm_bed",
    meals: "all_meals",
    ...overrides,
  };
}

describe("checkShape (every save)", () => {
  it("accepts an empty draft", () => {
    expect(checkShape(emptyDraft())).toEqual({});
  });

  it("caps hours, days and slots like the backend", () => {
    const errors = checkShape(complete({ hours_per_day: "7", days_per_week: "7", slots: "0" }));
    expect(errors.hours_per_day).toBe("At most 6 hours a day.");
    expect(errors.days_per_week).toBe("Give at least one day off a week (at most 6 working days).");
    expect(errors.slots).toBe("At least 1 slot.");
  });

  it("says when a number isn't a whole number", () => {
    expect(checkShape(complete({ hours_per_day: "4.5" })).hours_per_day).toBe(
      "Enter a whole number.",
    );
  });

  it("checks the dates against each other", () => {
    const errors = checkShape(
      complete({ start_date: "2026-12-12", end_date: "2026-12-10", apply_by: "2026-12-20" }),
    );
    expect(errors.end_date).toBe("The end date must be after the start date.");
    expect(errors.apply_by).toBe("Applications must close on or before the start date.");
  });

  it("keeps the minimum stay within the gig, by end date or by duration", () => {
    expect(checkShape(complete({ min_stay_days: "40" })).min_stay_days).toBe(
      "The minimum stay can't be longer than the gig.",
    );
    const byDuration = complete({
      length_mode: "duration",
      duration_days: "10",
      min_stay_days: "14",
    });
    expect(checkShape(byDuration).min_stay_days).toBeDefined();
    expect(
      checkShape(complete({ length_mode: "duration", duration_days: "400" })).duration_days,
    ).toBe("Between 1 and 365 days.");
  });

  it("checks deliverables only on barter and hybrid gigs", () => {
    const bad = [{ type: "instagram_reel" as const, quantity: "80", notes: "" }];
    expect(
      checkShape(complete({ compensation_model: "barter", deliverables: bad })).deliverables,
    ).toBe("Each deliverable needs a known type, a quantity from 1 to 50 and short notes.");
    // On a volunteer gig they're dropped from the payload, so not an error here.
    expect(checkShape(complete({ deliverables: bad })).deliverables).toBeUndefined();
  });

  it("limits screening questions", () => {
    const six = Array.from({ length: 6 }, (_, i) => `Question ${i}?`);
    expect(checkShape(complete({ screening_questions: six })).screening_questions).toBe(
      "At most 5 questions of up to 300 characters.",
    );
  });

  it("rejects a zero or malformed stipend on a paid gig", () => {
    expect(
      checkShape(complete({ compensation_model: "paid", stipend_amount: "0" })).stipend_amount,
    ).toBe("The stipend must be more than zero.");
    expect(
      checkShape(complete({ compensation_model: "paid", stipend_amount: "lots" })).stipend_amount,
    ).toBeDefined();
  });
});

describe("checkComplete (before review)", () => {
  it("passes a complete gig", () => {
    expect(checkComplete(complete(), TODAY)).toEqual({});
  });

  it("lists every required field", () => {
    const errors = checkComplete(emptyDraft(), TODAY);
    expect(Object.keys(errors).sort()).toEqual(
      [
        "apply_by",
        "compensation_model",
        "days_per_week",
        "description",
        "end_date",
        "hours_per_day",
        "meals",
        "property",
        "role_template",
        "start_date",
        "stay_type",
        "title",
      ].sort(),
    );
    expect(errors.title).toBe("Required before the gig can be reviewed.");
  });

  it("needs future dates", () => {
    const errors = checkComplete(complete({ start_date: TODAY, apply_by: "2026-11-01" }), TODAY);
    expect(errors.start_date).toBe("The start date must be in the future.");
    expect(errors.apply_by).toBe("The apply-by date has passed.");
  });

  it("applies the pay model's own rules", () => {
    expect(checkComplete(complete({ stay_type: "none" }), TODAY).stay_type).toBe(
      "Volunteer gigs must say where volunteers stay.",
    );
    expect(checkComplete(complete({ compensation_model: "barter" }), TODAY).deliverables).toBe(
      "Barter gigs need at least one deliverable.",
    );
    const hybrid = checkComplete(
      complete({ compensation_model: "hybrid", stay_type: "none" }),
      TODAY,
    );
    expect(hybrid.stipend_amount).toBe("Hybrid and paid gigs need a stipend above zero.");
    expect(hybrid.stipend_period).toBe("Say whether the stipend is per week, per month or total.");
    expect(hybrid.stay_type).toBe("Hybrid gigs include a stay: say what kind.");
  });

  it("asks for an end date or a duration, matching the chosen mode", () => {
    expect(checkComplete(complete({ end_date: "" }), TODAY).end_date).toBe(
      "Give an end date or a duration.",
    );
    expect(
      checkComplete(complete({ length_mode: "duration", duration_days: "" }), TODAY).duration_days,
    ).toBe("Give an end date or a duration.");
  });
});

describe("helpers", () => {
  it("works out the gig's length", () => {
    expect(gigLengthDays(complete())).toBe(31);
    expect(gigLengthDays(complete({ length_mode: "duration", duration_days: "10" }))).toBe(10);
    expect(gigLengthDays(complete({ end_date: "" }))).toBeNull();
  });

  it("maps fields to their builder step", () => {
    expect(stepOf("stipend_amount")).toBe("pay");
    expect(stepOf("screening_questions")).toBe("questions");
    expect(stepOf("min_followers")).toBe("who");
    expect(stepOf("property")).toBe("basics");
  });

  it("formats today in local time", () => {
    expect(todayIso(new Date(2026, 0, 5, 23, 30))).toBe("2026-01-05");
  });
});
