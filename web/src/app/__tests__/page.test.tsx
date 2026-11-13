import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../page";

describe("Landing page", () => {
  it("has one h1, a sign-in route and all pay models", () => {
    render(<Home />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(
      screen.getByRole("heading", { level: 1, name: /find talent for your stay/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Get started" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    const list = screen.getByRole("list", { name: /pay models/i });
    expect(within(list).getAllByRole("listitem")).toHaveLength(4);
  });
});
