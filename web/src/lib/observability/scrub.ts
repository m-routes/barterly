/**
 * Redaction for error reports, matching the API's (backend apps/common/redaction.py):
 * phone numbers, emails and UPI ids, PAN, Aadhaar, account numbers and tokens are
 * masked in every string, and values under sensitive keys are dropped.
 */

const MASK = "[redacted]";

/**
 * Sentry 11 collects user info, cookies, headers, query strings and bodies by default.
 * We collect none of them; scrubEvent below is the second layer.
 */
export const DATA_COLLECTION = {
  userInfo: false,
  cookies: false,
  httpHeaders: false,
  httpBodies: [],
  urlQueryParams: false,
  graphQL: { document: false, variables: false },
  genAI: { inputs: false, outputs: false },
} as const;

const SENSITIVE_KEY =
  /pass(word)?|secret|token|authori[sz]ation|cookie|session|otp|phone|mobile|e_?mail|aadhaa?r|pan_number|account_number|ifsc|upi|vpa|emergency|address|pincode|latitude|longitude|date_of_birth|dob/i;

const PATTERNS: RegExp[] = [
  /\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*/g,
  /\bbearer\s+[\w.~+/=-]{8,}/gi,
  /[\w.%+-]+@[\w-]+[\w.-]*/g,
  /\b[A-Z]{5}\d{4}[A-Z]\b/g,
  // Indian mobiles with a +91/91 prefix, then bare or 0-prefixed ones.
  /(?<![\d.])\+?91[\s-]?[6-9]\d{4}[\s-]?\d{5}(?!\d)/g,
  /(?<![\d.])0?[6-9]\d{4}[\s-]?\d{5}(?!\d)/g,
  /(?<![\d.])\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)/g,
  /(?<![\d.-])\d{9,18}(?![\d.])/g,
];

export function scrubText(text: string): string {
  return PATTERNS.reduce((out, pattern) => out.replace(pattern, MASK), text);
}

export function scrub<T>(value: T, depth = 0): T {
  if (depth > 12) return MASK as T;
  if (typeof value === "string") return scrubText(value) as T;
  if (Array.isArray(value)) return value.map((v) => scrub(v, depth + 1)) as T;
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, v] of Object.entries(value)) {
      out[key] = SENSITIVE_KEY.test(key) && v !== "" && v != null ? MASK : scrub(v, depth + 1);
    }
    return out as T;
  }
  return value;
}

/** Sentry beforeSend: keep the opaque user id only, drop bodies and cookies, mask PII. */
export function scrubEvent<E extends object>(event: E): E {
  const { user, request, ...rest } = event as Record<string, unknown> & {
    user?: { id?: string | number };
    request?: Record<string, unknown>;
  };
  const out = scrub(rest) as Record<string, unknown>;
  if (user?.id != null) out.user = { id: user.id };
  if (request) {
    const req = { ...request };
    const hadQuery = Boolean(req.query_string);
    delete req.cookies;
    delete req.data;
    delete req.query_string;
    out.request = { ...scrub(req), ...(hadQuery ? { query_string: MASK } : {}) };
  }
  return out as E;
}
