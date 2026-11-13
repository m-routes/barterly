import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/errors";
import { emitApiEvent } from "@/lib/api/events";

import { Toaster } from "./Toaster";

const serverError = new ApiError({
  status: 500,
  code: "server_error",
  message: "Something went wrong on our side.",
  requestId: "req-7",
});

describe("Toaster", () => {
  it("shows API errors once each, with the reference, and can be dismissed", async () => {
    render(<Toaster />);
    act(() => {
      emitApiEvent({ type: "error", error: serverError });
      emitApiEvent({ type: "error", error: serverError });
    });
    const toasts = screen.getAllByRole("alert");
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toHaveTextContent("Something went wrong on our side. (Reference: req-7)");

    await userEvent.setup().click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("ignores session-expired events (the session handles those)", () => {
    render(<Toaster />);
    act(() => emitApiEvent({ type: "session-expired" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
