import { expect, test, type Page } from "@playwright/test";

const vendor = {
  id: "8b0c1d2e-0000-4000-8000-000000000001",
  phone: "+919876543210",
  email: null,
  role: "vendor",
  is_active: true,
  profile_complete: true,
  created_at: "2026-11-01T10:00:00Z",
};

/** Look signed in to proxy.ts, and answer /api/v1/me/ in the browser. No backend needed. */
async function signInAs(page: Page, user: object) {
  await page
    .context()
    .addCookies([{ name: "barterly_refresh", value: "e2e", domain: "localhost", path: "/" }]);
  await page.route("**/api/v1/me/", (route) => route.fulfill({ json: user }));
}

test("signed-out visitors are sent to sign in, with a way back", async ({ page }) => {
  await page.goto("/console/gigs");
  await expect(page).toHaveURL(/\/login\?next=%2Fconsole%2Fgigs$/);
});

test("sign-in explains when Firebase isn't configured", async ({ page }) => {
  // CI runs without FIREBASE_* variables.
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign-in isn't available" })).toBeVisible();
});

test("a vendor gets the console, and every section has an empty state", async ({ page }) => {
  await signInAs(page, vendor);
  await page.goto("/console");
  const nav = page.getByRole("navigation", { name: "Console" });
  await expect(nav.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await nav.getByRole("link", { name: "Agreements" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Agreements" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "No agreements yet" })).toBeVisible();
});

test("a vendor without a profile is sent to set one up", async ({ page }) => {
  await signInAs(page, { ...vendor, profile_complete: false });
  await page.route("**/api/v1/profiles/vendor/me/", (route) =>
    route.fulfill({
      status: 404,
      json: { code: "profile_not_found", message: "No profile yet.", details: {} },
    }),
  );
  await page.goto("/console");
  await expect(page).toHaveURL(/\/onboarding\/vendor$/);
  await expect(page.getByLabel("Business name")).toBeVisible();
});

test("a new user picks a role first", async ({ page }) => {
  await signInAs(page, { ...vendor, role: "", profile_complete: false });
  await page.goto("/start");
  await expect(page).toHaveURL(/\/onboarding\/role$/);
  await expect(page.getByRole("radio", { name: /I run a place/ })).toBeVisible();
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("the console menu opens, and controls are at least 44px", async ({ page }) => {
    await signInAs(page, vendor);
    await page.goto("/console");
    await page.getByRole("button", { name: "Open menu" }).click();
    const menu = page.getByRole("button", { name: "Close menu" });
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    const links = page.getByRole("navigation", { name: "Console" }).getByRole("link");
    await expect(links).toHaveCount(9);
    for (const box of await Promise.all((await links.all()).map((l) => l.boundingBox()))) {
      expect(box!.height).toBeGreaterThanOrEqual(44);
    }
    expect((await menu.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    // No sideways scrolling on a phone.
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      375,
    );
  });
});
