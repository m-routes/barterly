import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { vendorUser } from "../../../../test/http";
import { nav } from "../../../../test/navigation";
import type { SessionState } from "@/lib/session/session";

import { ConsoleShell } from "./ConsoleShell";
import { CONSOLE_SECTIONS, activeSection } from "./nav";
import { SectionPage } from "./SectionPage";

vi.mock(
  "next/navigation",
  async () => (await import("../../../../test/navigation")).navigationMock,
);

const session = {
  state: { status: "signed-in", user: vendorUser } as SessionState,
  reload: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("@/lib/session/session", () => ({ useSession: () => session }));

beforeEach(() => {
  nav.reset();
  session.signOut.mockReset();
});

describe("ConsoleShell", () => {
  it("lists the sections in order and marks the current one", () => {
    nav.pathname = "/console/gigs";
    render(<ConsoleShell>content</ConsoleShell>);
    const sidebar = within(screen.getByRole("navigation", { name: "Console" }));
    const links = sidebar.getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual([
      "Dashboard",
      "Gigs",
      "Applicants",
      "Properties",
      "Verification",
      "Talent search",
      "Agreements",
      "Payments",
      "Analytics",
    ]);
    expect(sidebar.getByRole("link", { name: "Gigs" })).toHaveAttribute("aria-current", "page");
    expect(sidebar.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("main")).toHaveTextContent("content");
  });

  it("opens and closes the mobile menu, and Escape closes it", async () => {
    const user = userEvent.setup();
    render(<ConsoleShell>content</ConsoleShell>);
    const button = screen.getByRole("button", { name: "Open menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveFocus();
  });

  it("signs out from the sidebar", async () => {
    render(<ConsoleShell>content</ConsoleShell>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Sign out" }));
    expect(session.signOut).toHaveBeenCalled();
  });

  it("keeps vendors without a complete profile out", () => {
    session.state = { status: "signed-in", user: { ...vendorUser, profile_complete: false } };
    render(<ConsoleShell>content</ConsoleShell>);
    expect(screen.queryByText("content")).toBeNull();
    expect(nav.router.replace).toHaveBeenCalledWith("/onboarding/vendor");
    session.state = { status: "signed-in", user: vendorUser };
  });
});

describe("console sections", () => {
  it.each(CONSOLE_SECTIONS.map((s) => [s.label, s.href]))(
    "%s shows its heading and an empty state",
    (label, href) => {
      render(<SectionPage href={href} />);
      expect(screen.getByRole("heading", { level: 1, name: label })).toBeVisible();
      const section = CONSOLE_SECTIONS.find((s) => s.href === href)!;
      expect(screen.getByRole("heading", { level: 2, name: section.empty.title })).toBeVisible();
    },
  );

  it("matches nested paths to their section, and the dashboard only exactly", () => {
    expect(activeSection("/console/gigs/42")?.label).toBe("Gigs");
    expect(activeSection("/console")?.label).toBe("Dashboard");
    expect(activeSection("/console/unknown")).toBeUndefined();
  });
});
