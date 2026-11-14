"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { RequireRole } from "@/components/auth/RequireRole";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/Button";
import { useSession } from "@/lib/session/session";

import { CONSOLE_SECTIONS, activeSection } from "./nav";

function SectionIcon({ href }: { href: string }) {
  // Simple line icons, decorative only (the label names the section).
  const paths: Record<string, string> = {
    "/console": "M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6v-9h-6v9Zm0-16v5h6V4h-6Z",
    "/console/gigs": "M4 7h16v12H4zM9 7V5h6v2",
    "/console/applicants":
      "M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-6 9a6 6 0 0 1 12 0M17 11a3 3 0 0 0 0-6m4 15a6 6 0 0 0-4-5.6",
    "/console/properties": "M3 11 12 4l9 7M5 10v10h14V10M10 20v-5h4v5",
    "/console/verification": "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4",
    "/console/talent": "M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 4 4",
    "/console/agreements": "M7 3h7l4 4v14H7zM14 3v4h4M10 12h5M10 16h5",
    "/console/payments": "M3 7h18v10H3zM3 11h18M7 15h3",
    "/console/analytics": "M4 20V10m6 10V4m6 16v-7m4 7H2",
  };
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
      <path
        d={paths[href]}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function Sidebar({ account, onNavigate }: { account: string; onNavigate?: () => void }) {
  const pathname = usePathname();
  const active = activeSection(pathname);
  const { signOut } = useSession();
  return (
    <>
      <nav aria-label="Console">
        <ul className="sidebar__list">
          {CONSOLE_SECTIONS.map((section) => (
            <li key={section.href}>
              <Link
                href={section.href}
                className="sidebar__link"
                aria-current={active?.href === section.href ? "page" : undefined}
                onClick={onNavigate}
              >
                <SectionIcon href={section.href} />
                {section.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      <div className="sidebar__footer">
        <p className="sidebar__account">
          Signed in as <span className="sidebar__phone">{account}</span>
        </p>
        <Button variant="ghost" block onClick={() => void signOut()}>
          Sign out
        </Button>
      </div>
    </>
  );
}

function Shell({ account, children }: { account: string; children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="console">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="console__topbar">
        <Logo href="/console" />
        <button
          ref={menuButton}
          type="button"
          className="menu-button"
          aria-expanded={menuOpen}
          aria-controls="console-sidebar"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span className="visually-hidden">{menuOpen ? "Close menu" : "Open menu"}</span>
          <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
            <path
              d={menuOpen ? "M6 6l12 12M18 6 6 18" : "M4 7h16M4 12h16M4 17h16"}
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </header>
      <aside
        id="console-sidebar"
        className={`console__sidebar${menuOpen ? " console__sidebar--open" : ""}`}
      >
        <div className="console__brand">
          <Logo href="/console" />
        </div>
        <Sidebar account={account} onNavigate={() => setMenuOpen(false)} />
      </aside>
      <main id="main" className="console__main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}

/** The vendor console frame: only vendors with a complete profile get in. */
export function ConsoleShell({ children }: { children: React.ReactNode }) {
  return (
    <RequireRole role="vendor" requireComplete>
      {(user) => <Shell account={user.phone}>{children}</Shell>}
    </RequireRole>
  );
}
