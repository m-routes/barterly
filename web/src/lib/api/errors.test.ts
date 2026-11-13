import { describe, expect, it } from "vitest";

import { ApiError, describeError, fieldErrors, toApiError } from "./errors";

describe("toApiError", () => {
  it("falls back to a generic error when the body isn't the API's shape", () => {
    const error = toApiError(new Response("<html>", { status: 502 }), "<html>");
    expect(error).toMatchObject({ status: 502, code: "server_error" });
    expect(error.message).toBe("Something went wrong. Try again.");
  });
});

describe("fieldErrors", () => {
  it("takes the first message per field and maps non_field_errors to root", () => {
    const error = new ApiError({
      status: 400,
      code: "validation_error",
      message: "Invalid input.",
      details: { city: ["Too long.", "Other."], non_field_errors: ["Nope."], odd: [{ x: 1 }] },
    });
    expect(fieldErrors(error)).toEqual({ city: "Too long.", root: "Nope." });
  });

  it("is empty for errors that aren't validation errors", () => {
    expect(fieldErrors(new ApiError({ status: 409, code: "conflict", message: "x" }))).toEqual({});
  });
});

describe("describeError", () => {
  it("adds the request id to server errors so support can find them", () => {
    const error = new ApiError({
      status: 500,
      code: "server_error",
      message: "Broke.",
      requestId: "r1",
    });
    expect(describeError(error)).toBe("Broke. (Reference: r1)");
  });

  it("never shows a raw exception message", () => {
    expect(describeError(new Error("TypeError: x is undefined"))).toBe(
      "Something went wrong. Try again.",
    );
  });
});
