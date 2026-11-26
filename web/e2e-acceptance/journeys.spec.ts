import { expect, test } from "@playwright/test";

import { backOfficeSignIn, approveGig } from "./admin";
import { OTP_CODE, persona } from "./env";
import { api, contextFor, dump, signIn } from "./steps";
import { acceptOffer, apply, passCode, sign } from "./talent";
import { addProperty, inDays, onboard, postGig } from "./vendor";

/**
 * Core journey, part 1: a brand-new host signs up and posts a gig, Ops approves it, a
 * volunteer applies, is hired, both sign, and the host checks them in.
 *
 * Needs a fresh onboarding persona: `manage.py seed_staging --reset-onboarding` first.
 */
test("a new host posts a gig, hires a talent and checks them in", async ({ page, browser }) => {
  const host = persona("onboarding_vendor");
  const talentPersona = persona("journey_creator");
  const title = `Reels for the garden kitchen ${Date.now().toString(36)}`;
  const start = inDays(1); // check-in opens the day before a stay
  const end = inDays(8);

  await test.step("host signs up and sets up the business", async () => {
    await signIn(page, host);
    await onboard(page, host);
    await addProperty(page, host);
  });

  let gigId = "";
  await test.step("host posts a gig and sends it for review", async () => {
    gigId = await postGig(page, { title, startIn: 1, days: 7 });
  });

  await test.step("Ops approves it in the back office", async () => {
    const admin = await browser.newContext();
    const adminPage = await admin.newPage();
    await backOfficeSignIn(adminPage, persona("admin"));
    await approveGig(adminPage, title);
    await admin.close();
    await page.goto(`/console/gigs`);
    await dump(page, "gigs after approval");
  });

  const talent = await contextFor(browser, talentPersona);
  const talentPage = await talent.newPage();
  let applicationId = "";
  await test.step("the talent applies", async () => {
    applicationId = (await apply(talent, gigId, start, end)).id;
  });

  await test.step("host makes an offer from the applicants board", async () => {
    await page.goto(`/console/gigs/${gigId}/applicants`);
    await dump(page, "applicants");
    await page
      .getByRole("article", { name: talentPersona.name })
      .getByRole("button", { name: talentPersona.name, exact: true })
      .click();
    await page
      .getByRole("dialog", { name: talentPersona.name })
      .getByRole("link", { name: "Full page" })
      .click();
    await dump(page, "application");
    await page.getByRole("button", { name: "Make an offer" }).click();
    await page
      .getByLabel("Message (optional)")
      .fill("We'd love your reels for the garden kitchen!");
    await page.getByRole("button", { name: "Send offer" }).click();
    await dump(page, "offer sent");
  });

  let bookingId = "";
  await test.step("the talent accepts", async () => {
    bookingId = (await acceptOffer(talent, applicationId)).booking;
  });

  await test.step("both sign the agreement", async () => {
    await sign(talent, talentPage, talentPersona, bookingId);
    await page.goto("/console/agreements");
    const link = page.getByRole("link", { name: title });
    const href = await link.getAttribute("href");
    await page.goto(`${href}?test_numbers=1`);
    await page.getByRole("button", { name: "Sign version 1" }).click();
    await page.getByRole("checkbox", { name: /I have read version 1/ }).check();
    await page.getByRole("button", { name: "Send code" }).click();
    await page.getByLabel(/Code sent to/).fill(OTP_CODE);
    await page.getByRole("button", { name: "Sign", exact: true }).click();
    await expect
      .poll(
        async () =>
          (await api<{ status: string }>(talent, "GET", `/api/v1/bookings/${bookingId}/`)).status,
      )
      .toBe("confirmed");
  });

  await test.step("host checks the talent in with the pass code", async () => {
    await page.goto("/console/arrivals");
    await page.getByRole("button", { name: "Enter code" }).click();
    await page.getByLabel("Six-digit code").fill(await passCode(talent, bookingId));
    await page.getByRole("dialog").getByRole("button", { name: "Check in" }).click();
    await expect(page.getByText(/Checked in/)).toBeVisible();
  });

  await test.step("the check-in reaches the server (Arrivals syncs it)", async () => {
    await expect
      .poll(
        async () =>
          (await api<{ status: string }>(talent, "GET", `/api/v1/bookings/${bookingId}/`)).status,
        { timeout: 60_000 },
      )
      .toMatch(/checked_in|delivering/);
  });
  await talent.close();
});
