/** Small helpers for faking fetch in tests. */

export function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

export function errorBody(code: string, message = code, details: Record<string, unknown> = {}) {
  return { code, message, details };
}

/** A JWT-shaped string with the given exp (seconds since epoch); unsigned. */
export function fakeJwt(exp: number): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ exp, user_id: "u1" })}.sig`;
}

export const vendorUser = {
  id: "8b0c1d2e-0000-4000-8000-000000000001",
  phone: "+919876543210",
  email: null,
  role: "vendor" as const,
  is_active: true,
  profile_complete: true,
  created_at: "2026-11-01T10:00:00Z",
};
