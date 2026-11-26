import { type Browser, type BrowserContext, expect, type Page } from "@playwright/test";

import { OTP_CODE, national, type Persona } from "./env";

/** Debug helper: headings and controls on the current screen (EXPLORE=1 prints). */
export async function dump(page: Page, label: string) {
  if (!process.env.EXPLORE) return;
  await page.waitForTimeout(1500);
  const tree = await page.locator("body").ariaSnapshot();
  const keep = tree
    .split("\n")
    .filter((l) =>
      /heading|button|textbox|combobox|radio|checkbox|spinbutton|alert|status|dialog|article|link "/.test(
        l,
      ),
    )
    .filter((l) => !/option "/.test(l));
  console.log(`\n=== ${label}: ${page.url()}\n${keep.join("\n")}`);
}

/** Sign in through the real sign-in page (Firebase test number, or the local fake). */
export async function signIn(page: Page, persona: Persona, next = "") {
  await page.goto(`/login?test_numbers=1${next ? `&next=${encodeURIComponent(next)}` : ""}`);
  await page.getByLabel("Mobile number").fill(national(persona.phone));
  await page.getByRole("button", { name: "Send code" }).click();
  await page.getByRole("textbox", { name: "Code" }).fill(OTP_CODE);
  await page.getByRole("button", { name: "Verify and continue" }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/** A separate signed-in browser for another persona (the talent, say). */
export async function contextFor(browser: Browser, persona: Persona): Promise<BrowserContext> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, persona);
  await page.close();
  return context;
}

/** Map tiles are a third-party service: block them so pins are typed, deterministically. */
export async function noMapTiles(page: Page) {
  await page.route(/tile\.openstreetmap\.org|\{s\}\.tile/, (route) => route.abort());
}

/** The API through the web's own proxy, as the signed-in persona of `context`. */
export async function api<T = unknown>(
  context: BrowserContext,
  method: "GET" | "POST" | "PATCH",
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await context.request.fetch(path, {
    method,
    data: body,
    headers: { "Content-Type": "application/json" },
  });
  const text = await response.text();
  if (!response.ok()) {
    throw new Error(`${method} ${path} → ${response.status()}: ${text.slice(0, 500)}`);
  }
  return (text ? JSON.parse(text) : null) as T;
}
