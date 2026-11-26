import { expect, type Page } from "@playwright/test";

import type { Persona } from "./env";
import { dump, noMapTiles } from "./steps";

/** A brand-new vendor: pick the role, set up the business profile. */
export async function onboard(page: Page, p: Persona) {
  await page.getByRole("radio", { name: /I run a place/ }).check();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByLabel("Business name").fill(p.business_name!);
  await page.getByLabel("Business type").selectOption({ label: "Homestay" });
  await page
    .getByLabel("About your place")
    .fill("A six-room homestay in the tea hills, with a garden kitchen.");
  await page.getByLabel("Contact name").fill(p.name);
  await page.getByLabel("City or town").fill(p.city!);
  await page.getByLabel("State or union territory").selectOption({ label: p.state! });
  await page.getByRole("button", { name: "Create profile" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Get ready to host" })).toBeVisible();
}

/** The property, pinned by typed coordinates. */
export async function addProperty(page: Page, p: Persona) {
  await noMapTiles(page);
  await page.getByRole("link", { name: /Add a property/ }).click();
  const form = page.locator("form").filter({ has: page.getByLabel("Property name") });
  await form.getByLabel("Property name").fill(p.business_name!);
  await form.getByLabel("Kind of property").selectOption({ label: "Homestay" });
  await form.getByRole("checkbox", { name: "Wi-Fi" }).check();
  await form.getByLabel("Street address").fill("Tea Estate Road, near the post office");
  await form.getByLabel("City or town").fill(p.city!);
  await form.getByLabel("State or union territory").selectOption({ label: p.state! });
  await form.getByLabel("PIN code (optional)").fill(p.pincode!);
  await form.getByText("Exact location").scrollIntoViewIfNeeded();
  const latitude = form.getByLabel("Latitude");
  if (!(await latitude.isVisible())) {
    await form.getByRole("button", { name: "Enter coordinates instead" }).click();
  }
  await latitude.fill(String(p.latitude));
  await form.getByLabel("Longitude").fill(String(p.longitude));
  await form.getByRole("button", { name: "Use these coordinates" }).click();
  await form.getByLabel("The pin is on the property's entrance").check();
  await form.getByRole("button", { name: "Add property" }).click();
  await dump(page, "after add property");
}

/** A date n days from today in India (the app's dates are Asia/Kolkata, not UTC). */
export const inDays = (n: number) =>
  new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(
    new Date(Date.now() + n * 86_400_000),
  );

export type GigPlan = { title: string; startIn: number; days: number; slots?: number };

/** Post a content-for-stay gig through the five-step builder and send it for review. */
export async function postGig(page: Page, gig: GigPlan): Promise<string> {
  await page.goto("/console/gigs/new");
  const builder = page.locator("main:visible");
  await builder.getByRole("radio", { name: /^Content creator/ }).check();
  await builder.getByLabel("Gig title").fill(gig.title);
  await builder
    .getByLabel("Description")
    .fill("Help at the front desk and with the evening garden dinners. Friendly hosts.");
  await builder.getByLabel("Property", { exact: true }).selectOption({ index: 1 });
  await builder.getByLabel("Open slots").fill(String(gig.slots ?? 1));
  await builder.getByLabel("Start date").fill(inDays(gig.startIn));
  await builder.getByLabel("Apply by").fill(inDays(Math.max(1, gig.startIn - 3)));
  await builder.getByLabel("End date").fill(inDays(gig.startIn + gig.days));
  await builder.getByLabel(/Hours per day/).fill("5");
  await builder.getByLabel(/Days per week/).fill("5");
  await builder.getByRole("checkbox", { name: "Content writing" }).check();
  await dump(page, "basics filled");
  await builder.getByRole("button", { name: "Next" }).click();
  await builder.getByRole("radio", { name: /^Content for stay/ }).check();
  await builder.getByLabel("Stay", { exact: true }).selectOption({ index: 1 });
  await builder.getByLabel("Meals", { exact: true }).selectOption({ index: 1 });
  await builder.getByRole("button", { name: "Add a deliverable" }).click();
  await builder
    .getByLabel("Deliverable 1", { exact: true })
    .selectOption({ label: "Instagram reel" });
  await builder.getByRole("button", { name: "Next" }).click();
  await builder.getByRole("checkbox", { name: "English" }).check();
  await builder.getByRole("button", { name: "Next" }).click(); // Questions: none
  await builder.getByRole("button", { name: "Next" }).click();
  await expect(builder.getByRole("heading", { name: "Review", level: 2 })).toBeVisible();
  await builder.getByRole("button", { name: "Submit for review" }).click();
  await dump(page, "submitted");
  await expect(page.getByRole("heading", { name: "Sent for review" })).toBeVisible();
  const id = page.url().match(/gigs\/([0-9a-f-]{36})/)?.[1];
  if (!id) throw new Error(`No gig id in ${page.url()}`);
  return id;
}
