import { vi } from "vitest";

/**
 * A stand-in for next/navigation. Use with:
 *   vi.mock("next/navigation", () => navigationMock);
 * and set `nav.pathname` / `nav.search` per test; `nav.router` records calls.
 */
export const nav = {
  pathname: "/",
  search: "",
  router: { replace: vi.fn(), push: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() },
  reset() {
    this.pathname = "/";
    this.search = "";
    for (const fn of Object.values(this.router)) fn.mockReset();
  },
};

export const navigationMock = {
  useRouter: () => nav.router,
  usePathname: () => nav.pathname,
  useSearchParams: () => new URLSearchParams(nav.search),
};
