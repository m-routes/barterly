import { expect, test, type Page } from "@playwright/test";

/** Privacy pages and settings against a faked API (no backend). */

const VERSION = "2026-11-draft-1";

const vendor = {
  id: "8b0c1d2e-0000-4000-8000-000000000001",
  phone: "+919876543210",
  email: null,
  role: "vendor",
  is_active: true,
  profile_complete: true,
  needs_consent: false,
  created_at: "2026-11-01T10:00:00Z",
};

const consent = (purpose: string, label: string, granted: boolean, required = false) => ({
  purpose,
  label,
  required,
  granted,
  version: granted ? VERSION : "",
  current_version: VERSION,
  needs_renewal: false,
  recorded_at: granted ? "2026-11-20T10:00:00Z" : null,
});

async function signIn(page: Page, user: object = vendor) {
  await page
    .context()
    .addCookies([{ name: "barterly_refresh", value: "e2e", domain: "localhost", path: "/" }]);
  await page.route("**/api/v1/me/", (route) => route.fulfill({ json: user }));
}

for (const [slug, title] of [
  ["terms", "Terms of service"],
  ["privacy", "Privacy policy"],
  ["community-rules", "Community rules"],
  ["refunds", "Refund and cancellation policy"],
] as const) {
  test(`the ${slug} page is public and marked as a draft`, async ({ page }) => {
    await page.goto(`/legal/${slug}`);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
    await expect(page.getByRole("note")).toContainText("Draft for lawyer review");
  });
}

test("the grievance officer is one click from the landing page", async ({ page }) => {
  await page.route("**/api/v1/privacy/grievance-officer/", (route) =>
    route.fulfill({
      json: {
        name: "A. Officer",
        email: "grievance@barterly.in",
        phone: "",
        address: "Bengaluru",
        hours: "Mon–Fri",
        acknowledge_hours: 24,
        resolve_days: 15,
      },
    }),
  );
  await page.goto("/");
  await page
    .getByRole("navigation", { name: "Legal" })
    .getByRole("link", { name: "Grievance Officer" })
    .click();
  await expect(page).toHaveURL(/\/grievance$/);
  await expect(page.getByText("A. Officer")).toBeVisible();
  await expect(page.getByRole("link", { name: "grievance@barterly.in" })).toBeVisible();
});

test("a vendor withdraws location consent from the console", async ({ page }) => {
  await signIn(page);
  let consents = [
    consent("terms", "Terms of service", true, true),
    consent("privacy", "Privacy policy", true, true),
    consent("location", "Location use", true),
    consent("social", "Social account access", false),
    consent("marketing", "Marketing messages", false),
  ];
  const posted: unknown[] = [];
  await page.route("**/api/v1/privacy/consents/", async (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      posted.push(body);
      consents = consents.map((c) =>
        c.purpose === body.purpose ? { ...c, granted: body.granted } : c,
      );
    }
    await route.fulfill({ json: consents });
  });
  await page.route("**/api/v1/privacy/exports/", (route) =>
    route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } }),
  );
  await page.route("**/api/v1/privacy/deletion/", (route) =>
    route.fulfill({ json: { request: null, blockers: [], grace_days: 7 } }),
  );

  await page.goto("/console/privacy");
  await expect(
    page.getByRole("heading", { level: 1, name: "Privacy and your data" }),
  ).toBeVisible();
  const location = page.getByRole("listitem").filter({ hasText: "Location use" });
  await location.getByRole("button", { name: "Withdraw" }).click();
  await expect(location.getByRole("button", { name: "Allow" })).toBeVisible();
  expect(posted).toEqual([{ purpose: "location", granted: false, source: "web" }]);
});

test("a user whose terms changed is asked again before the console", async ({ page }) => {
  let user = { ...vendor, needs_consent: true };
  await page
    .context()
    .addCookies([{ name: "barterly_refresh", value: "e2e", domain: "localhost", path: "/" }]);
  await page.route("**/api/v1/me/", (route) => route.fulfill({ json: user }));
  await page.route("**/api/v1/privacy/consents/", (route) => {
    user = { ...vendor, needs_consent: false };
    return route.fulfill({ json: [] });
  });
  await page.goto("/console/gigs");
  await expect(page).toHaveURL(/\/onboarding\/consent$/);
  await page.getByRole("checkbox", { name: /terms of service/ }).check();
  await page.getByRole("checkbox", { name: /privacy policy/ }).check();
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/console$/);
});
