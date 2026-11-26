// @vitest-environment node
import { describe, expect, it } from "vitest";

import { contentSecurityPolicy, staticSecurityHeaders } from "./headers";

function directive(csp: string, name: string): string[] {
  const found = csp.split("; ").find((d) => d.startsWith(`${name} `) || d === name);
  return found ? found.split(" ").slice(1) : [];
}

describe("contentSecurityPolicy", () => {
  const csp = contentSecurityPolicy();

  it("only runs scripts from our origin and Google sign-in (no inline, no eval)", () => {
    const scripts = directive(csp, "script-src");
    expect(scripts[0]).toBe("'self'");
    expect(scripts).not.toContain("'unsafe-inline'");
    expect(scripts).not.toContain("'unsafe-eval'");
    expect(scripts.every((s) => s === "'self'" || s.startsWith("https://"))).toBe(true);
  });

  it("can't be framed, has no plugins and keeps forms and base on our origin", () => {
    expect(directive(csp, "frame-ancestors")).toEqual(["'none'"]);
    expect(directive(csp, "object-src")).toEqual(["'none'"]);
    expect(directive(csp, "form-action")).toEqual(["'self'"]);
    expect(directive(csp, "base-uri")).toEqual(["'self'"]);
    expect(csp).toContain("upgrade-insecure-requests");
  });

  it("allows the dev server's eval only in development", () => {
    expect(directive(contentSecurityPolicy({ dev: true }), "script-src")).toContain(
      "'unsafe-eval'",
    );
  });

  it("allows inline scripts only when asked", () => {
    expect(directive(contentSecurityPolicy({ inlineScripts: true }), "script-src")).toContain(
      "'unsafe-inline'",
    );
  });

  it("allows images and video from the media CDN origins, https only", () => {
    const csp = contentSecurityPolicy({
      mediaOrigins: [
        "https://media.barterly.in",
        " https://media.staging.barterly.in ",
        "http://x.test",
        "nonsense",
      ],
    });
    expect(directive(csp, "img-src")).toContain("https://media.barterly.in");
    expect(directive(csp, "img-src")).toContain("https://media.staging.barterly.in");
    expect(directive(csp, "media-src")).toContain("https://media.barterly.in");
    expect(csp).not.toContain("http://x.test");
    expect(csp).not.toContain("nonsense");
  });

  it("allows images from the configured tile host", () => {
    const custom = contentSecurityPolicy({ tileUrl: "https://tiles.example.com/{z}/{x}/{y}.png" });
    expect(directive(custom, "img-src")).toContain("https://tiles.example.com");
  });
});

describe("staticSecurityHeaders", () => {
  const map = (production: boolean) =>
    Object.fromEntries(staticSecurityHeaders(production).map((h) => [h.key, h.value]));

  it("sends HSTS in production only", () => {
    expect(map(true)["Strict-Transport-Security"]).toMatch(/max-age=31536000/);
    expect(map(false)["Strict-Transport-Security"]).toBeUndefined();
  });

  it("forbids framing and sniffing and sends the CSP", () => {
    expect(map(true)["X-Frame-Options"]).toBe("DENY");
    expect(map(true)["X-Content-Type-Options"]).toBe("nosniff");
    expect(map(true)["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
  });
});
