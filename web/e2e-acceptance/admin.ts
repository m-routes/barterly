import { expect, type Page } from "@playwright/test";

import { ADMIN_PASSWORD, API_URL, type Persona } from "./env";
import { dump } from "./steps";

/** The back office is the Django admin on the API's host, with a password. */
export async function backOfficeSignIn(page: Page, admin: Persona) {
  if (!ADMIN_PASSWORD) throw new Error("Set E2E_ADMIN_PASSWORD (seed_staging used the same).");
  await page.goto(`${API_URL}/admin/login/`);
  await dump(page, "admin login");
  await page.getByLabel(/phone/i).fill(admin.phone);
  await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: /log in|sign in/i }).click();
  await expect(page).not.toHaveURL(/\/login\//);
}

/** Approve a gig from the review queue, as Ops does. */
export async function approveGig(page: Page, gigTitle: string) {
  await page.goto(`${API_URL}/admin/queues/gigs/`);
  await dump(page, "gig queue");
  await page.getByRole("link", { name: gigTitle }).first().click();
  await dump(page, "gig review");
  await page.getByRole("button", { name: "Approve" }).click();
  await dump(page, "after approve");
}
