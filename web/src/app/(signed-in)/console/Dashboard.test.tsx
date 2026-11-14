import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { photo, page, property, vendorProfile, verification } from "../../../../test/fixtures";
import { errorBody, jsonResponse } from "../../../../test/http";

import { Dashboard } from "./Dashboard";

let answers: Record<string, () => Response>;

beforeEach(() => {
  answers = {
    "/api/v1/profiles/vendor/me/": () => jsonResponse(200, vendorProfile),
    "/api/v1/properties/": () =>
      jsonResponse(200, page([{ ...property, photos: [photo(), photo(), photo()] }])),
    "/api/v1/verification/me/": () => jsonResponse(200, verification),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((request: Request) => Promise.resolve(answers[new URL(request.url).pathname]!())),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Dashboard", () => {
  it("shows the setup checklist with the next step highlighted", async () => {
    render(<Dashboard />);
    expect(await screen.findByRole("heading", { name: "Get ready to host" })).toBeVisible();
    expect(screen.getByText("3 of 5 done")).toBeVisible();
    expect(screen.getByRole("heading", { name: /Business details \(done\)/ })).toBeVisible();
    expect(screen.getByRole("heading", { name: /Start your ID check \(to do\)/ })).toBeVisible();
    const next = screen.getByRole("link", { name: "Start ID check: Start your ID check" });
    expect(next).toHaveClass("button--primary");
    expect(next).toHaveAttribute("href", "/console/verification");
  });

  it("treats a missing profile as a step to do, not an error", async () => {
    answers["/api/v1/profiles/vendor/me/"] = () =>
      jsonResponse(404, errorBody("profile_not_found", "No profile yet."));
    answers["/api/v1/properties/"] = () => jsonResponse(200, page([]));
    render(<Dashboard />);
    expect(await screen.findByText("0 of 5 done")).toBeVisible();
    expect(screen.getByRole("link", { name: "Add details: Business details" })).toBeVisible();
  });

  it("offers a retry when loading fails", async () => {
    answers["/api/v1/verification/me/"] = () =>
      jsonResponse(500, errorBody("server_error", "Oops."));
    render(<Dashboard />);
    expect(
      await screen.findByRole("heading", { name: "We couldn't load your dashboard" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Try again" })).toBeVisible();
  });
});
