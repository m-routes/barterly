import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../../../test/http";

import { HelpCenter } from "./HelpCenter";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

let network: ReturnType<typeof vi.fn>;

const ticket = {
  id: "3f2a6c1e-8b7d-4e0f-9a1b-2c3d4e5f6a7b",
  reference: "S-3F2A6C1E",
  kind: "bug",
  subject: "Can't upload my reel",
  status: "open",
  booking: null,
  created_at: "2026-11-24T10:00:00+05:30",
  last_message_at: "2026-11-24T10:00:00+05:30",
  reply_expected_by: "2026-11-25T10:00:00+05:30",
  messages: [],
};

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
  push.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HelpCenter", () => {
  it("lists earlier requests", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, [ticket]));
    render(<HelpCenter basePath="/console/help" />);
    const link = await screen.findByRole("link", { name: "Can't upload my reel" });
    expect(link).toHaveAttribute("href", `/console/help/${ticket.id}`);
    expect(screen.getByText(/Waiting for us/)).toBeVisible();
  });

  it("checks the form, then sends it and opens the request", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, []));
    const user = userEvent.setup();
    render(<HelpCenter basePath="/console/help" screen="console/help" />);
    await user.click(await screen.findByRole("button", { name: "Send" }));
    expect(screen.getByText("Choose what it's about.")).toBeVisible();
    expect(network).toHaveBeenCalledTimes(1);

    network
      .mockResolvedValueOnce(jsonResponse(201, ticket))
      .mockResolvedValue(jsonResponse(200, [ticket]));
    await user.selectOptions(screen.getByRole("combobox", { name: /What's it about/ }), "safety");
    expect(screen.getByText(/Call 112/)).toBeVisible();
    await user.type(screen.getByRole("textbox", { name: "Title" }), "Host asked for a deposit");
    await user.type(screen.getByRole("textbox", { name: /Message/ }), "Before I arrive.");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await vi.waitFor(() => expect(push).toHaveBeenCalledWith(`/console/help/${ticket.id}`));
    const sent = await (network.mock.calls[1]![0] as Request).json();
    expect(sent).toEqual({
      kind: "safety",
      subject: "Host asked for a deposit",
      body: "Before I arrive.",
      platform: "web",
      screen: "console/help",
    });
  });
});
