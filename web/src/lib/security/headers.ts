/**
 * Browser-hardening headers for the web app (ASVS 14.4).
 *
 * One fixed Content-Security-Policy for every response (set in next.config). Pages are
 * prerendered (Cache Components / PPR), so a per-request nonce can't reach their
 * scripts; instead script files carry build-time SRI hashes (experimental.sri) and
 * only our own origin and Google's sign-in hosts may serve scripts.
 * See docs/security.md for why and what 'unsafe-inline' (if set) still allows.
 */

export type CspOptions = {
  /** Allow inline <script> (Next's RSC payload in prerendered pages needs it). */
  inlineScripts?: boolean;
  /** Next's dev server evaluates code for fast refresh. Never true in production. */
  dev?: boolean;
  /** The map tile template, e.g. https://tile.openstreetmap.org/{z}/{x}/{y}.png */
  tileUrl?: string;
};

const GOOGLE_AUTH = [
  "https://www.google.com",
  "https://www.gstatic.com",
  "https://apis.google.com",
];
const STORAGE = "https://storage.googleapis.com";

function originOf(template: string | undefined): string | null {
  if (!template) return null;
  try {
    return new URL(template.replace(/\{[a-z]\}/g, "a")).origin;
  } catch {
    return null;
  }
}

export function contentSecurityPolicy({
  inlineScripts = false,
  dev = false,
  tileUrl,
}: CspOptions = {}): string {
  const tiles = originOf(tileUrl) ?? "https://tile.openstreetmap.org";
  const directives: Record<string, string[]> = {
    "default-src": ["'self'"],
    "script-src": [
      "'self'",
      ...(inlineScripts ? ["'unsafe-inline'"] : []),
      ...GOOGLE_AUTH,
      ...(dev ? ["'unsafe-eval'"] : []),
    ],
    // React and the map set style attributes; styles can't run code.
    "style-src": ["'self'", "'unsafe-inline'"],
    "img-src": ["'self'", "data:", "blob:", STORAGE, tiles],
    "font-src": ["'self'"],
    // The BFF is same-origin; Firebase Auth and uploads to signed URLs are not.
    "connect-src": [
      "'self'",
      "https://identitytoolkit.googleapis.com",
      "https://securetoken.googleapis.com",
      "https://www.google.com",
      STORAGE,
      ...(dev ? ["ws:"] : []),
    ],
    // reCAPTCHA and Firebase's auth helper, and agreement PDFs from signed URLs.
    "frame-src": ["https://www.google.com", "https://*.firebaseapp.com", STORAGE],
    "worker-src": ["'self'", "blob:"],
    "manifest-src": ["'self'"],
    "object-src": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "frame-ancestors": ["'none'"],
  };
  const parts = Object.entries(directives).map(([name, values]) => `${name} ${values.join(" ")}`);
  if (!dev) parts.push("upgrade-insecure-requests");
  return parts.join("; ");
}

/** Headers for every response, set in next.config (static assets included). */
export function staticSecurityHeaders(
  production: boolean,
  csp: CspOptions = {},
): { key: string; value: string }[] {
  const headers = [
    { key: "Content-Security-Policy", value: contentSecurityPolicy({ ...csp, dev: !production }) },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Cross-Origin-Opener-Policy", value: "same-origin-allow-popups" },
    {
      key: "Permissions-Policy",
      // Camera (check-in QR) and location (check-in) only for our own pages.
      value: "camera=(self), geolocation=(self), microphone=(), payment=(), usb=()",
    },
  ];
  if (production) {
    headers.push({
      key: "Strict-Transport-Security",
      value: "max-age=31536000; includeSubDomains; preload",
    });
  }
  return headers;
}
