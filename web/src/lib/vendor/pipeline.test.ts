import { describe, expect, it } from "vitest";

import { applicant } from "../../../test/fixtures";

import {
  type PipelineApplicant,
  cleanFilters,
  columns,
  initials,
  listQuery,
  moveFor,
  sameFilters,
  targetsFor,
  tintFor,
  withStatus,
} from "./pipeline";

const card = (id: string, status: PipelineApplicant["status"]): PipelineApplicant =>
  ({
    ...applicant({ id, status }),
    rejection_code: "",
    tags: [],
    note_count: 0,
  }) as PipelineApplicant;

describe("moves", () => {
  it("go forward only, and Offered means sending terms", () => {
    expect(moveFor("applied", "shortlisted")).toEqual({ kind: "status", to: "shortlisted" });
    expect(moveFor("applied", "interview")).toEqual({ kind: "status", to: "interview" });
    expect(moveFor("interview", "offered")).toEqual({ kind: "offer" });
    expect(moveFor("shortlisted", "applied").kind).toBe("none");
    expect(moveFor("interview", "interview")).toEqual({
      kind: "none",
      reason: "Already in Interview.",
    });
    expect(moveFor("offered", "offered").kind).toBe("none");
    expect(moveFor("rejected", "shortlisted").kind).toBe("none");
  });

  it("list the columns a card can go to", () => {
    expect(targetsFor("applied")).toEqual(["shortlisted", "interview", "offered"]);
    expect(targetsFor("interview")).toEqual(["offered"]);
    expect(targetsFor("offered")).toEqual([]);
  });
});

describe("the board", () => {
  it("groups cards into the four columns and moves them", () => {
    const items = [card("a", "applied"), card("b", "interview"), card("c", "applied")];
    expect(columns(items).map((c) => [c.label, c.cards.map((x) => x.id)])).toEqual([
      ["Applied", ["a", "c"]],
      ["Shortlisted", []],
      ["Interview", ["b"]],
      ["Offered", []],
    ]);
    const moved = withStatus(items, new Set(["a", "zz"]), "shortlisted");
    expect(moved.map((x) => x.status)).toEqual(["shortlisted", "interview", "applied"]);
    expect(items[0]!.status).toBe("applied"); // not mutated
  });
});

describe("filters", () => {
  it("ask for every stage with the chosen filters", () => {
    expect(listQuery({ sort: "newest", min_score: 70, q: "riya", badge: "id_verified" })).toEqual({
      status: "applied,shortlisted,interview,offered",
      page_size: 100,
      sort: "newest",
      min_score: 70,
      q: "riya",
      badge: "id_verified",
    });
    expect(listQuery({})).toEqual({
      status: "applied,shortlisted,interview,offered",
      page_size: 100,
      sort: "fit",
    });
  });

  it("compare without empty values, best fit being the default", () => {
    expect(cleanFilters({ q: "", tag: undefined, min_score: 50 })).toEqual({ min_score: 50 });
    expect(sameFilters({ min_score: 50 }, { sort: "fit", min_score: 50, q: "" })).toBe(true);
    expect(sameFilters({ min_score: 50 }, { min_score: 70 })).toBe(false);
  });
});

describe("avatars", () => {
  it("use initials and a steady tint", () => {
    expect(initials("Riya Kapoor Sharma")).toBe("RS");
    expect(initials("Asha")).toBe("A");
    expect(initials("  ")).toBe("?");
    expect(tintFor("abc")).toBe(tintFor("abc"));
  });
});
