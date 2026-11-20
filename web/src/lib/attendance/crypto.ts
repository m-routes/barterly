import { ed25519 } from "@noble/curves/ed25519.js";
import { hmac } from "@noble/hashes/hmac.js";
import { sha1 } from "@noble/hashes/legacy.js";

/**
 * Checking a talent's check-in pass without a connection (apps/attendance/signing.py):
 * - the QR holds `BRT1.<payload>.<signature>`, signed with Ed25519 by the server; the
 *   console verifies it with the public keys it cached;
 * - the fallback six-digit code is TOTP (HMAC-SHA1, 5-minute step, the previous step
 *   accepted too) of the pass's code secret, which the cached arrivals list carries.
 * The server checks both again when the queued check-in syncs.
 */

export type PublicKey = { kid: string; alg: string; public_key: string };

export type PassPayload = {
  v: 1;
  kid: string;
  /** booking id */
  b: string;
  /** talent id */
  t: string;
  /** pass id */
  p: string;
  /** not before (Unix seconds) */
  nbf: number;
  /** expires (Unix seconds) */
  exp: number;
};

export type Verified =
  | { ok: true; payload: PassPayload }
  | { ok: false; reason: "not-a-pass" | "unknown-key" | "bad-signature" | "expired" | "not-yet" };

export function fromBase64Url(text: string): Uint8Array {
  const base64 = text.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
}

function parse(
  token: string,
): { body: string; payload: PassPayload; signature: Uint8Array } | null {
  const [prefix, body, signature] = token.trim().split(".");
  if (prefix !== "BRT1" || !body || !signature || token.trim().split(".").length !== 3) return null;
  try {
    const payload = JSON.parse(new TextDecoder().decode(fromBase64Url(body))) as PassPayload;
    if (payload?.v !== 1 || typeof payload.b !== "string") return null;
    return { body: `${prefix}.${body}`, payload, signature: fromBase64Url(signature) };
  } catch {
    return null;
  }
}

/** Is this a genuine pass, valid at `now` (allowing `skewSeconds` of clock drift)? */
export function verifyPass(
  token: string,
  keys: readonly PublicKey[],
  now: Date,
  skewSeconds = 120,
): Verified {
  const parsed = parse(token);
  if (!parsed) return { ok: false, reason: "not-a-pass" };
  const key = keys.find((k) => k.kid === parsed.payload.kid && k.alg === "Ed25519");
  if (!key) return { ok: false, reason: "unknown-key" };
  let genuine = false;
  try {
    genuine = ed25519.verify(
      parsed.signature,
      new TextEncoder().encode(parsed.body),
      fromBase64Url(key.public_key),
      { zip215: false }, // strict RFC 8032, as the server verifies
    );
  } catch {
    genuine = false;
  }
  if (!genuine) return { ok: false, reason: "bad-signature" };
  const seconds = now.getTime() / 1000;
  if (seconds < parsed.payload.nbf - skewSeconds) return { ok: false, reason: "not-yet" };
  if (seconds > parsed.payload.exp + skewSeconds) return { ok: false, reason: "expired" };
  return { ok: true, payload: parsed.payload };
}

const BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

export function fromBase32(text: string): Uint8Array {
  const clean = text.replace(/=+$/, "").toUpperCase();
  const out: number[] = [];
  let bits = 0;
  let value = 0;
  for (const ch of clean) {
    const index = BASE32.indexOf(ch);
    if (index < 0) throw new Error("Not base32");
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Uint8Array.from(out);
}

/** The six-digit code for `secret` at `at` (RFC 6238, HMAC-SHA1). */
export function codeAt(secret: string, at: Date, periodSeconds = 300, stepOffset = 0): string {
  const counter = Math.floor(at.getTime() / 1000 / periodSeconds) + stepOffset;
  const message = new Uint8Array(8);
  let rest = counter;
  for (let i = 7; i >= 0; i--) {
    message[i] = rest & 0xff;
    rest = Math.floor(rest / 256);
  }
  const digest = hmac(sha1, fromBase32(secret), message);
  const byte = (i: number) => digest[i] ?? 0;
  const offset = byte(digest.length - 1) & 0x0f;
  const number =
    ((byte(offset) & 0x7f) << 24) |
    (byte(offset + 1) << 16) |
    (byte(offset + 2) << 8) |
    byte(offset + 3);
  return String(number % 1_000_000).padStart(6, "0");
}

export function codeMatches(secret: string, code: string, at: Date, periodSeconds = 300): boolean {
  const digits = code.replace(/\D/g, "");
  return [0, -1].some((offset) => codeAt(secret, at, periodSeconds, offset) === digits);
}
