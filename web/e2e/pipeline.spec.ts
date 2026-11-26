import { expect, test, type Page } from "@playwright/test";

/**
 * The applicant pipeline in a real browser, against a faked API: native drag and drop,
 * keyboard moves, and putting a card back when the server refuses.
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
const GIG = "22222222-0000-4000-8000-000000000001";

function person(id: string, name: string, status: string, fit: number, badges = ["id_verified"]) {
  return {
    id,
    gig: GIG,
    gig_title: "Reception and social media volunteer",
    status,
    status_reason: "",
    proposed_start: "2026-12-12",
    proposed_end: "2027-01-05",
    applicant: {
      user_id: `u-${id}`,
      display_name: name,
      talent_type: "Volunteer traveller",
      home_city: "Pune",
      bio: "",
      languages: ["en"],
      skills: [],
      instagram_followers: null,
      badges,
      reliability: { score: 50, level: "new", version: "v1" },
    },
    fit: { score: fit, breakdown: {} },
    attachment_count: 0,
    conversation: null,
    unread_messages: 0,
    agreement: null,
    applied_at: "2026-11-10T10:00:00Z",
    rejection_code: "",
    tags: [],
    note_count: 0,
  };
}

async function open(page: Page, refuse = false) {
  const posted: string[] = [];
  await page
    .context()
    .addCookies([{ name: "barterly_refresh", value: "e2e", domain: "localhost", path: "/" }]);
  await page.route("**/api/v1/me/", (route) => route.fulfill({ json: vendor }));
  await page.route("**/api/v1/notifications/unread-count/", (route) =>
    route.fulfill({ json: { unread: 2 } }),
  );
  await page.route(`**/api/v1/gigs/${GIG}/`, (route) =>
    route.fulfill({
      json: { id: GIG, title: "Reception and social media volunteer", status: "live", slots: 2 },
    }),
  );
  await page.route(`**/api/v1/gigs/${GIG}/applications/?**`, (route) =>
    route.fulfill({
      json: {
        count: 5,
        next: null,
        previous: null,
        results: [
          person("a1", "Aarav Mehta", "applied", 92),
          person("a2", "Meera Sood", "applied", 88, []),
          person("a3", "Tanya Dogra", "shortlisted", 90),
          person("a4", "Nisha Patil", "interview", 91),
          person("a5", "Ishita Verma", "offered", 93),
        ],
      },
    }),
  );
  await page.route("**/api/v1/applicant-filters/", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/applications/*/status/", async (route) => {
    posted.push(`${new URL(route.request().url()).pathname} ${route.request().postData()}`);
    if (refuse) {
      await route.fulfill({
        status: 409,
        json: { code: "transition_refused", message: "The gig is paused.", details: {} },
      });
    } else {
      await route.fulfill({ json: {} });
    }
  });
  await page.goto(`/console/gigs/${GIG}/applicants`);
  await expect(page.getByRole("article", { name: "Aarav Mehta" })).toBeVisible();
  return posted;
}

const column = (page: Page, name: string) =>
  page.locator("section.board__column").filter({ has: page.getByRole("heading", { name }) });

test("drags a card to the next column", async ({ page }) => {
  const posted = await open(page);
  await page.getByRole("article", { name: "Aarav Mehta" }).dragTo(column(page, "Shortlisted"));
  await expect(
    column(page, "Shortlisted").getByRole("article", { name: "Aarav Mehta" }),
  ).toBeVisible();
  await expect
    .poll(() => posted)
    .toEqual(['/api/v1/applications/a1/status/ {"status":"shortlisted"}']);
  if (process.env.PIPELINE_SCREENSHOT) {
    await page.screenshot({ path: process.env.PIPELINE_SCREENSHOT, fullPage: true });
  }
});

test("moves a card with the keyboard alone", async ({ page }) => {
  const posted = await open(page);
  await page.getByRole("button", { name: "Move Meera Sood with the keyboard" }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("status")).toContainText("Picked up Meera Sood");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  await expect(
    column(page, "Interview").getByRole("article", { name: "Meera Sood" }),
  ).toBeVisible();
  await expect
    .poll(() => posted)
    .toEqual(['/api/v1/applications/a2/status/ {"status":"interview"}']);
});

test("puts a card back when the server refuses", async ({ page }) => {
  await open(page, true);
  await page.getByRole("button", { name: "Shortlist Aarav Mehta" }).click();
  await expect(page.locator(".toast")).toContainText("The gig is paused.");
  await expect(column(page, "Applied").getByRole("article", { name: "Aarav Mehta" })).toBeVisible();
});
