import { createHmac } from "node:crypto";

import { expect, test, type BrowserContext } from "@playwright/test";

/**
 * The arrivals screen as a PWA, against a faked API: it opens with no network once
 * visited, checks a code offline, queues the check-in and syncs it when back online.
 */

const vendor = {
  id: "8b0c1d2e-0000-4000-8000-000000000001",
  phone: "+919876543210",
  email: null,
  role: "vendor",
  is_active: true,
  profile_complete: true,
  created_at: "2026-11-01T10:00:00Z",
};

const SECRET = "JBSWY3DPEHPK3PXP";

function base32(text: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of text) bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  const bytes = bits.match(/.{8}/g) ?? [];
  return Buffer.from(bytes.map((b) => parseInt(b, 2)));
}

/** The six-digit code the talent's app would show now (RFC 6238, 5-minute step). */
function codeNow(): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 1000 / 300)));
  const digest = createHmac("sha1", base32(SECRET)).update(counter).digest();
  const offset = digest[digest.length - 1]! & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

function today() {
  const now = new Date();
  return {
    date: now.toISOString().slice(0, 10),
    generated_at: now.toISOString(),
    public_keys: [{ kid: "k1", alg: "Ed25519", public_key: "AAAA" }],
    code_period_seconds: 300,
    clock_skew_seconds: 120,
    arrivals: [
      {
        booking_id: "b-1",
        talent_id: "t-1",
        talent_name: "Aarav Mehta",
        gig_title: "Mural for the café",
        property_name: "Sea Breeze",
        start_date: now.toISOString().slice(0, 10),
        end_date: "2027-01-31",
        status: "confirmed",
        problem: "",
        pass_id: "p-1",
        code_secret: SECRET,
        pass_valid_from: new Date(Date.now() - 3600_000).toISOString(),
        pass_valid_until: new Date(Date.now() + 86_400_000).toISOString(),
        no_show_from: new Date(Date.now() + 3600_000).toISOString(),
      },
    ],
    in_house: [],
  };
}

async function fakeApi(context: BrowserContext, synced: unknown[]) {
  await context.addCookies([
    { name: "barterly_refresh", value: "e2e", domain: "localhost", path: "/" },
  ]);
  // context.route also sees requests that pass through the service worker.
  await context.route("**/api/v1/me/", (route) => route.fulfill({ json: vendor }));
  await context.route("**/api/v1/attendance/arrivals/", (route) =>
    route.fulfill({ json: today() }),
  );
  await context.route("**/api/v1/attendance/hours/pending/", (route) =>
    route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } }),
  );
  await context.route("**/api/v1/notifications/**", (route) =>
    route.fulfill({ json: { count: 0, next: null, previous: null, results: [], unread: 0 } }),
  );
  await context.route("**/api/v1/attendance/sync/", async (route) => {
    const { events } = route.request().postDataJSON() as { events: Array<{ client_id: string }> };
    synced.push(...events);
    await route.fulfill({
      json: {
        results: events.map((e) => ({
          client_id: e.client_id,
          status: "applied",
          message: "",
          booking_id: "b-1",
        })),
      },
    });
  });
}

test("checks a talent in by code with no network, and syncs when it's back", async ({
  page,
  context,
}) => {
  const synced: unknown[] = [];
  await fakeApi(context, synced);

  await page.goto("/console/arrivals");
  await expect(page.getByText("Aarav Mehta")).toBeVisible();
  // Let the service worker take control, and visit once more so it keeps the page.
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect(page.getByText("Aarav Mehta")).toBeVisible();

  await context.setOffline(true);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Arrivals" })).toBeVisible();
  await expect(page.getByText("Aarav Mehta")).toBeVisible();
  await expect(page.getByText("Offline", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Enter code" }).click();
  await page.getByLabel("Six-digit code").fill(codeNow());
  await page.getByRole("dialog").getByRole("button", { name: "Check in" }).click();
  await expect(page.getByText("Checked in · waiting to sync")).toBeVisible();
  expect(synced).toHaveLength(0);

  await context.setOffline(false);
  await expect.poll(() => synced.length).toBe(1);
  expect(synced[0]).toMatchObject({ booking_id: "b-1", method: "code" });
  await expect(page.getByText(/Synced 1 check-in/)).toBeVisible();
});

test("the console can be installed: a manifest that opens on arrivals", async ({ request }) => {
  const manifest = await (await request.get("/manifest.webmanifest")).json();
  expect(manifest).toMatchObject({ start_url: "/console/arrivals", display: "standalone" });
});
