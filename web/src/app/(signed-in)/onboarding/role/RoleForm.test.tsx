import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse, vendorUser } from "../../../../../test/http";

import { RoleForm } from "./RoleForm";

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
    await user.click(screen.getByRole("button", { name: "Continue" }));

    await vi.waitFor(() => expect(onChosen).toHaveBeenCalledWith(vendorUser));
    expect(await (network.mock.calls[0]![0] as Request).json()).toEqual({ role: "vendor" });
  });

  it("carries on if the role was already chosen elsewhere", async () => {
    network.mockResolvedValueOnce(jsonResponse(409, errorBody("role_already_set")));
    const onChosen = vi.fn();
    const user = userEvent.setup();
    render(<RoleForm onChosen={onChosen} />);
    await user.click(screen.getByRole("radio", { name: /I'm talent/ }));
    await user.click(screen.getByRole("button", { name: "Continue" }));
    await vi.waitFor(() => expect(onChosen).toHaveBeenCalledWith(null));
  });
});
