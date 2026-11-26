import { expect, test } from "@playwright/test";

import { fixturesFor, persona } from "./env";
import { api, contextFor, dump, signIn } from "./steps";
import { handIn } from "./talent";

/**
 * Core journey, part 2: after the stay. The talent hands in the reel, the host approves
 * it, which releases the escrow and pays the talent, and both review each other.
 *
 * Starts from `manage.py prepare_journey --talent creator`: a paid stay at the café,
 * escrow funded, the reel due.
 */
type Fixtures = {
  booking_deliverable_due: string;
  booking_deliverable_due_title: string;
};

test("the talent hands in, the host approves and the money is released", async ({
  page,
  browser,
}) => {
  const ids = fixturesFor<Fixtures>("creator");
  const host = persona("cafe_owner");
  const talentPersona = persona("creator");
  const bookingId = ids.booking_deliverable_due;
  const talent = await contextFor(browser, talentPersona);

  await test.step("the talent hands in the reel", async () => {
    expect(await handIn(talent, bookingId)).toBeGreaterThan(0);
  });

  await test.step("the host approves it in Content", async () => {
    await signIn(page, host);
    await page.goto("/console/content");
    const item = page
      .getByRole("region", { name: "Waiting for review" })
      .getByRole("listitem")
      .filter({ hasText: ids.booking_deliverable_due_title });
    await item.getByRole("button", { name: "Approve" }).click();
    await dump(page, "after approve");
    await expect(item).toHaveCount(0);
  });

  await test.step("approval releases the escrow and the talent is paid", async () => {
    await expect
      .poll(
        async () =>
          (
            await api<{ escrow: { status: string } | null }>(
              talent,
              "GET",
              `/api/v1/bookings/${bookingId}/escrow/`,
            )
          ).escrow?.status,
        { message: "the escrow is released" },
      )
      .toMatch(/released/);
    const wallet = await api<{ in_transit_paise: number; paid_out_paise: number }>(
      talent,
      "GET",
      "/api/v1/wallet/",
    );
    expect(wallet.in_transit_paise + wallet.paid_out_paise).toBeGreaterThan(0);
  });

  const hostApi = page.context();
  await test.step("the host checks the talent out: the stay is complete", async () => {
    await api(hostApi, "POST", `/api/v1/bookings/${bookingId}/attendance/check-out/`, {});
    const booking = await api<{ status: string }>(talent, "GET", `/api/v1/bookings/${bookingId}/`);
    expect(booking.status).toBe("completed");
  });

  await test.step("both review, and the reviews publish together", async () => {
    const scores = { communication: 5, accuracy: 5, safety: 5, reliability: 5 };
    const path = `/api/v1/bookings/${bookingId}/reviews/`;
    type Reviews = { theirs: { rating: number } | null; they_have_reviewed: boolean };
    await api(talent, "POST", path, {
      rating: 5,
      text: "A lovely café with a clear brief, quick feedback and fair, on-time pay.",
      ...scores,
    });
    // Double-blind: the host can't see the talent's review before writing their own.
    const before = await api<Reviews>(hostApi, "GET", path);
    expect(before.they_have_reviewed).toBe(true);
    expect(before.theirs).toBeNull();
    await api(hostApi, "POST", path, {
      rating: 5,
      text: "Brilliant reel, delivered on time with the right label. Would host again.",
      ...scores,
    });
    const after = await api<Reviews>(talent, "GET", path);
    expect(after.theirs?.rating).toBe(5);
  });
  await talent.close();
});
