import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse, vendorUser } from "../../../../../test/http";

import { LEGAL_VERSION } from "@/lib/legal/documents";

import { RoleForm } from "./RoleForm";

async function agreeToEverything(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("checkbox", { name: "I am 18 or older." }));
  await user.click(screen.getByRole("checkbox", { name: /terms of service/ }));
  await user.click(screen.getByRole("checkbox", { name: /privacy policy/ }));
}

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RoleForm", () => {
  it("asks for a choice", async () => {
    const user = userEvent.setup();
    render(<RoleForm onChosen={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Choose how you'll use Barterly.")).toBeVisible();
    expect(network).not.toHaveBeenCalled();
  });

  it("saves the role and hands back the updated user", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, vendorUser));
    const onChosen = vi.fn();
    const user = userEvent.setup();
    render(<RoleForm onChosen={onChosen} />);
    await user.click(screen.getByRole("radio", { name: /I run a place/ }));
    await agreeToEverything(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await vi.waitFor(() => expect(onChosen).toHaveBeenCalledWith(vendorUser));
    expect(await (network.mock.calls[0]![0] as Request).json()).toEqual({
      role: "vendor",
      confirm_adult: true,
      terms_version: LEGAL_VERSION,
      privacy_version: LEGAL_VERSION,
      source: "web",
    });
  });

  it("carries on if the role was already chosen elsewhere", async () => {
    network.mockResolvedValueOnce(jsonResponse(409, errorBody("role_already_set")));
    const onChosen = vi.fn();
    const user = userEvent.setup();
    render(<RoleForm onChosen={onChosen} />);
    await user.click(screen.getByRole("radio", { name: /I'm talent/ }));
    await agreeToEverything(user);
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await vi.waitFor(() => expect(onChosen).toHaveBeenCalledWith(null));
  });

  it("needs the 18+ declaration and each agreement, separately", async () => {
    const user = userEvent.setup();
    render(<RoleForm onChosen={vi.fn()} />);
    await user.click(screen.getByRole("radio", { name: /I'm talent/ }));
    await user.click(screen.getByRole("checkbox", { name: /terms of service/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("You must be 18 or older to use Barterly.")).toBeVisible();
    expect(screen.getByText("Accept the privacy policy to continue.")).toBeVisible();
    expect(screen.queryByText("Accept the terms of service to continue.")).toBeNull();
    expect(network).not.toHaveBeenCalled();
  });

  it("links to the legal pages", () => {
    render(<RoleForm onChosen={vi.fn()} />);
    expect(screen.getByRole("link", { name: "terms of service" })).toHaveAttribute(
      "href",
      "/legal/terms",
    );
    expect(screen.getByRole("link", { name: "privacy policy" })).toHaveAttribute(
      "href",
      "/legal/privacy",
    );
  });
});
