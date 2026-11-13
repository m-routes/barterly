import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse, vendorUser } from "../../../test/http";
import { nav } from "../../../test/navigation";
import { emitApiEvent } from "@/lib/api/events";

import { SessionProvider, useSession } from "./session";

vi.mock("next/navigation", async () => (await import("../../../test/navigation")).navigationMock);

function Probe() {
  const { state } = useSession();
  return <p>{state.status === "signed-in" ? `in:${state.user.role}` : state.status}</p>;
}

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  nav.reset();
  nav.pathname = "/console/gigs";
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SessionProvider", () => {
  it("loads the signed-in user", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, vendorUser));
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    );
    expect(screen.getByText("loading")).toBeVisible();
    expect(await screen.findByText("in:vendor")).toBeVisible();
  });

  it("sends signed-out people to /login, coming back here after", async () => {
    // /me is 401, and so is the refresh.
    network.mockResolvedValue(jsonResponse(401, errorBody("not_authenticated")));
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    );
    await vi.waitFor(() =>
      expect(nav.router.replace).toHaveBeenCalledWith("/login?next=%2Fconsole%2Fgigs"),
    );
  });

  it("keeps errors that aren't about sign-in, for the page to show", async () => {
    network.mockResolvedValue(jsonResponse(502, errorBody("api_unavailable")));
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    );
    expect(await screen.findByText("error")).toBeVisible();
    expect(nav.router.replace).not.toHaveBeenCalled();
  });

  it("signs out when any call reports the session expired", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, vendorUser));
    render(
      <SessionProvider>
        <Probe />
      </SessionProvider>,
    );
    await screen.findByText("in:vendor");
    act(() => emitApiEvent({ type: "session-expired" }));
    await vi.waitFor(() => expect(nav.router.replace).toHaveBeenCalled());
    expect(nav.router.replace.mock.calls[0]![0]).toMatch(/^\/login\?next=/);
  });
});
