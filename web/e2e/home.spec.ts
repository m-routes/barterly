import { expect, test } from "@playwright/test";

test("landing page leads to sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Find talent for your stay, café or tour",
  );
  await page.getByRole("link", { name: "Get started" }).click();
  await expect(page).toHaveURL(/\/login$/);
});
