import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LEGAL_VERSION } from "@/lib/legal/documents";

import { jsonResponse } from "../../../../../test/http";

import { ConsentForm } from "./ConsentForm";

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn(async () => jsonResponse(200, []));
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ConsentForm", () => {
  it("records the terms and the privacy policy as two separate consents", async () => {
    const onAccepted = vi.fn();
    const user = userEvent.setup();
    render(<ConsentForm onAccepted={onAccepted} />);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Accept the terms of service to continue.")).toBeVisible();
    expect(network).not.toHaveBeenCalled();

    await user.click(screen.getByRole("checkbox", { name: /terms of service/ }));
    await user.click(screen.getByRole("checkbox", { name: /privacy policy/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await vi.waitFor(() => expect(onAccepted).toHaveBeenCalled());
    const bodies = await Promise.all(
      network.mock.calls.map(([request]) => (request as Request).json()),
    );
    expect(bodies).toEqual([
      { purpose: "terms", granted: true, version: LEGAL_VERSION, source: "web" },
      { purpose: "privacy", granted: true, version: LEGAL_VERSION, source: "web" },
    ]);
  });
});
