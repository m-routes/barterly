import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { vendorUser } from "../../../test/http";
import { nav } from "../../../test/navigation";
import { ApiError } from "@/lib/api/errors";
import type { SessionState } from "@/lib/session/session";

import { RequireRole } from "./RequireRole";

vi.mock("next/navigation", async () => (await import("../../../test/navigation")).navigationMock);

const session = {
  state: { status: "loading" } as SessionState,
  reload: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("@/lib/session/session", () => ({ useSession: () => session }));

function renderGuard(requireComplete = false) {
  return render(
    <RequireRole role="vendor" requireComplete={requireComplete}>
      {(user) => <p>Welcome {user.phone}</p>}
    </RequireRole>,
  );
}

beforeEach(() => {
  nav.reset();
  session.reload.mockReset();
  session.signOut.mockReset();
});

describe("RequireRole", () => {
  it("shows a loading state while the session loads", () => {
    session.state = { status: "loading" };
    renderGuard();
    expect(screen.getByRole("status")).toHaveTextContent("Loading your account");
  });

  it("renders the page for the right role", () => {
    session.state = { status: "signed-in", user: vendorUser };
    renderGuard(true);
    expect(screen.getByText("Welcome +919876543210")).toBeVisible();
    expect(nav.router.replace).not.toHaveBeenCalled();
  });

  it("sends people without a role to choose one", () => {
    session.state = { status: "signed-in", user: { ...vendorUser, role: "" } };
    renderGuard();
    expect(nav.router.replace).toHaveBeenCalledWith("/onboarding/role");
    expect(screen.queryByText(/Welcome/)).toBeNull();
  });

  it("sends vendors to finish their profile when the page needs it", () => {
    session.state = { status: "signed-in", user: { ...vendorUser, profile_complete: false } };
    renderGuard(true);
    expect(nav.router.replace).toHaveBeenCalledWith("/onboarding/vendor");
  });

  it("explains, rather than redirects, when the role is wrong", async () => {
    nav.pathname = "/console";
    session.state = { status: "signed-in", user: { ...vendorUser, role: "talent" } };
    renderGuard();
    expect(screen.getByRole("heading", { name: "The web console is for vendors" })).toBeVisible();
    await userEvent.setup().click(screen.getByRole("button", { name: "Go to my home" }));
    expect(nav.router.replace).toHaveBeenCalledWith("/talent");
  });

  it("offers a retry when /me fails", async () => {
    session.state = {
      status: "error",
      error: new ApiError({
        status: 502,
        code: "api_unavailable",
        message: "We couldn't reach Barterly.",
      }),
    };
    renderGuard();
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn't reach Barterly.");
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(session.reload).toHaveBeenCalled();
  });
});
