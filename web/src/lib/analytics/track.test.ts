import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { jsonResponse } from "../../../test/http";

import { screenOf } from "./events";
import { flush, resetAnalytics, setAnalyticsConsent, track } from "./track";

let network: ReturnType<typeof vi.fn>;

beforeEach(() => {
  resetAnalytics();
  network = vi.fn();
  vi.stubGlobal("fetch", network);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function consents(analytics: boolean) {
  return jsonResponse(200, [
    { purpose: "terms", granted: true },
    { purpose: "analytics", granted: analytics },
  ]);
}

describe("screenOf", () => {
  it("takes ids out of paths", () => {
    expect(screenOf("/console/gigs/3f2a6c1e-8b7d-4e0f-9a1b-2c3d4e5f6a7b/edit")).toBe(
      "console/gigs/edit",
    );
    expect(screenOf("/")).toBe("home");
    expect(screenOf("/account/help/42")).toBe("account/help");
  });
});

describe("track", () => {
  it("sends nothing without consent", async () => {
    network.mockResolvedValueOnce(consents(false));
    track("help_opened", { screen: "console/help" });
    await flush();
    expect(network).toHaveBeenCalledTimes(1); // only the consent check
    expect((network.mock.calls[0]![0] as Request).url).toContain("/api/v1/privacy/consents/");
  });

  it("sends a batch once the person has agreed", async () => {
    network
      .mockResolvedValueOnce(consents(true))
      .mockResolvedValueOnce(jsonResponse(202, { accepted: 2, dropped: 0, consent: true }));
    track("screen_view", { screen: "console" });
    track("feedback_sent", { kind: "bug" });
    await flush();
    const sent = await (network.mock.calls[1]![0] as Request).json();
    expect(sent.platform).toBe("web");
    expect(sent.events.map((e: { name: string }) => e.name)).toEqual([
      "screen_view",
      "feedback_sent",
    ]);
  });

  it("stops at once when consent is withdrawn", async () => {
    setAnalyticsConsent(true);
    track("screen_view", { screen: "console" });
    setAnalyticsConsent(false);
    await flush();
    track("screen_view", { screen: "console/gigs" });
    await flush();
    expect(network).not.toHaveBeenCalled();
  });
});
