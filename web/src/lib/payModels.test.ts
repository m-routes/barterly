import { describe, expect, it } from "vitest";

import { PAY_MODELS, describePayModel } from "./payModels";

describe("describePayModel", () => {
  it("formats each pay model with its label and summary", () => {
    expect(describePayModel("volunteer")).toBe("Volunteer: Work for stay");
    expect(describePayModel("hybrid")).toBe("Hybrid: Stay plus stipend");
  });

  it("covers all four pay models", () => {
    expect(Object.keys(PAY_MODELS)).toEqual(["volunteer", "barter", "hybrid", "paid"]);
  });
});
