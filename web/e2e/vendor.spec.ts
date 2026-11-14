import { expect, test, type Page } from "@playwright/test";

/**
 * Vendor flows against a faked API (no backend): page.route answers /api/v1/*.
 * Map tiles are faked too, so CI never loads openstreetmap.org.
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

const property = {
  id: "11111111-0000-4000-8000-000000000001",
  name: "Sea Salt Homestay",
  property_type: "homestay",
  address: "12 Beach Road",
  city: "Palolem",
  state: "Goa",
  pincode: "403702",
  latitude: "15.009900",
  longitude: "74.023200",
  location_confirmed: true,
  amenities: [],
  house_rules: [],
  women_friendly: false,
  verification_status: "not_started",
  photos: [],
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T10:00:00Z",
};

// A 1×1 transparent PNG.
const TILE = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
  "base64",
);

async function signIn(page: Page) {
  await page
    .context()
    .addCookies([{ name: "barterly_refresh", value: "e2e", domain: "localhost", path: "/" }]);
  await page.route("**/api/v1/me/", (route) => route.fulfill({ json: vendor }));
}

test("the property map loads lazily, credits OpenStreetMap and moves the pin", async ({ page }) => {
  await signIn(page);
  await page.route("https://tile.openstreetmap.org/**", (route) =>
    route.fulfill({ body: TILE, contentType: "image/png" }),
  );
  await page.route("**/api/v1/geo/geocode/", (route) =>
    route.fulfill({
      json: {
        found: true,
        latitude: 15.0099,
        longitude: 74.0232,
        display_name: "Palolem Beach, Goa",
        city: "Canacona",
        state: "Goa",
        postcode: "403702",
      },
    }),
  );
  await page.goto("/console/properties/new");

  // The map's code only loads once it scrolls into view.
  await page.getByText("Exact location").scrollIntoViewIfNeeded();
  const map = page.getByRole("region", { name: /^Map\./ });
  await expect(map).toBeVisible();
  await expect(page.getByRole("link", { name: "OpenStreetMap" })).toHaveAttribute(
    "href",
    "https://www.openstreetmap.org/copyright",
  );

  await page.getByLabel("Search for the place").fill("Palolem beach");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("15.009900, 74.023200", { exact: true })).toBeVisible();
  await expect(page.getByLabel("City or town")).toHaveValue("Canacona");

  // Tapping the map moves the pin, and the pin then needs confirming again.
  await page.getByLabel("The pin is on the property's entrance").check();
  const box = (await map.boundingBox())!;
  await page.mouse.click(box.x + box.width / 2 + 40, box.y + box.height / 2 + 40);
  await expect(page.getByText("15.009900, 74.023200", { exact: true })).toBeHidden();
  await expect(page.getByLabel("The pin is on the property's entrance")).not.toBeChecked();
});

test("when map tiles can't load, coordinates can be typed instead", async ({ page }) => {
  await signIn(page);
  await page.route("https://tile.openstreetmap.org/**", (route) => route.abort());
  await page.goto("/console/properties/new");
  await page.getByText("Exact location").scrollIntoViewIfNeeded();

  await expect(page.getByText(/The map couldn't load/)).toBeVisible({ timeout: 15_000 });
  await page.getByLabel("Latitude").fill("15.5527");
  await page.getByLabel("Longitude").fill("73.7517");
  await page.getByRole("button", { name: "Use these coordinates" }).click();
  await expect(page.getByText("15.552700, 73.751700", { exact: true })).toBeVisible();
});

test("the gig builder previews as you type and saves the draft by itself", async ({ page }) => {
  await signIn(page);
  await page.route("**/api/v1/properties/?**", (route) =>
    route.fulfill({ json: { count: 1, next: null, previous: null, results: [property] } }),
  );
  await page.route("**/api/v1/profiles/skills/", (route) => route.fulfill({ json: [] }));
  const created: unknown[] = [];
  await page.route("**/api/v1/gigs/", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    created.push(body);
    await route.fulfill({
      status: 201,
      json: {
        ...body,
        id: "22222222-0000-4000-8000-000000000001",
        status: "draft",
        status_reason: "",
        min_age: 18,
        submitted_at: null,
        published_at: null,
        closed_at: null,
        created_at: "2026-11-14T10:00:00Z",
        updated_at: "2026-11-14T10:00:00Z",
      },
    });
  });
  await page.route("**/api/v1/gigs/22222222-0000-4000-8000-000000000001/", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        ...(created[0] as object),
        ...body,
        id: "22222222-0000-4000-8000-000000000001",
        status: "draft",
      },
    });
  });
  await page.goto("/console/gigs/new");

  await page.getByLabel(/Volunteer/).check();
  await page.getByLabel("Gig title").fill("Reception and social media volunteer");
  await page.getByLabel(/Hours per day/).fill("8");
  await expect(page.getByText("At most 6 hours a day.")).toBeVisible();
  await page.getByLabel(/Hours per day/).fill("4");
  await page.getByLabel(/Days per week/).fill("5");

  const preview = page.getByRole("article", { name: "Preview of your gig" });
  await expect(preview).toContainText("Reception and social media volunteer");
  await expect(preview).toContainText("Sea Salt Homestay · Palolem");
  await expect(preview).toContainText("4 hrs/day · 5 days/week");

  await page.getByRole("button", { name: "Next" }).click();
  await page.getByLabel(/Work for stay/).check();
  await page.getByLabel("Stay", { exact: true }).selectOption("dorm_bed");
  await page.getByLabel("Meals", { exact: true }).selectOption("all_meals");
  await expect(preview).toContainText("dorm bed + all meals");

  await expect(page.getByText(/Draft saved at/)).toBeVisible();
  await expect(page).toHaveURL(/\/console\/gigs\/22222222-0000-4000-8000-000000000001\/edit$/);
  expect(created[0]).toMatchObject({
    property: property.id,
    title: "Reception and social media volunteer",
    role_template: "volunteer",
    compensation_model: "volunteer",
    hours_per_day: 4,
  });
});
