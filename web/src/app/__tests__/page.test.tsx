import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "../page";

describe("Home page", () => {
  it("renders the heading and all pay models", () => {
    render(<Home />);
    expect(
      screen.getByRole("heading", { level: 1, name: /barterly vendor console/i }),
    ).toBeInTheDocument();
    const list = screen.getByRole("list", { name: /pay models/i });
    expect(within(list).getAllByRole("listitem")).toHaveLength(4);
  });
});
