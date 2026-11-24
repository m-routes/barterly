import { createHmac } from "node:crypto";

import { type BrowserContext, expect, type Page } from "@playwright/test";

import { API_URL, OTP_CODE, type Persona } from "./env";
import { api } from "./steps";

/**
 * The talent's side of the journeys, through the API as the talent (the talent's UI is
 * the Flutter app, covered by mobile/integration_test). Calls go through the web's
 * proxy with the talent's own session, exactly as the app's calls reach the API.
 */

type Page_<T> = { results: T[] };

export async function apply(talent: BrowserContext, gigId: string, start: string, end: string) {
  return api<{ id: string }>(talent, "POST", `/api/v1/gigs/${gigId}/applications/`, {
    pitch: "Two seasons making reels for homestays in Kerala; happy to help in the garden too.",
    answers: [],
    proposed_start: start,
    proposed_end: end,
    attachments: [],
  });
}

/** Wait for the host's offer to reach the talent, then accept it. */
export async function acceptOffer(talent: BrowserContext, applicationId: string) {
  let offerId = "";
  await expect
    .poll(
      async () => {
        const thread = await api<{ open_offer: string | null; your_turn: boolean }>(
          talent,
          "GET",
          `/api/v1/applications/${applicationId}/offers/`,
        );
        offerId = thread.your_turn && thread.open_offer ? thread.open_offer : "";
        return offerId;
      },
      { message: "the host's offer reaches the talent" },
    )
    .not.toBe("");
  return api<{ booking: string; agreement_version: string }>(
    talent,
    "POST",
    `/api/v1/offers/${offerId}/accept/`,
    {},
  );
}

/**
 * A fresh phone confirmation for signing. The local stack's fake verifier takes
 * `fake-otp:` tokens; on staging the talent's browser runs Firebase's own SDK (from
 * gstatic, which the CSP allows) with the persona's test number.
 */
export async function freshOtpToken(page: Page, persona: Persona): Promise<string> {
  if (/localhost|127\.0\.0\.1/.test(API_URL)) {
    return `fake-otp:${persona.phone}@${Math.floor(Date.now() / 1000)}`;
  }
  // The public Firebase web config (not secret; the same values the login page uses).
  const config = {
    apiKey: process.env.E2E_FIREBASE_API_KEY,
    authDomain: process.env.E2E_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.E2E_FIREBASE_PROJECT_ID,
    appId: process.env.E2E_FIREBASE_APP_ID,
  };
  if (!config.apiKey || !config.projectId) {
    throw new Error("Set E2E_FIREBASE_API_KEY, _AUTH_DOMAIN, _PROJECT_ID and _APP_ID for staging.");
  }
  return page.evaluate(
    async ({ config, phone, code }) => {
      const base = "https://www.gstatic.com/firebasejs/11.10.0";
      const { initializeApp } = await import(/* @vite-ignore */ `${base}/firebase-app.js`);
      const auth = await import(/* @vite-ignore */ `${base}/firebase-auth.js`);
      const app = initializeApp(config, "acceptance-signing");
      const instance = auth.getAuth(app);
      instance.settings.appVerificationDisabledForTesting = true;
      const host = document.createElement("div");
      document.body.append(host);
      const verifier = new auth.RecaptchaVerifier(instance, host, { size: "invisible" });
      const confirmation = await auth.signInWithPhoneNumber(instance, phone, verifier);
      const credential = await confirmation.confirm(code);
      return credential.user.getIdToken();
    },
    { config, phone: persona.phone, code: OTP_CODE },
  );
}

export async function sign(
  talent: BrowserContext,
  page: Page,
  persona: Persona,
  bookingId: string,
) {
  const agreement = await api<{ versions: { id: string; status: string; pdf_sha256: string }[] }>(
    talent,
    "GET",
    `/api/v1/bookings/${bookingId}/agreement/`,
  );
  const version = agreement.versions.find((v) => v.status === "awaiting") ?? agreement.versions[0];
  if (!version) throw new Error("No agreement version to sign");
  return api(talent, "POST", `/api/v1/agreement-versions/${version.id}/sign/`, {
    consent: true,
    document_sha256: version.pdf_sha256,
    otp_token: await freshOtpToken(page, persona),
  });
}

/** The six-digit code the talent's pass shows right now (TOTP, as the app computes it). */
export async function passCode(talent: BrowserContext, bookingId: string): Promise<string> {
  const pass = await api<{ code_secret: string; code_period_seconds: number; code_digits: number }>(
    talent,
    "POST",
    `/api/v1/bookings/${bookingId}/attendance/pass/`,
    {},
  );
  return totp(pass.code_secret, pass.code_period_seconds, pass.code_digits);
}

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secret.replace(/=+$/, "").toUpperCase()) {
    bits += alphabet.indexOf(ch).toString(2).padStart(5, "0");
  }
  const bytes = bits.match(/.{8}/g) ?? [];
  return Buffer.from(bytes.map((b) => parseInt(b, 2)));
}

function totp(secret: string, period: number, digits: number): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 1000 / period)));
  const digest = createHmac("sha1", base32(secret)).update(counter).digest();
  const offset = digest[digest.length - 1]! & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 10 ** digits).padStart(digits, "0");
}

export async function handIn(talent: BrowserContext, bookingId: string) {
  const items = await api<{ id: string }[] | Page_<{ id: string }>>(
    talent,
    "GET",
    `/api/v1/bookings/${bookingId}/deliverables/items/`,
  );
  const list = Array.isArray(items) ? items : items.results;
  for (const item of list) {
    await api(talent, "POST", `/api/v1/deliverables/items/${item.id}/submit/`, {
      post_url: "https://www.instagram.com/reel/acceptance-test/",
      file_ids: [],
      note: "Posted with the paid-partnership label and the homestay tagged.",
      disclosure_confirmed: true,
    });
  }
  return list.length;
}
