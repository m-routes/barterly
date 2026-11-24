import Link from "next/link";

import { Logo } from "@/components/Logo";

import { LegalFooter } from "./LegalFooter";

/** The frame of a public legal page, always marked as a draft until a lawyer signs off. */
export function LegalPage({
  title,
  version,
  children,
}: {
  title: string;
  version?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="legal">
      <a href="#main" className="skip-link">
        Skip to content
      </a>
      <header className="landing__header">
        <Link href="/" aria-label="Barterly home">
          <Logo />
        </Link>
      </header>
      <main id="main" className="legal__main">
        <p className="legal__draft" role="note">
          <strong>Draft for lawyer review.</strong> This text is not final and is not yet in force.
        </p>
        <h1 className="legal__title">{title}</h1>
        {version ? <p className="legal__version">Version {version}</p> : null}
        <article className="legal__body">{children}</article>
      </main>
      <LegalFooter />
    </div>
  );
}
