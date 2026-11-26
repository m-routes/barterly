import { defineConfig, devices } from "@playwright/test";

/**
 * The acceptance suite: real journeys against a running stack (docs/qa/README.md).
 *
 * - Nightly and on release candidates against staging: ACCEPTANCE_WEB_URL and
 *   ACCEPTANCE_API_URL point at it, personas sign in with Firebase test numbers
 *   (E2E_OTP_CODE).
 * - Locally or in CI against the local acceptance stack: the same journeys, with the
 *   API's local fake sign-in (code 123456) and stand-in payments.
 *
 * Every journey runs on a desktop browser and at 390 px (a phone).
 */
export default defineConfig({
  testDir: "./e2e-acceptance",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1, // journeys share personas: run them in order
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never", outputFolder: "acceptance-report" }]]
    : "list",
  use: {
    baseURL: process.env.ACCEPTANCE_WEB_URL ?? "http://localhost:3011",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "phone-390",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true },
    },
  ],
});
