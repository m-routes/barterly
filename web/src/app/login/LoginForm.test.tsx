import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse, vendorUser } from "../../../test/http";
import { nav } from "../../../test/navigation";
import type { PhoneSignIn } from "@/lib/firebase/phoneAuth";

import { LoginForm } from "./LoginForm";

vi.mock("next/navigation", async () => (await import("../../../test/navigation")).navigationMock);

function fakeSignIn(overrides: Partial<{ send: unknown; confirm: unknown }> = {}) {
  const confirm = vi.fn(async (code: string) => {
    if (overrides.confirm) throw overrides.confirm;
    if (code !== "123456") throw { code: "auth/invalid-verification-code" };
    return "firebase-id-token";
  });
  const signIn: PhoneSignIn & { sendCode: ReturnType<typeof vi.fn> } = {
    sendCode: vi.fn(async () => {
      if (overrides.send) throw overrides.send;
      return { confirm };
    }),
    reset: vi.fn(async () => undefined),
  };
  return signIn;
}

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  nav.reset();
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function enterPhone(signIn: PhoneSignIn, phone = "98765 43210") {
  const user = userEvent.setup();
  render(<LoginForm phoneSignIn={signIn} />);
  await user.type(screen.getByLabelText("Mobile number"), phone);
  await user.click(screen.getByRole("button", { name: "Send code" }));
  return user;
}

describe("LoginForm", () => {
  it("checks the number before sending a code", async () => {
    const signIn = fakeSignIn();
    await enterPhone(signIn, "12345");
    expect(await screen.findByText("Enter a 10-digit Indian mobile number.")).toBeVisible();
    expect(screen.getByLabelText("Mobile number")).toHaveAttribute("aria-invalid", "true");
    expect(signIn.sendCode).not.toHaveBeenCalled();
  });

  it("sends the code to the E.164 number and asks for it", async () => {
    const signIn = fakeSignIn();
    await enterPhone(signIn);
    expect(signIn.sendCode).toHaveBeenCalledWith("+919876543210", expect.any(HTMLElement));
    expect(await screen.findByRole("heading", { name: "Enter your code" })).toBeVisible();
    expect(screen.getByText("+919876543210")).toBeVisible();
  });

  it("explains Firebase errors when the code can't be sent", async () => {
    await enterPhone(fakeSignIn({ send: { code: "auth/too-many-requests" } }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });

  it("shows a wrong code on the code field", async () => {
    const user = await enterPhone(fakeSignIn());
    await user.type(await screen.findByLabelText("Code"), "000000");
    await user.click(screen.getByRole("button", { name: "Verify and continue" }));
    expect(await screen.findByText(/That code isn't right/)).toBeVisible();
    expect(network).not.toHaveBeenCalled();
  });

  it("exchanges the token and goes to the safe `next` page", async () => {
    nav.search = "next=/console/gigs";
    network.mockResolvedValueOnce(
      jsonResponse(200, {
        is_new_user: false,
        needs_role: false,
        profile_complete: true,
        user: vendorUser,
      }),
    );
    const signIn = fakeSignIn();
    const user = await enterPhone(signIn);
    await user.type(await screen.findByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify and continue" }));

    await vi.waitFor(() => expect(nav.router.replace).toHaveBeenCalledWith("/console/gigs"));
    const request = network.mock.calls[0]![0] as Request;
    expect(new URL(request.url).pathname).toBe("/api/v1/auth/exchange/");
    expect(await request.json()).toEqual({ id_token: "firebase-id-token" });
    expect(signIn.reset).toHaveBeenCalled();
  });

  it("sends new users to choose a role, ignoring `next`", async () => {
    nav.search = "next=/console/gigs";
    network.mockResolvedValueOnce(
      jsonResponse(200, {
        is_new_user: true,
        needs_role: true,
        profile_complete: false,
        user: { ...vendorUser, role: "", profile_complete: false },
      }),
    );
    const user = await enterPhone(fakeSignIn());
    await user.type(await screen.findByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify and continue" }));
    await vi.waitFor(() => expect(nav.router.replace).toHaveBeenCalledWith("/onboarding/role"));
  });

  it("shows the API's message when the exchange fails", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(403, errorBody("account_disabled", "This account has been disabled.")),
    );
    const user = await enterPhone(fakeSignIn());
    await user.type(await screen.findByLabelText("Code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify and continue" }));
    expect(await screen.findByText("This account has been disabled.")).toBeVisible();
    expect(nav.router.replace).not.toHaveBeenCalled();
  });

  it("lets you resend only after the countdown", async () => {
    await enterPhone(fakeSignIn());
    expect(await screen.findByRole("button", { name: /Resend code in \d+s/ })).toBeDisabled();
  });
});
