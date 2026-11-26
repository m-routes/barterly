import { expect, test } from "@playwright/test";

import { fixturesFor, national, OTP_CODE, persona } from "./env";
import { api, contextFor, signIn } from "./steps";
import { passCode } from "./talent";

/**
 * Failure scenarios people actually hit, through the real UI where there is one.
 * (Backend: backend/apps/qa/tests/test_failure_scenarios.py; offline apply in the app:
 * mobile/integration_test/failures_test.dart.)
 *
 * Starts from `manage.py prepare_journey --talent trip_leader`.
 */
type Fixtures = {
  booking_arriving_today: string;
  booking_arriving_today_title: string;
  booking_unfunded: string;
  booking_starts_tomorrow: string;
  booking_starts_tomorrow_title: string;
  booking_starts_tomorrow_agreement: string;
};

test("a wrong sign-in code is explained, and signs nobody in", async ({ page }) => {
  await page.goto("/login?test_numbers=1");
  await page.getByLabel("Mobile number").fill(national(persona("volunteer").phone));
  await page.getByRole("button", { name: "Send code" }).click();
  const wrong = OTP_CODE === "000000" ? "111111" : "000000";
  await page.getByRole("textbox", { name: "Code" }).fill(wrong);
  await page.getByRole("button", { name: "Verify and continue" }).click();
  await expect(page.getByText("That code isn't right. Check the SMS and try again.")).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
  const me = await page.request.get("/api/v1/me/");
  expect(me.status()).toBe(401);
});

test("a check-in made offline is kept and syncs when the network returns", async ({
  page,
  browser,
  context,
}) => {
  const ids = fixturesFor<Fixtures>("trip_leader");
  const talent = await contextFor(browser, persona("trip_leader"));
  const code = await passCode(talent, ids.booking_arriving_today);

  await signIn(page, persona("hostel_owner"));
  await page.goto("/console/arrivals");
  // Today's list (and the keys to check passes) must load once before going offline.
  const row = page
    .locator("main:visible")
    .getByRole("listitem")
    .filter({ hasText: ids.booking_arriving_today_title });
  await expect(row).toBeVisible();
  await context.setOffline(true);
  await row.getByRole("button", { name: "Enter code" }).click();
  await page.getByLabel("Six-digit code").fill(code);
  await page.getByRole("dialog").getByRole("button", { name: "Check in" }).click();
  await expect(page.getByText("Checked in · waiting to sync").first()).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByText(/Synced \d+ check-in/)).toBeVisible({ timeout: 30_000 });
  await expect
    .poll(
      async () =>
        (
          await api<{ status: string }>(
            talent,
            "GET",
            `/api/v1/bookings/${ids.booking_arriving_today}/`,
          )
        ).status,
    )
    .toMatch(/checked_in|delivering/);
  await talent.close();
});

test("tapping pay twice makes one order, not two charges", async ({ page }) => {
  const ids = fixturesFor<Fixtures>("trip_leader");
  await signIn(page, persona("cafe_owner"));
  const url = `/api/v1/bookings/${ids.booking_unfunded}/escrow/fund/`;
  const [one, two] = await Promise.all([
    api<{ order_id: string; escrow: { id: string } }>(page.context(), "POST", url, {}),
    api<{ order_id: string; escrow: { id: string } }>(page.context(), "POST", url, {}),
  ]);
  expect(one.order_id).toBe(two.order_id);
  expect(one.escrow.id).toBe(two.escrow.id);
});

test("a host cancelling the day before sees the cost first, and it's recorded", async ({
  page,
}) => {
  const ids = fixturesFor<Fixtures>("trip_leader");
  await signIn(page, persona("hostel_owner"));
  await page.goto(`/console/agreements/${ids.booking_starts_tomorrow_agreement}`);
  await page.getByRole("button", { name: "Cancel this booking" }).click();
  await page.getByLabel("Reason").selectOption({ index: 1 });
  await page.getByLabel("More about why (optional)").fill("Burst pipe; the dorm is closed.");
  if (process.env.EXPLORE)
    console.log(
      "PANEL:",
      await page.getByRole("heading", { name: "Cancel this booking" }).locator("..").innerText(),
    );
  // The cost of cancelling this late is shown before confirming.
  await expect(page.getByText(/counts as a last-minute cancellation/)).toBeVisible();
  await expect(page.getByText(/the stay starts in 1 day\./)).toBeVisible();
  await page.getByRole("button", { name: "Cancel the booking" }).click();
  await expect
    .poll(
      async () =>
        (
          await api<{ status: string }>(
            page.context(),
            "GET",
            `/api/v1/bookings/${ids.booking_starts_tomorrow}/`,
          )
        ).status,
    )
    .toBe("cancelled");
});
